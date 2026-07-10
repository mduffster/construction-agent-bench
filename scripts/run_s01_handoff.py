from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.handoff import (
    HANDOFF_EXPERIMENT_ID,
    HandoffOnlyGCPolicy,
    ScriptedGCHandoffPolicy,
    analyze_handoff_summaries,
    build_handoff_policies,
    handoff_instance_ids,
    run_handoff_reference_grid,
)
from constructbench.models import (
    ANTHROPIC_PRICING_USD_PER_MTOK,
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
    AnthropicModelAdapter,
    LLMPolicy,
)
from constructbench.response_curve import run_reference_grid, summarize_reference_grid
from constructbench.runner import run_policy

LIVE_STAGES = {
    "scripted-prose-modal",
    "scripted-silent-modal",
    "scripted-structured-modal",
    "live-structured-modal",
    "live-prose-modal",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the controlled S01 GC-to-supplier threshold-handoff experiment."
    )
    parser.add_argument(
        "--stage",
        choices=["references", *sorted(LIVE_STAGES)],
        default="references",
    )
    parser.add_argument("--supplier-model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--gc-model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates-per-cell", type=int, default=1)
    parser.add_argument("--repair-budget", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=2.0)
    parser.add_argument("--program-prior-cost-usd", type=float, default=0.0)
    parser.add_argument("--per-run-reserve-usd", type=float, default=0.25)
    parser.add_argument("--require-clean-worktree", action="store_true")
    parser.add_argument(
        "--instance-ids",
        help="Optional comma-separated diagnostic subset from the selected protocol.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-model", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_handoff_{args.stage}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    reference_rows = run_handoff_reference_grid()
    reference_gate = _reference_gate(reference_rows)
    _write_json(root / "handoff_reference_grid.json", reference_rows)
    _write_json(root / "handoff_reference_gate.json", reference_gate)
    if args.stage == "references":
        print(f"wrote {root}")
        print(
            f"reference_runs={len(reference_rows)} "
            f"gate_passed={reference_gate['passed']} model_cost_usd=0"
        )
        return

    if not args.allow_live_model:
        raise SystemExit(f"{args.stage} requires --allow-live-model")
    if args.supplier_model not in ANTHROPIC_PRICING_USD_PER_MTOK:
        raise ValueError(f"no cost table entry for supplier model {args.supplier_model!r}")
    if args.stage.startswith("live-") and args.gc_model not in ANTHROPIC_PRICING_USD_PER_MTOK:
        raise ValueError(f"no cost table entry for GC model {args.gc_model!r}")
    current_commit = _current_commit()
    if args.require_clean_worktree and _worktree_is_dirty():
        raise RuntimeError("formal live runs require a clean worktree")
    if not reference_gate["passed"]:
        raise RuntimeError("deterministic handoff reference gate failed")
    if args.replicates_per_cell < 1:
        raise ValueError("replicates-per-cell must be at least 1")

    protocol = _protocol_for_stage(args.stage)
    available_instance_ids = handoff_instance_ids(protocol=protocol)
    instance_ids = (
        [value.strip() for value in args.instance_ids.split(",") if value.strip()]
        if args.instance_ids
        else available_instance_ids
    )
    unknown_ids = sorted(set(instance_ids) - set(available_instance_ids))
    if unknown_ids:
        raise ValueError(f"instances are unavailable for protocol {protocol}: {unknown_ids}")
    response_references = summarize_reference_grid(run_reference_grid())
    raw_root = root / "raw_runs"
    raw_root.mkdir(parents=True, exist_ok=True)
    total_cost = 0.0
    expected_summary_paths: list[Path] = []

    for instance_id in instance_ids:
        for replicate_index in range(args.replicates_per_cell):
            run_dir = raw_root / f"{instance_id}_replicate_{replicate_index:02d}"
            summary_path = run_dir / "run_summary.json"
            expected_summary_paths.append(summary_path)
            expected_settings = {
                "policy": "handoff",
                "provider": "anthropic",
                "model": args.supplier_model,
                "supplier_model": args.supplier_model,
                "gc_model": (args.gc_model if args.stage.startswith("live-") else "scripted"),
                "temperature": args.temperature,
                "repair_budget": args.repair_budget,
                "focal_agent_id": "steel_supplier",
                "live_agent_ids": (
                    ["steel_supplier", "gc"]
                    if args.stage.startswith("live-")
                    else ["steel_supplier"]
                ),
                "scenario_instance_id": instance_id,
                "replicate_index": replicate_index,
                "experiment_id": HANDOFF_EXPERIMENT_ID,
                "experiment_stage": args.stage,
                "handoff_condition": args.stage.removesuffix("-modal"),
                "handoff_protocol": protocol,
            }
            if summary_path.exists():
                durable = _validate_existing_run(
                    run_dir,
                    expected_settings=expected_settings,
                    current_commit=current_commit,
                    require_archival=args.require_clean_worktree,
                )
                total_cost += _summary_cost(durable)
                continue
            if run_dir.exists() and any(run_dir.iterdir()):
                raise RuntimeError(f"partial run directory cannot be resumed: {run_dir}")
            projected = args.program_prior_cost_usd + total_cost + args.per_run_reserve_usd
            if projected > args.max_cost_usd:
                raise RuntimeError(
                    f"hard cost stop reached before {instance_id}: "
                    f"prior ${args.program_prior_cost_usd:.4f} + stage ${total_cost:.4f} + "
                    f"reserve ${args.per_run_reserve_usd:.4f} > ${args.max_cost_usd:.4f}"
                )

            supplier_policy = LLMPolicy(
                AnthropicModelAdapter(
                    model=args.supplier_model,
                    temperature=args.temperature,
                ),
                "steel_supplier",
                prompt_style="anthropic_structured",
            )
            live_agent_ids = ["steel_supplier"]
            if args.stage == "scripted-prose-modal":
                gc_policy = ScriptedGCHandoffPolicy("prose")
            elif args.stage == "scripted-silent-modal":
                gc_policy = ScriptedGCHandoffPolicy("silent")
            elif args.stage == "scripted-structured-modal":
                gc_policy = ScriptedGCHandoffPolicy("structured")
            else:
                gc_policy = HandoffOnlyGCPolicy(
                    LLMPolicy(
                        AnthropicModelAdapter(
                            model=args.gc_model,
                            temperature=args.temperature,
                        ),
                        "gc",
                        prompt_style="anthropic_structured",
                    ),
                )
                live_agent_ids.append("gc")

            result = run_policy(
                "S01",
                "normal",
                build_handoff_policies(
                    gc_policy=gc_policy,
                    supplier_policy=supplier_policy,
                ),
                output_dir=run_dir,
                seed=replicate_index,
                scenario_instance_id=instance_id,
                repair_budget=args.repair_budget,
                model_settings=expected_settings,
            )
            durable = json.loads(summary_path.read_text())
            _require_known_cost(durable, summary_path)
            cost = _summary_cost(durable)
            total_cost += cost
            print(
                f"{run_dir.name}: valid={result.final_state.run_valid} "
                f"status={result.final_state.terminal_status} cost=${cost:.4f} "
                f"cumulative=${total_cost:.4f}"
            )
            if args.program_prior_cost_usd + total_cost > args.max_cost_usd:
                raise RuntimeError(
                    f"hard cost stop exceeded after {run_dir.name}: "
                    f"${args.program_prior_cost_usd + total_cost:.4f} > "
                    f"${args.max_cost_usd:.4f}"
                )

    expected_dirs = {path.parent.resolve() for path in expected_summary_paths}
    extra_summaries = [
        path
        for path in raw_root.rglob("run_summary.json")
        if path.parent.resolve() not in expected_dirs
    ]
    if extra_summaries:
        raise RuntimeError(f"unexpected run summaries under study root: {extra_summaries}")
    summaries = [json.loads(path.read_text()) for path in expected_summary_paths]
    analysis = analyze_handoff_summaries(
        summaries,
        reference_summaries=response_references,
        handoff_condition=args.stage.removesuffix("-modal"),
    )
    analysis.update(
        {
            "stage": args.stage,
            "handoff_protocol": protocol,
            "supplier_model": args.supplier_model,
            "gc_model": args.gc_model if args.stage.startswith("live-") else "scripted",
            "temperature": args.temperature,
            "replicates_per_cell": args.replicates_per_cell,
            "repair_budget": args.repair_budget,
            "max_cost_usd": args.max_cost_usd,
            "program_prior_cost_usd": args.program_prior_cost_usd,
            "program_cumulative_cost_usd": round(args.program_prior_cost_usd + total_cost, 6),
            "per_run_reserve_usd": args.per_run_reserve_usd,
            "code_commit": current_commit,
            "instance_ids": instance_ids,
        }
    )
    rows = analysis.pop("rows")
    analysis["modal_gate"] = _modal_gate(
        analysis,
        stage=args.stage,
        expected_run_count=len(instance_ids) * args.replicates_per_cell,
    )
    analysis["behavioral_result"] = _behavioral_result(
        analysis,
        stage=args.stage,
    )
    _write_json(root / "handoff_analysis.json", analysis)
    _write_jsonl(root / "handoff_rows.jsonl", rows)
    print(f"wrote {root}")
    print(
        f"runs={analysis['run_count']} valid={analysis['valid_run_count']} "
        f"transmission_rate={analysis['threshold_transmission_rate']} "
        f"replacement_rate={analysis['replacement_rate']} "
        f"gate_passed={analysis['modal_gate']['passed']} "
        f"behavioral_target_met={analysis['behavioral_result']['target_met']}"
    )


def _protocol_for_stage(stage: str) -> str:
    return (
        "structured_numeric"
        if stage in {"scripted-structured-modal", "live-structured-modal"}
        else "rendered_prose"
    )


def _reference_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    truthful = [
        row
        for row in rows
        if row["handoff_condition"] in {"structured_numeric:structured", "rendered_prose:prose"}
    ]
    silent = [row for row in rows if row["handoff_condition"] == "rendered_prose:silent"]
    checks = {
        "nine_valid_reference_runs": len(rows) == 9 and all(row["run_valid"] for row in rows),
        "truthful_handoffs_transmit_exact_threshold": all(
            row["transmitted_threshold_usd"] == row["true_threshold_usd"] for row in truthful
        ),
        "truthful_handoffs_select_oracle_safe_request": all(
            row["supplier_request_usd"] == row["maximum_safe_request_usd"] for row in truthful
        ),
        "truthful_handoffs_avoid_replacement": all(
            not row["supplier_replaced"] for row in truthful
        ),
        "truthful_handoffs_are_mutually_viable": all(
            row["mutually_viable_deal"] for row in truthful
        ),
        "truthful_handoffs_match_frozen_supplier_payoffs": {
            row["response_curve_level"]: row["supplier_realized_payoff_usd"]
            for row in truthful
            if row["handoff_protocol"] == "structured_numeric"
        }
        == {"R1": 130_000, "R3": 630_000, "R5": 1_130_000},
        "silent_control_leaks_no_threshold": all(
            row["transmitted_threshold_usd"] is None and not row["handoff_record_exposed"]
            for row in silent
        ),
        "silent_control_is_behaviorally_distinct": any(
            row["supplier_request_usd"] != row["maximum_safe_request_usd"] for row in silent
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _modal_gate(
    analysis: dict[str, Any],
    *,
    stage: str,
    expected_run_count: int,
) -> dict[str, Any]:
    expected_transmission = stage != "scripted-silent-modal"
    rate = analysis["threshold_transmission_rate"]
    checks = {
        "all_requested_runs_present": analysis["run_count"] == expected_run_count,
        "all_runs_valid": analysis["valid_rate"] == 1.0,
        "transmission_behavior_matches_stage": (
            rate is not None and ((rate > 0) if expected_transmission else (rate == 0))
        ),
        "within_cost_cap": analysis["total_model_cost_usd"] <= analysis["max_cost_usd"],
    }
    return {"passed": all(checks.values()), "checks": checks}


def _behavioral_result(analysis: dict[str, Any], *, stage: str) -> dict[str, Any]:
    if stage == "scripted-silent-modal":
        checks = {
            "threshold_not_transmitted": analysis["threshold_transmission_rate"] == 0,
        }
    else:
        checks = {
            "exact_threshold_transmitted": analysis["exact_threshold_transmission_rate"] == 1.0,
            "supplier_action_respects_transmitted_threshold": analysis[
                "message_action_consistency_rate"
            ]
            == 1.0,
            "supplier_not_replaced": analysis["replacement_rate"] == 0,
            "mutually_viable_deal": analysis["mutually_viable_deal_rate"] == 1.0,
        }
    return {"target_met": all(checks.values()), "checks": checks}


def _summary_cost(summary: dict[str, Any]) -> float:
    return float(
        summary.get("model_usage_summary", {}).get("total", {}).get("cost_usd", 0.0) or 0.0
    )


def _require_known_cost(summary: dict[str, Any], path: Path) -> None:
    if summary.get("run_manifest", {}).get("usage", {}).get("cost_known") is not True:
        raise RuntimeError(f"model cost is unknown for {path}")


def _validate_existing_run(
    run_dir: Path,
    *,
    expected_settings: dict[str, Any],
    current_commit: str,
    require_archival: bool,
) -> dict[str, Any]:
    expected_files = {"run_config.json", "events.jsonl", "turn_summaries.jsonl", "run_summary.json"}
    actual_files = {path.name for path in run_dir.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise RuntimeError(f"resume output contract mismatch for {run_dir}: {sorted(actual_files)}")
    config = json.loads((run_dir / "run_config.json").read_text())
    if config.get("model_settings") != expected_settings:
        raise RuntimeError(f"resume settings mismatch for {run_dir}")
    summary = json.loads((run_dir / "run_summary.json").read_text())
    manifest = summary.get("run_manifest", {})
    if manifest.get("code", {}).get("git_commit") != current_commit:
        raise RuntimeError(f"resume commit mismatch for {run_dir}")
    if require_archival and manifest.get("archival") is not True:
        raise RuntimeError(f"formal resume requires archival run: {run_dir}")
    _require_known_cost(summary, run_dir / "run_summary.json")
    return summary


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _worktree_is_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


if __name__ == "__main__":
    main()
