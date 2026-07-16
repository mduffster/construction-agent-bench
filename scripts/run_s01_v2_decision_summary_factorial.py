"""Run the frozen four-arm S01 V2 decision-summary factorial confirmation."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.models import DEFAULT_ANTHROPIC_HAIKU_MODEL
from constructbench.runner import run_policy
from constructbench.s01_v2_decision_summary_factorial import (
    BOTH_SUMMARIES,
    CONTRACTOR_ONLY,
    DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
    FACTORIAL_CONDITIONS,
    NO_SUMMARY,
    SUPPLIER_ONLY,
    aggregate_factorial_rows,
    build_factorial_policies,
    factorial_reference_policies,
    factorial_run_row,
    summary_recipients,
)
from constructbench.s01_v2_derived_state_packet import DERIVED_STATE_PACKET_SCHEMA_VERSION
from constructbench.s01_v2_ladder import (
    EFFICIENT_BACKGROUND_FIXTURE,
    LINEAGE_LIVE_FIELDS_BY_NODE,
    LINEAGE_LIVE_PROFILE_ID,
    default_live_policy_factory,
    lineage_gate,
)
from scripts.run_s01_v2_derived_state_packet import (
    _reference_outcome_signature,
    _require_known_cost,
    _summary_call_count,
    _summary_cost,
    _validate_existing_run,
    _write_json,
    _write_jsonl,
)

FROZEN_MODEL = DEFAULT_ANTHROPIC_HAIKU_MODEL
FROZEN_TEMPERATURE = 0.0
FROZEN_MAX_TOKENS = 1200
FROZEN_REPAIR_BUDGET = 1
FRESH_BUDGET_CAP_USD = 6.8
PER_RUN_RESERVE_USD = 0.17
REPLICATES_PER_ARM = 10

# Ten complete four-arm blocks. Reverse-order pairs limit simple order effects;
# each condition appears once per block and ten times overall.
ORDER_BLOCKS = (
    (NO_SUMMARY, SUPPLIER_ONLY, CONTRACTOR_ONLY, BOTH_SUMMARIES),
    (BOTH_SUMMARIES, CONTRACTOR_ONLY, SUPPLIER_ONLY, NO_SUMMARY),
    (SUPPLIER_ONLY, NO_SUMMARY, BOTH_SUMMARIES, CONTRACTOR_ONLY),
    (CONTRACTOR_ONLY, BOTH_SUMMARIES, NO_SUMMARY, SUPPLIER_ONLY),
    (NO_SUMMARY, CONTRACTOR_ONLY, BOTH_SUMMARIES, SUPPLIER_ONLY),
    (SUPPLIER_ONLY, BOTH_SUMMARIES, CONTRACTOR_ONLY, NO_SUMMARY),
    (BOTH_SUMMARIES, SUPPLIER_ONLY, NO_SUMMARY, CONTRACTOR_ONLY),
    (CONTRACTOR_ONLY, NO_SUMMARY, SUPPLIER_ONLY, BOTH_SUMMARIES),
    (NO_SUMMARY, SUPPLIER_ONLY, CONTRACTOR_ONLY, BOTH_SUMMARIES),
    (BOTH_SUMMARIES, CONTRACTOR_ONLY, SUPPLIER_ONLY, NO_SUMMARY),
)
STUDY_SEQUENCE = tuple(
    (condition, replicate_index)
    for replicate_index, block in enumerate(ORDER_BLOCKS)
    for condition in block
)


@dataclass(frozen=True)
class FactorialBudget:
    cap_usd: float = FRESH_BUDGET_CAP_USD
    per_run_reserve_usd: float = PER_RUN_RESERVE_USD

    def validate(self) -> None:
        if self.cap_usd <= 0 or self.per_run_reserve_usd <= 0:
            raise ValueError("budget values must be positive")
        if round(len(STUDY_SEQUENCE) * self.per_run_reserve_usd, 6) > self.cap_usd:
            raise ValueError("frozen run reserve exceeds factorial budget cap")

    def assert_can_start(self, spent_usd: float) -> None:
        if spent_usd + self.per_run_reserve_usd > self.cap_usd:
            raise RuntimeError(
                "factorial cost stop: "
                f"spent ${spent_usd:.6f} + reserve ${self.per_run_reserve_usd:.6f} "
                f"> cap ${self.cap_usd:.6f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--allow-live-batch", action="store_true")
    parser.add_argument("--allow-dirty-worktree", action="store_true")
    args = parser.parse_args()

    _validate_frozen_design()
    budget = FactorialBudget()
    budget.validate()
    root = args.output_dir or Path("outputs") / (
        "s01_v2_decision_summary_factorial_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    root.mkdir(parents=True, exist_ok=True)
    commit = _current_commit()
    _write_or_validate_manifest(root, commit=commit)

    references = {
        condition: _run_or_resume_reference(
            root / "references" / condition,
            condition=condition,
            commit=commit,
            allow_dirty_worktree=args.allow_dirty_worktree,
        )
        for condition in FACTORIAL_CONDITIONS
    }
    gate = _reference_gate(references)
    _write_json(root / "reference_gate.json", gate)
    if not gate["passed"]:
        raise RuntimeError(f"decision-summary factorial reference gate failed: {gate}")

    if args.preflight_only:
        _write_progress(root, rows=[], stop_reason="preflight_only", commit=commit)
        print(f"factorial preflight passed; wrote {root}")
        return

    if not args.allow_live_batch:
        raise SystemExit("live decision-summary factorial requires --allow-live-batch")
    if not args.allow_dirty_worktree and _worktree_is_dirty():
        raise RuntimeError("formal live factorial requires a clean worktree")

    live_factory = default_live_policy_factory(
        model=FROZEN_MODEL,
        temperature=FROZEN_TEMPERATURE,
        max_tokens=FROZEN_MAX_TOKENS,
    )
    run_root = root / "runs"
    run_root.mkdir(exist_ok=True)
    _validate_existing_prefix(run_root)
    rows: list[dict[str, Any]] = []
    spent = 0.0
    for sequence_index, (condition, replicate_index) in enumerate(STUDY_SEQUENCE):
        run_dir = run_root / _run_dir_name(sequence_index, condition, replicate_index)
        settings = _model_settings(condition, replicate_index, sequence_index)
        summary_path = run_dir / "run_summary.json"
        if summary_path.exists():
            summary = _validate_existing_run(
                run_dir,
                expected_settings=settings,
                current_commit=commit,
                require_archival=not args.allow_dirty_worktree,
            )
        else:
            if run_dir.exists() and any(run_dir.iterdir()):
                raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
            budget.assert_can_start(spent)
            result = run_policy(
                "S01_V2",
                "normal",
                build_factorial_policies(condition, live_factory),
                output_dir=run_dir,
                seed=replicate_index,
                repair_budget=FROZEN_REPAIR_BUDGET,
                model_settings=settings,
            )
            summary = json.loads(summary_path.read_text())
            _require_known_cost(summary, summary_path)
            print(
                f"{run_dir.name}: valid={result.final_state.run_valid} "
                f"status={result.final_state.terminal_status} "
                f"cost=${_summary_cost(summary):.6f}"
            )
        spent += _summary_cost(summary)
        row = factorial_run_row(
            condition=condition,
            replicate_index=replicate_index,
            sequence_index=sequence_index,
            summary=summary,
        )
        rows.append(row)
        _write_progress(root, rows=rows, stop_reason=None, commit=commit)
        if spent > budget.cap_usd:
            _write_progress(root, rows=rows, stop_reason="budget_stop", commit=commit)
            raise RuntimeError(f"factorial cap exceeded: ${spent:.6f} > ${budget.cap_usd:.6f}")

    _validate_existing_prefix(run_root, require_complete=True)
    print(f"wrote {root}; runs={len(rows)} cost=${spent:.6f}")


def _validate_frozen_design() -> None:
    if len(STUDY_SEQUENCE) != len(FACTORIAL_CONDITIONS) * REPLICATES_PER_ARM:
        raise RuntimeError("factorial sequence length does not match frozen design")
    for condition in FACTORIAL_CONDITIONS:
        if sum(item == condition for item, _ in STUDY_SEQUENCE) != REPLICATES_PER_ARM:
            raise RuntimeError(f"factorial condition count mismatch for {condition}")


def _model_settings(condition: str, replicate_index: int, sequence_index: int) -> dict[str, Any]:
    return {
        "policy": "s01_v2_decision_summary_factorial",
        "provider": "anthropic",
        "model": FROZEN_MODEL,
        "temperature": FROZEN_TEMPERATURE,
        "max_tokens": FROZEN_MAX_TOKENS,
        "repair_budget": FROZEN_REPAIR_BUDGET,
        "seed": replicate_index,
        "experiment_id": DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
        "experiment_condition": condition,
        "replicate_index": replicate_index,
        "sequence_index": sequence_index,
        "study_sequence": [item for item, _ in STUDY_SEQUENCE],
        "decision_summary_recipients": sorted(summary_recipients(condition)),
        "packet_schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
        "live_agent_ids": ["steel_supplier", "gc"],
        "scripted_agent_ids": ["owner", "labor_subcontractor", "lender", "inspector"],
        "scripted_background_fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "live_decision_profile": LINEAGE_LIVE_PROFILE_ID,
        "live_parameter_fields_by_node": {
            node_id: list(fields) for node_id, fields in LINEAGE_LIVE_FIELDS_BY_NODE.items()
        },
    }


def _reference_settings(condition: str) -> dict[str, Any]:
    return {
        "policy": "s01_v2_decision_summary_factorial_reference",
        "fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "experiment_id": DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
        "experiment_condition": condition,
        "decision_summary_recipients": sorted(summary_recipients(condition)),
        "packet_schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
    }


def _run_or_resume_reference(
    run_dir: Path, *, condition: str, commit: str, allow_dirty_worktree: bool
) -> dict[str, Any]:
    settings = _reference_settings(condition)
    summary_path = run_dir / "run_summary.json"
    if summary_path.exists():
        return _validate_existing_run(
            run_dir,
            expected_settings=settings,
            current_commit=commit,
            require_archival=not allow_dirty_worktree,
            require_known_cost=False,
        )
    run_policy(
        "S01_V2",
        "normal",
        factorial_reference_policies(condition),
        output_dir=run_dir,
        repair_budget=FROZEN_REPAIR_BUDGET,
        model_settings=settings,
    )
    return json.loads(summary_path.read_text())


def _reference_gate(references: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline = _reference_outcome_signature(references[NO_SUMMARY])
    checks: dict[str, bool] = {}
    for condition, summary in references.items():
        analysis = summary.get("s01_v2_analysis", {})
        exposures = analysis.get("observation_intervention_exposures", [])
        expected = {
            (agent_id, {"steel_supplier": "S01_B1_SUPPLIER_COMMITMENT", "gc": "S01_B2_GC_INTEGRATED_PACKAGE"}[agent_id])
            for agent_id in summary_recipients(condition)
        }
        actual = {(item.get("agent_id"), item.get("phase_id")) for item in exposures}
        checks[f"{condition}_valid"] = summary.get("run_valid") is True
        checks[f"{condition}_lineage_complete"] = lineage_gate(summary).get("passed") is True
        checks[f"{condition}_no_model_calls"] = _summary_call_count(summary) == 0
        checks[f"{condition}_exposure_exact"] = (
            actual == expected
            and len(exposures) == len(expected)
            and all(item.get("hash_matches") is True for item in exposures)
        )
        checks[f"{condition}_consequence_inert"] = _reference_outcome_signature(summary) == baseline
    return {"passed": all(checks.values()), "checks": checks}


def _write_or_validate_manifest(root: Path, *, commit: str) -> None:
    payload = {
        "schema_version": "constructbench.s01_v2_decision_summary_factorial_manifest.v1",
        "experiment_id": DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
        "code_commit": commit,
        "model": FROZEN_MODEL,
        "temperature": FROZEN_TEMPERATURE,
        "max_tokens": FROZEN_MAX_TOKENS,
        "repair_budget": FROZEN_REPAIR_BUDGET,
        "replicates_per_arm": REPLICATES_PER_ARM,
        "fresh_budget_cap_usd": FRESH_BUDGET_CAP_USD,
        "per_run_reserve_usd": PER_RUN_RESERVE_USD,
        "study_sequence": [
            {"sequence_index": index, "condition": condition, "replicate_index": replicate}
            for index, (condition, replicate) in enumerate(STUDY_SEQUENCE)
        ],
    }
    path = root / "study_manifest.json"
    if path.exists() and json.loads(path.read_text()) != payload:
        raise RuntimeError("factorial study manifest mismatch")
    if not path.exists():
        _write_json(path, payload)


def _write_progress(
    root: Path, *, rows: list[dict[str, Any]], stop_reason: str | None, commit: str
) -> None:
    _write_jsonl(root / "study_rows.jsonl", rows)
    _write_json(
        root / "study_analysis.json",
        {
            "schema_version": "constructbench.s01_v2_decision_summary_factorial_analysis.v1",
            "experiment_id": DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
            "code_commit": commit,
            "requested_run_count": len(STUDY_SEQUENCE),
            "completed_run_count": len(rows),
            "stop_reason": stop_reason,
            "fresh_budget_cap_usd": FRESH_BUDGET_CAP_USD,
            "per_run_reserve_usd": PER_RUN_RESERVE_USD,
            "aggregate": aggregate_factorial_rows(rows) if rows else None,
        },
    )


def _validate_existing_prefix(run_root: Path, *, require_complete: bool = False) -> None:
    missing_seen = False
    expected = []
    for index, (condition, replicate) in enumerate(STUDY_SEQUENCE):
        run_dir = run_root / _run_dir_name(index, condition, replicate)
        expected.append(run_dir.resolve())
        exists = (run_dir / "run_summary.json").exists()
        if run_dir.exists() and any(run_dir.iterdir()) and not exists:
            raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
        if not exists:
            missing_seen = True
        elif missing_seen:
            raise RuntimeError("completed factorial runs must form an exact prefix")
    extras = [
        path for path in run_root.rglob("run_summary.json") if path.parent.resolve() not in expected
    ]
    if extras:
        raise RuntimeError(f"unexpected factorial run summaries: {extras}")
    if require_complete and missing_seen:
        raise RuntimeError("factorial output is incomplete")


def _run_dir_name(sequence_index: int, condition: str, replicate_index: int) -> str:
    return f"{sequence_index:02d}_{condition}_replicate_{replicate_index:02d}"


def _current_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _worktree_is_dirty() -> bool:
    return bool(
        subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )


if __name__ == "__main__":
    main()
