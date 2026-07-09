from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.analysis import load_run_summaries
from constructbench.focal import S01_COMMERCIAL_NEUTRAL_POLICY_ID, build_focal_policies
from constructbench.models import (
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
    AnthropicModelAdapter,
    LLMPolicy,
)
from constructbench.response_curve import (
    RESPONSE_CURVE_EXPERIMENT_ID,
    analyze_live_summaries,
    response_curve_instance_ids,
    run_reference_grid,
    summarize_reference_grid,
)
from constructbench.runner import run_policy

STRONGER_MODEL_DEFAULT = "claude-sonnet-5"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the low-cost S01 replaceability response-curve experiment."
    )
    parser.add_argument(
        "--stage",
        choices=["references", "modal-pilot", "haiku-confirmation", "stronger-modal"],
        default="references",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--replicates-per-cell", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--repair-budget", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument(
        "--instance-ids",
        help="Optional comma-separated response-curve instance IDs for a diagnostic subset.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-model", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_response_curve_{args.stage}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    reference_rows = run_reference_grid()
    reference_summaries = summarize_reference_grid(reference_rows)
    _write_json(root / "reference_grid.json", reference_rows)
    _write_json(root / "reference_summary.json", reference_summaries)
    if args.stage == "references":
        print(f"wrote {root}")
        print(f"reference_runs={len(reference_rows)} invalid=0 model_cost_usd=0")
        return

    if not args.allow_live_model:
        raise SystemExit(f"{args.stage} requires --allow-live-model")

    defaults = _live_defaults(args.stage)
    model = args.model or defaults["model"]
    replicates = args.replicates_per_cell or defaults["replicates_per_cell"]
    temperature = (
        args.temperature if args.temperature is not None else defaults["temperature"]
    )
    max_cost_usd = (
        args.max_cost_usd if args.max_cost_usd is not None else defaults["max_cost_usd"]
    )

    raw_root = root / "raw_runs"
    raw_root.mkdir(parents=True, exist_ok=True)
    total_cost = 0.0
    instance_ids = (
        [value.strip() for value in args.instance_ids.split(",") if value.strip()]
        if args.instance_ids
        else response_curve_instance_ids()
    )
    unknown_ids = sorted(set(instance_ids) - set(response_curve_instance_ids()))
    if unknown_ids:
        raise ValueError(f"unknown response-curve instance IDs: {unknown_ids}")
    for instance_id in instance_ids:
        for replicate_index in range(replicates):
            run_dir = raw_root / f"{instance_id}_replicate_{replicate_index:02d}"
            summary_path = run_dir / "run_summary.json"
            if summary_path.exists():
                total_cost += _summary_cost(json.loads(summary_path.read_text()))
                continue
            if total_cost >= max_cost_usd:
                raise RuntimeError(
                    f"hard cost stop reached before {instance_id}: "
                    f"${total_cost:.4f} >= ${max_cost_usd:.4f}"
                )
            focal_policy = LLMPolicy(
                AnthropicModelAdapter(model=model, temperature=temperature),
                "steel_supplier",
                prompt_style="anthropic_structured",
            )
            result = run_policy(
                "S01",
                "normal",
                build_focal_policies(
                    "S01",
                    "steel_supplier",
                    focal_policy,
                    counterparty_policy_id=S01_COMMERCIAL_NEUTRAL_POLICY_ID,
                ),
                output_dir=run_dir,
                seed=replicate_index,
                scenario_instance_id=instance_id,
                repair_budget=args.repair_budget,
                model_settings={
                    "policy": "focal",
                    "provider": "anthropic",
                    "model": model,
                    "temperature": temperature,
                    "repair_budget": args.repair_budget,
                    "focal_agent_id": "steel_supplier",
                    "counterparty_policy_id": S01_COMMERCIAL_NEUTRAL_POLICY_ID,
                    "scenario_instance_id": instance_id,
                    "replicate_index": replicate_index,
                    "experiment_id": RESPONSE_CURVE_EXPERIMENT_ID,
                    "experiment_stage": args.stage,
                },
            )
            cost = float(
                result.final_state.histories.get("model_usage", [{}])[-1].get(
                    "estimated_cost_usd", 0.0
                )
                if result.final_state.histories.get("model_usage")
                else 0.0
            )
            # The durable summary is authoritative; this fallback keeps the
            # progress line useful across adapter telemetry versions.
            durable = json.loads(summary_path.read_text())
            cost = _summary_cost(durable) or cost
            total_cost += cost
            print(
                f"{run_dir.name}: valid={result.final_state.run_valid} "
                f"status={result.final_state.terminal_status} cost=${cost:.4f} "
                f"cumulative=${total_cost:.4f}"
            )
            if total_cost > max_cost_usd:
                raise RuntimeError(
                    f"hard cost stop exceeded after {run_dir.name}: "
                    f"${total_cost:.4f} > ${max_cost_usd:.4f}"
                )

    loaded = load_run_summaries([raw_root])
    analysis = analyze_live_summaries(
        [summary for summary, _ in loaded],
        reference_summaries=reference_summaries,
    )
    analysis["stage"] = args.stage
    analysis["model"] = model
    analysis["temperature"] = temperature
    analysis["replicates_per_cell"] = replicates
    analysis["repair_budget"] = args.repair_budget
    analysis["max_cost_usd"] = max_cost_usd
    analysis["instance_ids"] = instance_ids
    analysis["modal_gate"] = _modal_gate(analysis) if args.stage == "modal-pilot" else None
    rows = analysis.pop("rows")
    _write_json(root / "response_curve_analysis.json", analysis)
    _write_jsonl(root / "response_curve_rows.jsonl", rows)
    print(f"wrote {root}")
    print(
        f"runs={analysis['run_count']} valid={analysis['valid_run_count']} "
        f"cost=${analysis['total_model_cost_usd']:.4f} "
        f"violations={analysis['request_monotonicity_violations']}"
    )
    if analysis["modal_gate"] is not None:
        print(f"go_for_confirmation={analysis['modal_gate']['passed']}")


def _live_defaults(stage: str) -> dict[str, Any]:
    if stage == "modal-pilot":
        return {
            "model": DEFAULT_ANTHROPIC_HAIKU_MODEL,
            "replicates_per_cell": 1,
            "temperature": 0.0,
            "max_cost_usd": 1.0,
        }
    if stage == "haiku-confirmation":
        return {
            "model": DEFAULT_ANTHROPIC_HAIKU_MODEL,
            "replicates_per_cell": 5,
            "temperature": 1.0,
            "max_cost_usd": 4.0,
        }
    return {
        "model": STRONGER_MODEL_DEFAULT,
        "replicates_per_cell": 1,
        "temperature": 0.0,
        "max_cost_usd": 4.0,
    }


def _modal_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    rows_path_signal = bool(
        analysis["mean_attainable_regret_usd"]
        and analysis["mean_attainable_regret_usd"] > 0
    )
    checks = {
        "valid_rate_at_least_90_percent": analysis["valid_rate"] >= 0.9,
        "all_ten_cells_present": analysis["run_count"] == 10,
        "informative_response_or_consequential_failure": (
            analysis["request_monotonicity_violations"] > 0 or rows_path_signal
        ),
        "within_cost_cap": analysis["total_model_cost_usd"]
        <= analysis["max_cost_usd"],
    }
    return {"passed": all(checks.values()), "checks": checks}


def _summary_cost(summary: dict[str, Any]) -> float:
    return float(
        summary.get("model_usage_summary", {})
        .get("total", {})
        .get("cost_usd", 0.0)
        or 0.0
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


if __name__ == "__main__":
    main()
