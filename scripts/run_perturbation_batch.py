"""Generate and run the 10 ConstructBench perturbation simulations."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from constructbench.perturbations import build_perturbation_scenarios
from constructbench.runs import run_single

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="ollama")
    parser.add_argument("--model-id", default="gemma4:e2b")
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--default-individual-level", type=int, default=2)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    parser.add_argument("--max-tick", type=int, default=14)
    parser.add_argument("--condition-level", choices=["comfortable", "normal", "strained"])
    parser.add_argument("--breach-profile", choices=["easy", "hard"], default="easy")
    args = parser.parse_args()

    condition_suffix = f"_{args.condition_level}" if args.condition_level else ""
    batch_id = datetime.now(UTC).strftime(f"perturbation_batch{condition_suffix}_%Y%m%d_%H%M%S")
    batch_root = Path(args.output_root) / batch_id
    scenario_dir = batch_root / "scenarios"
    run_root = batch_root / "runs"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    scenarios = build_perturbation_scenarios(args.default_individual_level)
    summary_rows: list[dict[str, Any]] = []

    for scenario_id, scenario in scenarios.items():
        scenario_path = scenario_dir / f"{scenario_id}.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        output = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=scenario_path,
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            random_seed=args.random_seed,
            oversight_condition="normal_operations",
            breach_profile=args.breach_profile,
            condition_overrides=_all_agent_overrides(args.condition_level),
            run_id=f"run_{scenario_id}_{args.policy_mode}_{args.random_seed}",
            max_tick=args.max_tick,
        )
        summary_rows.append(_summarize_run(scenario_id, output, args.condition_level or "default"))

    _write_summary(batch_root, summary_rows)
    print(batch_root)


def _summarize_run(scenario_id: str, output: Path, condition_level: str) -> dict[str, Any]:
    final_metrics = json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    final_snapshot = json.loads(
        (output / "state_snapshots.jsonl").read_text(encoding="utf-8").splitlines()[-1],
    )
    reports = [
        json.loads(line)
        for line in (output / "agent_decision_reports.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    non_none_reports = [
        report for report in reports if report["decision"]["type"] != "none"
    ]

    return {
        "scenario_id": scenario_id,
        "condition_level": condition_level,
        "output_dir": str(output),
        "forecast_completion_tick": final_snapshot["canonical"]["forecast_completion_tick"],
        "forecast_final_cost": final_snapshot["canonical"]["forecast_final_cost"],
        "steel_delivery_forecast_end_tick": final_snapshot["canonical"]["tasks"]["steel_delivery"][
            "forecast_end_tick"
        ],
        "steel_erection_forecast_end_tick": final_snapshot["canonical"]["tasks"]["steel_erection"][
            "forecast_end_tick"
        ],
        "inspection_count": len(final_snapshot["canonical"]["inspections"]),
        "public_update_count": final_metrics["information"]["public_update_count"],
        "private_event_count": final_metrics["information"]["private_event_count"],
        "contract_breach_count": final_metrics["financial_contract"]["contract_breach_count"],
        "auditor_flags": final_metrics["oversight"]["auditor_flags"],
        "mean_pairwise_trust": final_metrics["trust"]["mean_pairwise_trust"],
        "omission_count": final_metrics["information"]["omission_count"],
        "inaccurate_claim_count": final_metrics["information"]["inaccurate_claim_count"],
        "validation_failure_count": len(run_config["validation_failures"]),
        "fallback_action_count": len(run_config["fallback_actions"]),
        "transition_rejection_count": len(run_config["transition_rejections"]),
        "non_none_decision_count": len(non_none_reports),
        "primary_decisions": [
            {
                "tick": report["tick"],
                "agent_id": report["agent_id"],
                "decision": report["decision"],
                "observed_new_info": report["observed_new_info"],
                "rationale": report["rationale"],
                "decision_parameters_used": report["decision_parameters_used"],
                "transitions_applied": report["transitions_applied"],
            }
            for report in non_none_reports
        ],
    }


def _write_summary(batch_root: Path, rows: list[dict[str, Any]]) -> None:
    (batch_root / "batch_summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fieldnames = [
        "scenario_id",
        "condition_level",
        "output_dir",
        "forecast_completion_tick",
        "forecast_final_cost",
        "steel_delivery_forecast_end_tick",
        "steel_erection_forecast_end_tick",
        "inspection_count",
        "public_update_count",
        "private_event_count",
        "contract_breach_count",
        "auditor_flags",
        "mean_pairwise_trust",
        "omission_count",
        "inaccurate_claim_count",
        "validation_failure_count",
        "fallback_action_count",
        "transition_rejection_count",
        "non_none_decision_count",
    ]
    with (batch_root / "batch_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})


def _all_agent_overrides(value: str | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "owner_developer": value,
        "general_contractor": value,
        "steel_supplier": value,
        "labor_subcontractor": value,
        "lender": value,
        "inspector": value,
    }


if __name__ == "__main__":
    main()
