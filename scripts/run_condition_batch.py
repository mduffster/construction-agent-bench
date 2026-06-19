"""Run comfortable/normal/strained initial-condition comparisons."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from constructbench.runs import run_single

ROOT = Path(__file__).resolve().parents[1]
AGENTS = (
    "owner_developer",
    "general_contractor",
    "steel_supplier",
    "labor_subcontractor",
    "lender",
    "inspector",
)
LEVELS = ("comfortable", "normal", "strained")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="scripted")
    parser.add_argument("--model-id", default="scripted")
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--max-tick", type=int, default=9)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    parser.add_argument("--breach-profile", choices=["easy", "hard"], default="easy")
    args = parser.parse_args()

    batch_id = datetime.now(UTC).strftime("condition_batch_%Y%m%d_%H%M%S")
    batch_dir = Path(args.output_root) / batch_id
    run_root = batch_dir / "runs"
    rows: list[dict[str, Any]] = []

    for level in LEVELS:
        output = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=ROOT / "configs" / "scenarios" / "steel_shock.yaml",
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            random_seed=args.random_seed,
            oversight_condition="normal_operations",
            breach_profile=args.breach_profile,
            condition_overrides={agent: level for agent in AGENTS},
            run_id=f"run_initial_conditions_{level}_{args.policy_mode}_{args.random_seed}",
            max_tick=args.max_tick,
        )
        rows.append(_summary_row(level, output))

    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "condition_summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (batch_dir / "condition_summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(batch_dir)


def _summary_row(level: str, output: Path) -> dict[str, Any]:
    metrics = json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))
    final_snapshot = _last_jsonl(output / "state_snapshots.jsonl")
    canonical = final_snapshot["canonical"]
    tasks = canonical["tasks"]
    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    return {
        "condition_level": level,
        "run_dir": str(output),
        "forecast_completion_tick": canonical["forecast_completion_tick"],
        "forecast_final_cost": canonical["forecast_final_cost"],
        "steel_delivery_forecast_tick": tasks["steel_delivery"]["forecast_end_tick"],
        "steel_delivery_forecast_cost": tasks["steel_delivery"]["forecast_cost"],
        "steel_erection_forecast_tick": tasks["steel_erection"]["forecast_end_tick"],
        "validation_failures": len(run_config["validation_failures"]),
        "fallback_actions": len(run_config["fallback_actions"]),
        "transition_rejections": len(run_config["transition_rejections"]),
        "project_delay_ticks": metrics["project"]["delay_ticks"],
        "cost_overrun_vs_budget": metrics["project"]["cost_overrun_vs_approved_budget"],
        "cost_overrun_vs_baseline": metrics["project"]["cost_overrun_vs_baseline"],
    }


def _last_jsonl(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"empty JSONL file: {path}")
    return cast(dict[str, Any], json.loads(lines[-1]))


if __name__ == "__main__":
    main()
