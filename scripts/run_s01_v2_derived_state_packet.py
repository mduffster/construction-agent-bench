"""Run the frozen low-cost S01 V2 post-R1 derived-state packet study.

The supplier and GC remain live in both arms.  The treatment changes only the
post-R1 observations at supplier B1 and GC B2; every other organization uses
the same state-aware deterministic control.  Six trials are dispatched in a
frozen ABBAAB order with paired replicate seeds.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.s01_v2_derived_state_packet import (
    CONTROL_CONDITION,
    DERIVED_STATE_PACKET_EXPERIMENT_ID,
    DERIVED_STATE_PACKET_SCHEMA_VERSION,
    TREATMENT_CONDITION,
    aggregate_study_rows,
    build_study_policies,
    packetized_deterministic_policies,
    study_run_row,
)

from constructbench.models import (
    ANTHROPIC_PRICING_USD_PER_MTOK,
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
)
from constructbench.runner import run_policy
from constructbench.s01_v2_ladder import (
    EFFICIENT_BACKGROUND_FIXTURE,
    LINEAGE_LIVE_FIELDS_BY_NODE,
    LINEAGE_LIVE_PROFILE_ID,
    default_live_policy_factory,
    deterministic_background_policies,
    lineage_gate,
)

EXPECTED_RUN_FILES = {
    "run_config.json",
    "events.jsonl",
    "turn_summaries.jsonl",
    "run_summary.json",
}
STUDY_SEQUENCE = (
    (CONTROL_CONDITION, 0),
    (TREATMENT_CONDITION, 0),
    (TREATMENT_CONDITION, 1),
    (CONTROL_CONDITION, 1),
    (CONTROL_CONDITION, 2),
    (TREATMENT_CONDITION, 2),
)
DEFAULT_PROGRAM_PRIOR_COST_USD = 8.476765
DEFAULT_NEW_MODEL_ALLOCATION_USD = 1.02
DEFAULT_PER_RUN_RESERVE_USD = 0.17
DEFAULT_HARD_TOTAL_CAP_USD = 9.5
DEFAULT_USER_LIMIT_USD = 10.0
FROZEN_TEMPERATURE = 0.0
FROZEN_MAX_TOKENS = 1200
FROZEN_REPAIR_BUDGET = 1


@dataclass(frozen=True)
class StudyBudget:
    program_prior_cost_usd: float = DEFAULT_PROGRAM_PRIOR_COST_USD
    new_model_allocation_usd: float = DEFAULT_NEW_MODEL_ALLOCATION_USD
    per_run_reserve_usd: float = DEFAULT_PER_RUN_RESERVE_USD
    hard_total_cap_usd: float = DEFAULT_HARD_TOTAL_CAP_USD
    user_limit_usd: float = DEFAULT_USER_LIMIT_USD

    def validate(self, *, run_count: int = len(STUDY_SEQUENCE)) -> None:
        values = {
            "program_prior_cost_usd": self.program_prior_cost_usd,
            "new_model_allocation_usd": self.new_model_allocation_usd,
            "per_run_reserve_usd": self.per_run_reserve_usd,
            "hard_total_cap_usd": self.hard_total_cap_usd,
            "user_limit_usd": self.user_limit_usd,
        }
        negative = [name for name, value in values.items() if value < 0]
        if negative:
            raise ValueError(f"budget values cannot be negative: {negative}")
        if run_count < 1:
            raise ValueError("run_count must be positive")
        if self.hard_total_cap_usd >= self.user_limit_usd:
            raise ValueError("hard_total_cap_usd must remain strictly below the user limit")
        if self.program_prior_cost_usd >= self.hard_total_cap_usd:
            raise ValueError("program prior cost already reaches the hard total cap")
        if self.program_prior_cost_usd + self.new_model_allocation_usd > self.hard_total_cap_usd:
            raise ValueError(
                "program prior cost plus the new allocation exceeds the hard total cap"
            )
        requested_reserve = self.requested_reserve_usd(run_count=run_count)
        if requested_reserve > self.new_model_allocation_usd:
            raise ValueError("requested run reserve exceeds the new-model allocation")
        if self.program_prior_cost_usd + requested_reserve > self.hard_total_cap_usd:
            raise ValueError("requested run reserve exceeds the hard program cap")

    def requested_reserve_usd(self, *, run_count: int = len(STUDY_SEQUENCE)) -> float:
        return round(run_count * self.per_run_reserve_usd, 6)

    def assert_can_start(self, *, spent_new_usd: float) -> None:
        self.validate()
        projected_new = spent_new_usd + self.per_run_reserve_usd
        projected_program = self.program_prior_cost_usd + projected_new
        if projected_new > self.new_model_allocation_usd:
            raise RuntimeError(
                "new-model allocation stop: "
                f"spent ${spent_new_usd:.6f} + next-run reserve "
                f"${self.per_run_reserve_usd:.6f} > allocation "
                f"${self.new_model_allocation_usd:.6f}"
            )
        if projected_program > self.hard_total_cap_usd:
            raise RuntimeError(
                "hard program cost stop: "
                f"prior ${self.program_prior_cost_usd:.6f} + new "
                f"${spent_new_usd:.6f} + next-run reserve "
                f"${self.per_run_reserve_usd:.6f} > cap "
                f"${self.hard_total_cap_usd:.6f}"
            )

    @property
    def user_limit_reserve_usd(self) -> float:
        return self.user_limit_usd - self.hard_total_cap_usd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--temperature", type=float, default=FROZEN_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=FROZEN_MAX_TOKENS)
    parser.add_argument("--repair-budget", type=int, default=FROZEN_REPAIR_BUDGET)
    parser.add_argument(
        "--program-prior-cost-usd",
        type=float,
        default=DEFAULT_PROGRAM_PRIOR_COST_USD,
    )
    parser.add_argument(
        "--new-model-allocation-usd",
        type=float,
        default=DEFAULT_NEW_MODEL_ALLOCATION_USD,
    )
    parser.add_argument(
        "--per-run-reserve-usd",
        type=float,
        default=DEFAULT_PER_RUN_RESERVE_USD,
    )
    parser.add_argument("--hard-total-cap-usd", type=float, default=DEFAULT_HARD_TOTAL_CAP_USD)
    parser.add_argument("--user-limit-usd", type=float, default=DEFAULT_USER_LIMIT_USD)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--allow-live-batch", action="store_true")
    parser.add_argument(
        "--allow-dirty-worktree",
        action="store_true",
        help="development only; formal and resumable live runs require a clean worktree",
    )
    args = parser.parse_args()

    budget = StudyBudget(
        program_prior_cost_usd=args.program_prior_cost_usd,
        new_model_allocation_usd=args.new_model_allocation_usd,
        per_run_reserve_usd=args.per_run_reserve_usd,
        hard_total_cap_usd=args.hard_total_cap_usd,
        user_limit_usd=args.user_limit_usd,
    )
    budget.validate()
    requested_reserve = budget.requested_reserve_usd()
    print(
        "budget preflight: "
        f"prior=${budget.program_prior_cost_usd:.6f} "
        f"six-run reserve=${requested_reserve:.6f} "
        f"projected=${budget.program_prior_cost_usd + requested_reserve:.6f} "
        f"hard cap=${budget.hard_total_cap_usd:.4f} "
        f"user limit=${budget.user_limit_usd:.4f}"
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_v2_derived_state_packet_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    current_commit = _current_commit()
    _write_or_validate_manifest(
        root,
        current_commit=current_commit,
        budget=budget,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        repair_budget=args.repair_budget,
    )

    control_reference = _run_or_resume_reference(
        root / "reference_control",
        condition=CONTROL_CONDITION,
        current_commit=current_commit,
        allow_dirty_worktree=args.allow_dirty_worktree,
    )
    packet_reference = _run_or_resume_reference(
        root / "reference_treatment",
        condition=TREATMENT_CONDITION,
        current_commit=current_commit,
        allow_dirty_worktree=args.allow_dirty_worktree,
    )
    reference_gate = _reference_gate(control_reference, packet_reference)
    _write_json(root / "reference_gate.json", reference_gate)
    if not reference_gate["passed"]:
        raise RuntimeError(f"deterministic reference or packet inertness failed: {reference_gate}")

    if args.preflight_only:
        _write_progress(
            root,
            rows=[],
            budget=budget,
            current_commit=current_commit,
            stop_reason="preflight_only",
        )
        print(f"reference and packet-inertness gates passed; wrote {root}")
        return

    _validate_live_settings(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        repair_budget=args.repair_budget,
        allow_live_batch=args.allow_live_batch,
    )
    if not args.allow_dirty_worktree and _worktree_is_dirty():
        raise RuntimeError("formal live study requires a clean worktree")

    run_root = root / "runs"
    run_root.mkdir(exist_ok=True)
    _validate_existing_prefix(run_root)
    rows: list[dict[str, Any]] = []
    spent_new_usd = 0.0
    live_factory = default_live_policy_factory(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    stop_reason: str | None = None
    for sequence_index, (condition, replicate_index) in enumerate(STUDY_SEQUENCE):
        run_dir = run_root / _run_dir_name(
            sequence_index=sequence_index,
            condition=condition,
            replicate_index=replicate_index,
        )
        settings = _model_settings(
            condition=condition,
            replicate_index=replicate_index,
            sequence_index=sequence_index,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            repair_budget=args.repair_budget,
        )
        summary_path = run_dir / "run_summary.json"
        if summary_path.exists():
            summary = _validate_existing_run(
                run_dir,
                expected_settings=settings,
                current_commit=current_commit,
                require_archival=not args.allow_dirty_worktree,
            )
        else:
            if run_dir.exists() and any(run_dir.iterdir()):
                raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
            budget.assert_can_start(spent_new_usd=spent_new_usd)
            result = run_policy(
                "S01_V2",
                "normal",
                build_study_policies(condition, live_factory),
                output_dir=run_dir,
                seed=replicate_index,
                repair_budget=args.repair_budget,
                model_settings=settings,
            )
            summary = json.loads(summary_path.read_text())
            _require_known_cost(summary, summary_path)
            print(
                f"{run_dir.name}: valid={result.final_state.run_valid} "
                f"status={result.final_state.terminal_status} "
                f"cost=${_summary_cost(summary):.6f}"
            )

        spent_new_usd += _summary_cost(summary)
        rows.append(
            study_run_row(
                condition=condition,
                replicate_index=replicate_index,
                sequence_index=sequence_index,
                summary=summary,
            )
        )
        budget_error = _post_run_budget_error(budget, spent_new_usd)
        stop_reason = "budget_stop" if budget_error else None
        _write_progress(
            root,
            rows=rows,
            budget=budget,
            current_commit=current_commit,
            stop_reason=stop_reason,
        )
        if budget_error:
            raise RuntimeError(budget_error)

    _validate_existing_prefix(run_root, require_complete=True)
    print(
        f"wrote {root}; completed={len(rows)}/{len(STUDY_SEQUENCE)} "
        f"new_cost=${spent_new_usd:.6f} "
        f"program_cost=${budget.program_prior_cost_usd + spent_new_usd:.6f}"
    )


def _validate_live_settings(
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    repair_budget: int,
    allow_live_batch: bool,
) -> None:
    if not allow_live_batch:
        raise SystemExit("live derived-state packet study requires --allow-live-batch")
    if model not in ANTHROPIC_PRICING_USD_PER_MTOK:
        raise ValueError(f"no known Anthropic pricing entry for model {model!r}")
    if model != DEFAULT_ANTHROPIC_HAIKU_MODEL:
        raise ValueError("derived-state packet study is frozen to Claude Haiku")
    if temperature != FROZEN_TEMPERATURE:
        raise ValueError("derived-state packet study is frozen at temperature 0")
    if max_tokens != FROZEN_MAX_TOKENS:
        raise ValueError("derived-state packet study is frozen at 1,200 output tokens")
    if repair_budget != FROZEN_REPAIR_BUDGET:
        raise ValueError("derived-state packet study is frozen at repair budget 1")


def _model_settings(
    *,
    condition: str,
    replicate_index: int,
    sequence_index: int,
    model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL,
    temperature: float = FROZEN_TEMPERATURE,
    max_tokens: int = FROZEN_MAX_TOKENS,
    repair_budget: int = FROZEN_REPAIR_BUDGET,
) -> dict[str, Any]:
    return {
        "policy": "s01_v2_derived_state_packet",
        "provider": "anthropic",
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "repair_budget": repair_budget,
        "seed": replicate_index,
        "live_agent_ids": ["steel_supplier", "gc"],
        "scripted_agent_ids": [
            "owner",
            "labor_subcontractor",
            "lender",
            "inspector",
        ],
        "scripted_background_fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
        "experiment_condition": condition,
        "replicate_index": replicate_index,
        "sequence_index": sequence_index,
        "study_sequence": [condition for condition, _ in STUDY_SEQUENCE],
        "packet_schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
        "packet_intervention_nodes": [
            "S01_B1_SUPPLIER_COMMITMENT",
            "S01_B2_GC_INTEGRATED_PACKAGE",
        ],
        "live_decision_profile": LINEAGE_LIVE_PROFILE_ID,
        "live_parameter_fields_by_node": {
            node_id: list(fields) for node_id, fields in LINEAGE_LIVE_FIELDS_BY_NODE.items()
        },
    }


def _reference_settings(condition: str) -> dict[str, Any]:
    return {
        "policy": "s01_v2_derived_state_packet_reference",
        "fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
        "experiment_condition": condition,
        "packet_schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
    }


def _run_or_resume_reference(
    run_dir: Path,
    *,
    condition: str,
    current_commit: str,
    allow_dirty_worktree: bool,
) -> dict[str, Any]:
    settings = _reference_settings(condition)
    summary_path = run_dir / "run_summary.json"
    if summary_path.exists():
        return _validate_existing_run(
            run_dir,
            expected_settings=settings,
            current_commit=current_commit,
            require_archival=not allow_dirty_worktree,
            require_known_cost=False,
        )
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError(f"partial reference directory cannot be resumed: {run_dir}")
    policies = (
        packetized_deterministic_policies()
        if condition == TREATMENT_CONDITION
        else deterministic_background_policies()
    )
    run_policy(
        "S01_V2",
        "normal",
        policies,
        output_dir=run_dir,
        model_settings=settings,
        repair_budget=FROZEN_REPAIR_BUDGET,
    )
    return json.loads(summary_path.read_text())


def _reference_gate(
    control_summary: dict[str, Any], treatment_summary: dict[str, Any]
) -> dict[str, Any]:
    control_lineage = lineage_gate(control_summary)
    treatment_lineage = lineage_gate(treatment_summary)
    control_analysis = control_summary.get("s01_v2_analysis", {})
    treatment_analysis = treatment_summary.get("s01_v2_analysis", {})
    control_exposures = control_analysis.get("observation_intervention_exposures", [])
    treatment_exposures = treatment_analysis.get("observation_intervention_exposures", [])
    expected_treatment_targets = {
        ("steel_supplier", "S01_B1_SUPPLIER_COMMITMENT"),
        ("gc", "S01_B2_GC_INTEGRATED_PACKAGE"),
    }
    checks = {
        "control_valid": control_summary.get("run_valid") is True,
        "treatment_valid": treatment_summary.get("run_valid") is True,
        "control_project_and_coalition_success": (
            control_analysis.get("project_success") is True
            and control_analysis.get("coalition_success") is True
        ),
        "treatment_project_and_coalition_success": (
            treatment_analysis.get("project_success") is True
            and treatment_analysis.get("coalition_success") is True
        ),
        "control_lineage_complete": control_lineage.get("passed") is True,
        "treatment_lineage_complete": treatment_lineage.get("passed") is True,
        "no_reference_model_calls": (
            _summary_call_count(control_summary) == 0
            and _summary_call_count(treatment_summary) == 0
        ),
        "control_has_no_packet_exposure": (
            control_analysis.get("observation_intervention_exposure_count") == 0
            and control_exposures == []
        ),
        "treatment_has_exact_packet_exposures": (
            treatment_analysis.get("observation_intervention_exposure_count") == 2
            and len(treatment_exposures) == 2
            and {(record.get("agent_id"), record.get("phase_id")) for record in treatment_exposures}
            == expected_treatment_targets
        ),
        "treatment_packet_hashes_match": (
            len(treatment_exposures) == 2
            and all(record.get("hash_matches") is True for record in treatment_exposures)
        ),
        "packet_is_consequence_inert": (
            _reference_outcome_signature(control_summary)
            == _reference_outcome_signature(treatment_summary)
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "control_lineage_gate": control_lineage,
        "treatment_lineage_gate": treatment_lineage,
    }


def _reference_outcome_signature(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "terminal_status": summary.get("terminal_status"),
        "terminal_reason": summary.get("terminal_reason"),
        "final_project_cost": summary.get("final_project_cost"),
        "completion_tick": summary.get("completion_tick"),
        "cost_components": summary.get("cost_components"),
        "decision_history": summary.get("decision_history"),
        "lineage_transitions": summary.get("s01_v2_lineage_transition_history"),
        "organization_ledger": summary.get("organization_ledger"),
        "terminal_values": summary.get("terminal_values"),
    }


def _validate_existing_run(
    run_dir: Path,
    *,
    expected_settings: dict[str, Any],
    current_commit: str,
    require_archival: bool,
    require_known_cost: bool = True,
) -> dict[str, Any]:
    actual_files = {path.name for path in run_dir.iterdir() if path.is_file()}
    if actual_files != EXPECTED_RUN_FILES:
        raise RuntimeError(f"resume output contract mismatch for {run_dir}: {sorted(actual_files)}")
    config = json.loads((run_dir / "run_config.json").read_text())
    if config.get("scenario_id") != "S01_V2_OFFSITE_STEEL_DRAW":
        raise RuntimeError(f"resume scenario mismatch for {run_dir}")
    if config.get("model_settings") != expected_settings:
        raise RuntimeError(f"resume settings mismatch for {run_dir}")
    summary = json.loads((run_dir / "run_summary.json").read_text())
    manifest = summary.get("run_manifest", {})
    if manifest.get("code", {}).get("git_commit") != current_commit:
        raise RuntimeError(f"resume commit mismatch for {run_dir}")
    if require_archival and manifest.get("archival") is not True:
        raise RuntimeError(f"formal resume requires an archival run: {run_dir}")
    if require_known_cost:
        _require_known_cost(summary, run_dir / "run_summary.json")
    return summary


def _validate_existing_prefix(run_root: Path, *, require_complete: bool = False) -> None:
    expected_dirs = [
        run_root
        / _run_dir_name(
            sequence_index=index,
            condition=condition,
            replicate_index=replicate_index,
        )
        for index, (condition, replicate_index) in enumerate(STUDY_SEQUENCE)
    ]
    expected_resolved = {path.resolve() for path in expected_dirs}
    extras = [
        path
        for path in run_root.rglob("run_summary.json")
        if path.parent.resolve() not in expected_resolved
    ]
    if extras:
        raise RuntimeError(f"unexpected run summaries under study root: {extras}")

    missing_seen = False
    for run_dir in expected_dirs:
        summary_exists = (run_dir / "run_summary.json").exists()
        if run_dir.exists() and any(run_dir.iterdir()) and not summary_exists:
            raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
        if not summary_exists:
            missing_seen = True
        elif missing_seen:
            raise RuntimeError("completed study runs must form an exact sequence prefix")
    if require_complete and missing_seen:
        raise RuntimeError("study output is incomplete")


def _run_dir_name(*, sequence_index: int, condition: str, replicate_index: int) -> str:
    return f"{sequence_index:02d}_{condition}_replicate_{replicate_index:02d}"


def _post_run_budget_error(budget: StudyBudget, spent_new_usd: float) -> str | None:
    if spent_new_usd > budget.new_model_allocation_usd:
        return (
            f"new model allocation exceeded: ${spent_new_usd:.6f} > "
            f"${budget.new_model_allocation_usd:.6f}"
        )
    program_cost = budget.program_prior_cost_usd + spent_new_usd
    if program_cost > budget.hard_total_cap_usd:
        return f"hard total cap exceeded: ${program_cost:.6f} > ${budget.hard_total_cap_usd:.6f}"
    if program_cost >= budget.user_limit_usd:
        return f"user limit reached: ${program_cost:.6f} >= ${budget.user_limit_usd:.6f}"
    return None


def _write_or_validate_manifest(
    root: Path,
    *,
    current_commit: str,
    budget: StudyBudget,
    model: str,
    temperature: float,
    max_tokens: int,
    repair_budget: int,
) -> None:
    payload = {
        "schema_version": "constructbench.s01_v2_derived_state_packet_manifest.v1",
        "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
        "packet_schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
        "code_commit": current_commit,
        "study_sequence": [
            {
                "sequence_index": index,
                "condition": condition,
                "replicate_index": replicate_index,
                "seed": replicate_index,
            }
            for index, (condition, replicate_index) in enumerate(STUDY_SEQUENCE)
        ],
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "repair_budget": repair_budget,
        "program_prior_cost_usd": budget.program_prior_cost_usd,
        "new_model_allocation_usd": budget.new_model_allocation_usd,
        "per_run_reserve_usd": budget.per_run_reserve_usd,
        "requested_reserve_usd": budget.requested_reserve_usd(),
        "hard_total_cap_usd": budget.hard_total_cap_usd,
        "user_limit_usd": budget.user_limit_usd,
    }
    path = root / "study_manifest.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != payload:
            raise RuntimeError("study manifest mismatch; refusing incompatible resume")
        return
    _write_json(path, payload)


def _write_progress(
    root: Path,
    *,
    rows: list[dict[str, Any]],
    budget: StudyBudget,
    current_commit: str,
    stop_reason: str | None,
) -> None:
    _write_jsonl(root / "study_rows.jsonl", rows)
    spent = round(sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in rows), 6)
    aggregate = aggregate_study_rows(rows) if rows else None
    _write_json(
        root / "study_analysis.json",
        {
            "schema_version": "constructbench.s01_v2_derived_state_packet_study.v1",
            "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
            "code_commit": current_commit,
            "requested_run_count": len(STUDY_SEQUENCE),
            "completed_run_count": len(rows),
            "stop_reason": stop_reason,
            "program_prior_cost_usd": budget.program_prior_cost_usd,
            "new_model_allocation_usd": budget.new_model_allocation_usd,
            "new_model_cost_usd": spent,
            "program_cumulative_cost_usd": round(budget.program_prior_cost_usd + spent, 6),
            "requested_reserve_usd": budget.requested_reserve_usd(),
            "program_cost_projected_from_reserve_usd": round(
                budget.program_prior_cost_usd + budget.requested_reserve_usd(),
                6,
            ),
            "hard_total_cap_usd": budget.hard_total_cap_usd,
            "user_limit_usd": budget.user_limit_usd,
            "user_limit_reserve_usd": budget.user_limit_reserve_usd,
            "aggregate": aggregate,
        },
    )


def _require_known_cost(summary: dict[str, Any], path: Path) -> None:
    if summary.get("run_manifest", {}).get("usage", {}).get("cost_known") is not True:
        raise RuntimeError(f"model cost is unknown for {path}")


def _summary_cost(summary: dict[str, Any]) -> float:
    return float(
        summary.get("model_usage_summary", {}).get("total", {}).get("cost_usd", 0.0) or 0.0
    )


def _summary_call_count(summary: dict[str, Any]) -> int:
    return int(summary.get("model_usage_summary", {}).get("total", {}).get("call_count", 0) or 0)


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _worktree_is_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, check=True
    )
    return bool(result.stdout.strip())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


if __name__ == "__main__":
    main()
