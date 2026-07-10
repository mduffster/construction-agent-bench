"""Run the low-cost mixed-policy qualification ladder for S01 V2.

The deterministic efficient witness remains in every background role. Live
Claude Haiku roles are added cumulatively: supplier+GC, inspector, owner+lender,
then labor/full six. The runner stops after an invalid run or a failed lineage
chain when lineage metrics are present. It also refuses to start a rung unless
the conservative budget reserve fits both the new-study allocation and the
all-program cap.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.models import (
    ANTHROPIC_PRICING_USD_PER_MTOK,
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
)
from constructbench.runner import run_policy
from constructbench.s01_v2_ladder import (
    DEFAULT_HARD_TOTAL_CAP_USD,
    DEFAULT_NEW_MODEL_ALLOCATION_USD,
    DEFAULT_PROGRAM_PRIOR_COST_USD,
    DEFAULT_STAGE_RESERVE_PER_LIVE_ROLE_USD,
    DEFAULT_USER_LIMIT_USD,
    EFFICIENT_BACKGROUND_FIXTURE,
    LADDER_STAGE_BY_ID,
    LINEAGE_LIVE_FIELDS_BY_NODE,
    LINEAGE_LIVE_PROFILE_ID,
    S01_V2_LADDER_EXPERIMENT_ID,
    BudgetConfig,
    LadderStage,
    build_mixed_policies,
    default_live_policy_factory,
    deterministic_background_policies,
    lineage_gate,
    run_row,
    stages_through,
    validate_live_roles,
)

EXPECTED_RUN_FILES = {
    "run_config.json",
    "events.jsonl",
    "turn_summaries.jsonl",
    "run_summary.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through-stage",
        choices=list(LADDER_STAGE_BY_ID),
        default="full_six",
        help="run the cumulative ladder through this rung",
    )
    parser.add_argument(
        "--live-roles",
        help="comma-separated roles for one custom rung instead of the cumulative ladder",
    )
    parser.add_argument("--model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--repair-budget", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--program-prior-cost-usd", type=float, default=DEFAULT_PROGRAM_PRIOR_COST_USD
    )
    parser.add_argument(
        "--new-model-allocation-usd", type=float, default=DEFAULT_NEW_MODEL_ALLOCATION_USD
    )
    parser.add_argument("--hard-total-cap-usd", type=float, default=DEFAULT_HARD_TOTAL_CAP_USD)
    parser.add_argument("--user-limit-usd", type=float, default=DEFAULT_USER_LIMIT_USD)
    parser.add_argument(
        "--stage-reserve-per-live-role-usd",
        type=float,
        default=DEFAULT_STAGE_RESERVE_PER_LIVE_ROLE_USD,
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--allow-live-batch", action="store_true")
    parser.add_argument(
        "--allow-dirty-worktree",
        action="store_true",
        help="development only; formal and resumable live runs require a clean worktree",
    )
    args = parser.parse_args()

    budget = BudgetConfig(
        program_prior_cost_usd=args.program_prior_cost_usd,
        new_model_allocation_usd=args.new_model_allocation_usd,
        hard_total_cap_usd=args.hard_total_cap_usd,
        user_limit_usd=args.user_limit_usd,
        stage_reserve_per_live_role_usd=args.stage_reserve_per_live_role_usd,
    )
    budget.validate()
    stages = _selected_stages(args.live_roles, args.through_stage)
    requested_reserve = sum(budget.stage_reserve_usd(stage.live_roles) for stage in stages)
    print(
        "budget preflight: "
        f"prior=${budget.program_prior_cost_usd:.4f} "
        f"requested-stage reserve=${requested_reserve:.4f} "
        f"projected=${budget.program_prior_cost_usd + requested_reserve:.4f} "
        f"hard cap=${budget.hard_total_cap_usd:.4f} "
        f"user limit=${budget.user_limit_usd:.4f}"
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_v2_multiplayer_ladder_{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    current_commit = _current_commit()
    reference_summary = _run_or_resume_reference(
        root / "reference_run",
        current_commit=current_commit,
        allow_dirty_worktree=args.allow_dirty_worktree,
    )
    reference_gate = _reference_gate(reference_summary)
    _write_json(root / "reference_gate.json", reference_gate)
    if not reference_gate["passed"]:
        raise RuntimeError(f"deterministic S01 V2 reference gate failed: {reference_gate}")
    if args.preflight_only:
        _write_progress(
            root,
            stages=stages,
            rows=[],
            budget=budget,
            current_commit=current_commit,
            stop_reason="preflight_only",
        )
        print(f"reference gate passed; wrote {root}")
        return

    if not args.allow_live_batch:
        raise SystemExit("live multiplayer ladder requires --allow-live-batch")
    if args.model not in ANTHROPIC_PRICING_USD_PER_MTOK:
        raise ValueError(f"no known Anthropic pricing entry for model {args.model!r}")
    if args.model != DEFAULT_ANTHROPIC_HAIKU_MODEL:
        raise ValueError(
            "low-cost qualification ladder is frozen to the default Claude Haiku model"
        )
    if args.temperature != 0.0:
        raise ValueError("qualification ladder is frozen at temperature 0")
    if args.repair_budget != 1:
        raise ValueError("qualification ladder is frozen at repair budget 1")
    if args.max_tokens < 256:
        raise ValueError("max-tokens below 256 is unlikely to return a valid submission")
    if not args.allow_dirty_worktree and _worktree_is_dirty():
        raise RuntimeError("formal live ladder requires a clean worktree")

    rows: list[dict[str, Any]] = []
    spent_new_usd = 0.0
    stop_reason: str | None = None
    run_root = root / "runs"
    run_root.mkdir(exist_ok=True)
    for stage_index, stage in enumerate(stages):
        run_dir = run_root / f"{stage_index:02d}_{stage.stage_id}"
        expected_settings = _model_settings(
            stage,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            repair_budget=args.repair_budget,
            seed=args.seed,
        )
        summary_path = run_dir / "run_summary.json"
        if summary_path.exists():
            summary = _validate_existing_run(
                run_dir,
                expected_settings=expected_settings,
                current_commit=current_commit,
                require_archival=not args.allow_dirty_worktree,
            )
        else:
            if run_dir.exists() and any(run_dir.iterdir()):
                raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
            budget.assert_can_start(spent_new_usd=spent_new_usd, live_roles=stage.live_roles)
            policies = build_mixed_policies(
                stage.live_roles,
                live_policy_factory=default_live_policy_factory(
                    model=args.model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                ),
            )
            result = run_policy(
                "S01_V2",
                "normal",
                policies,
                output_dir=run_dir,
                seed=args.seed,
                repair_budget=args.repair_budget,
                model_settings=expected_settings,
            )
            summary = json.loads(summary_path.read_text())
            _require_known_cost(summary, summary_path)
            print(
                f"{stage.stage_id}: valid={result.final_state.run_valid} "
                f"status={result.final_state.terminal_status} "
                f"cost=${_summary_cost(summary):.4f}"
            )

        spent_new_usd += _summary_cost(summary)
        row = run_row(stage=stage, summary=summary)
        rows.append(row)
        budget_error = _post_run_budget_error(budget, spent_new_usd)
        if not row["run_valid"]:
            stop_reason = f"invalid_agent_output:{stage.stage_id}"
        elif row["lineage_gate"]["available"] and not row["lineage_gate"]["passed"]:
            stop_reason = f"lineage_failure:{stage.stage_id}"
        elif budget_error:
            stop_reason = f"budget_stop:{stage.stage_id}"
        _write_progress(
            root,
            stages=stages,
            rows=rows,
            budget=budget,
            current_commit=current_commit,
            stop_reason=stop_reason,
        )
        if budget_error:
            raise RuntimeError(budget_error)
        if stop_reason:
            break

    expected_dirs = {
        (run_root / f"{index:02d}_{stage.stage_id}").resolve() for index, stage in enumerate(stages)
    }
    extras = [
        path
        for path in run_root.rglob("run_summary.json")
        if path.parent.resolve() not in expected_dirs
    ]
    if extras:
        raise RuntimeError(f"unexpected run summaries under ladder root: {extras}")
    print(
        f"wrote {root}; completed={len(rows)}/{len(stages)} "
        f"new_cost=${spent_new_usd:.4f} "
        f"program_cost=${budget.program_prior_cost_usd + spent_new_usd:.4f}"
    )
    if stop_reason:
        raise SystemExit(f"ladder stopped: {stop_reason}")


def _selected_stages(live_roles: str | None, through_stage: str) -> list[LadderStage]:
    if live_roles is None:
        return stages_through(through_stage)
    roles = validate_live_roles(value.strip() for value in live_roles.split(",") if value.strip())
    return [LadderStage("custom_" + "_".join(roles), roles)]


def _model_settings(
    stage: LadderStage,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    repair_budget: int,
    seed: int,
) -> dict[str, Any]:
    return {
        "policy": "s01_v2_mixed_ladder",
        "provider": "anthropic",
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "repair_budget": repair_budget,
        "seed": seed,
        "live_agent_ids": list(stage.live_roles),
        "scripted_agent_ids": [
            agent_id
            for agent_id in deterministic_background_policies()
            if agent_id not in stage.live_roles
        ],
        "scripted_background_fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "experiment_id": S01_V2_LADDER_EXPERIMENT_ID,
        "experiment_stage": stage.stage_id,
        "live_decision_profile": LINEAGE_LIVE_PROFILE_ID,
        "live_parameter_fields_by_node": {
            node_id: list(fields)
            for node_id, fields in LINEAGE_LIVE_FIELDS_BY_NODE.items()
        },
    }


def _run_or_resume_reference(
    run_dir: Path,
    *,
    current_commit: str,
    allow_dirty_worktree: bool,
) -> dict[str, Any]:
    settings = {
        "policy": "s01_v2_ladder_reference",
        "fixture": EFFICIENT_BACKGROUND_FIXTURE,
        "experiment_id": S01_V2_LADDER_EXPERIMENT_ID,
    }
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
    run_policy(
        "S01_V2",
        "normal",
        deterministic_background_policies(),
        output_dir=run_dir,
        model_settings=settings,
        repair_budget=1,
    )
    return json.loads(summary_path.read_text())


def _reference_gate(summary: dict[str, Any]) -> dict[str, Any]:
    analysis = summary.get("s01_v2_analysis", {})
    lineage = lineage_gate(summary)
    checks = {
        "run_valid": summary.get("run_valid") is True,
        "project_success": analysis.get("project_success") is True,
        "coalition_success": analysis.get("coalition_success") is True,
        "all_eighteen_decisions_resolved": analysis.get("decision_count") == 18,
        "lineage_complete_when_available": not lineage["available"] or lineage["passed"] is True,
    }
    return {"passed": all(checks.values()), "checks": checks, "lineage_gate": lineage}


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


def _require_known_cost(summary: dict[str, Any], path: Path) -> None:
    if summary.get("run_manifest", {}).get("usage", {}).get("cost_known") is not True:
        raise RuntimeError(f"model cost is unknown for {path}")


def _summary_cost(summary: dict[str, Any]) -> float:
    return float(
        summary.get("model_usage_summary", {}).get("total", {}).get("cost_usd", 0.0) or 0.0
    )


def _post_run_budget_error(budget: BudgetConfig, spent_new_usd: float) -> str | None:
    if spent_new_usd > budget.new_model_allocation_usd:
        return (
            f"new model allocation exceeded: ${spent_new_usd:.6f} > "
            f"${budget.new_model_allocation_usd:.6f}"
        )
    program_cost = budget.program_prior_cost_usd + spent_new_usd
    if program_cost > budget.hard_total_cap_usd:
        return f"hard total cap exceeded: ${program_cost:.6f} > ${budget.hard_total_cap_usd:.6f}"
    return None


def _write_progress(
    root: Path,
    *,
    stages: list[LadderStage],
    rows: list[dict[str, Any]],
    budget: BudgetConfig,
    current_commit: str,
    stop_reason: str | None,
) -> None:
    spent = round(sum(row["model_cost_usd"] for row in rows), 6)
    requested_stage_reserve = round(
        sum(budget.stage_reserve_usd(stage.live_roles) for stage in stages), 6
    )
    _write_json(
        root / "ladder_summary.json",
        {
            "schema_version": "constructbench.s01_v2_multiplayer_ladder.v1",
            "experiment_id": S01_V2_LADDER_EXPERIMENT_ID,
            "code_commit": current_commit,
            "requested_stages": [stage.stage_id for stage in stages],
            "completed_stage_count": len(rows),
            "stop_reason": stop_reason,
            "program_prior_cost_usd": budget.program_prior_cost_usd,
            "new_model_allocation_usd": budget.new_model_allocation_usd,
            "new_model_cost_usd": spent,
            "program_cumulative_cost_usd": round(budget.program_prior_cost_usd + spent, 6),
            "hard_total_cap_usd": budget.hard_total_cap_usd,
            "user_limit_usd": budget.user_limit_usd,
            "user_limit_reserve_usd": budget.user_limit_reserve_usd,
            "stage_reserve_per_live_role_usd": budget.stage_reserve_per_live_role_usd,
            "requested_stage_reserve_usd": requested_stage_reserve,
            "program_cost_projected_from_stage_reserves_usd": round(
                budget.program_prior_cost_usd + requested_stage_reserve, 6
            ),
            "rows": rows,
        },
    )


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


if __name__ == "__main__":
    main()
