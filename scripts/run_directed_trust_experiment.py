"""Run the directed dimensional trust diagnostic experiment."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import yaml

from constructbench.perturbations import PERTURBATIONS, build_combination_scenario
from constructbench.runs import run_single

ROOT = Path(__file__).resolve().parents[1]
MODES = ("scalar_baseline", "structured_dimensional")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-scenarios", type=int, default=5)
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="scripted")
    parser.add_argument("--model-id", default="scripted")
    parser.add_argument("--random-seed", type=int, default=31)
    parser.add_argument("--max-tick", type=int, default=14)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    args = parser.parse_args()

    suite_id = datetime.now(UTC).strftime("directed_trust_%Y%m%d_%H%M%S")
    suite_root = Path(args.output_root) / suite_id
    scenario_dir = suite_root / "scenarios"
    run_root = suite_root / "runs"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    severities = _severity_schedule(args.num_scenarios)
    for scenario_index, severity in enumerate(severities, start=1):
        scenario_id = f"directed_steel_level_{severity}_{scenario_index:02d}"
        scenario = _steel_scenario(scenario_id, severity)
        scenario_path = scenario_dir / f"{scenario_id}.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")

        for mode in MODES:
            run_id = f"{scenario_index:02d}_{scenario_id}_{mode}_{args.policy_mode}"
            output_dir = run_single(
                project_config_path=ROOT / "configs" / "project_baseline.yaml",
                agent_config_dir=ROOT / "configs" / "agents",
                scenario_config_path=scenario_path,
                output_root=run_root,
                policy_mode=args.policy_mode,
                model_id=args.model_id,
                random_seed=args.random_seed + scenario_index,
                oversight_condition="normal_operations",
                breach_profile="easy",
                assessment_update_mode=mode,
                run_id=run_id,
                max_tick=args.max_tick,
            )
            rows.append(_summarize_run(output_dir, scenario_id, severity, mode))

    _write_outputs(suite_root, rows)
    _plot_dyad_updates(suite_root, rows)
    _plot_scalar_supplement(suite_root, rows)
    print(suite_root)


def _severity_schedule(num_scenarios: int) -> list[int]:
    base = [1, 2, 3, 4, 2]
    if num_scenarios <= len(base):
        return base[:num_scenarios]
    return [base[index % len(base)] for index in range(num_scenarios)]


def _steel_scenario(scenario_id: str, severity: int) -> dict[str, Any]:
    scenario = build_combination_scenario(
        scenario_id,
        {"steel_supplier_cost_delay": severity},
        description=(
            "Directed trust diagnostic: steel supplier risk disclosure reaches "
            "the general contractor under matched update modes."
        ),
    )
    steel = next(
        perturbation
        for perturbation in PERTURBATIONS
        if perturbation.id == "steel_supplier_cost_delay"
    )
    data = steel.data_by_level[severity]
    delivery_tick = int(data["current_delivery_forecast"])
    scenario["scheduled_events"].append(
        {
            "event_type": "private_message",
            "private_message": {
                "tick": 9,
                "message_id": f"steel_supplier_disclosure_level_{severity}_tick_9",
                "sender": "steel_supplier",
                "recipients": ["general_contractor"],
                "summary": (
                    "Steel supplier disclosure: updated delivery forecast is "
                    f"tick {delivery_tick}; input cost pressure is material. "
                    "This is proactive disclosure of steel delivery risk."
                ),
                "linked_object_id": "steel_contract",
                "claims": [
                    {
                        "field": "forecast_end_tick",
                        "value": delivery_tick,
                        "unit": "tick",
                        "confidence": 0.75,
                    },
                ],
                "delay_ticks": 1,
            },
        },
    )
    if delivery_tick > 14:
        scenario["scheduled_events"].append(
            {
                "event_type": "public_ledger_entry",
                "public_ledger_entry": {
                    "tick": 14,
                    "entry_id": f"official_steel_delivery_failure_level_{severity}_tick_14",
                    "source": "system",
                    "entry_type": "milestone_status",
                    "linked_object_id": "steel_delivery",
                    "data": {
                        "summary": (
                            "Official milestone status: steel was not delivered by "
                            "the committed tick 14 date."
                        ),
                    },
                    "claims": [
                        {
                            "field": "forecast_end_tick",
                            "value": delivery_tick,
                            "unit": "tick",
                            "confidence": 1.0,
                        },
                    ],
                },
            },
        )
    scenario["max_tick"] = 14
    return scenario


def _summarize_run(
    output_dir: Path,
    scenario_id: str,
    severity: int,
    mode: str,
) -> dict[str, Any]:
    metrics = json.loads((output_dir / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output_dir / "run_config.json").read_text(encoding="utf-8"))
    updates = _expectation_updates(output_dir)
    gc_updates = [
        update
        for update in updates
        if update.get("observer") == "general_contractor"
        and update.get("target") == "steel_supplier"
    ]
    first_update = gc_updates[0] if gc_updates else {}
    commercial = first_update.get("commercial_response", {})
    previous = first_update.get("previous_assessment", {})
    posterior = first_update.get("updated_assessment", {})
    return {
        "scenario_id": scenario_id,
        "severity": severity,
        "mode": mode,
        "output_dir": str(output_dir),
        "validation_failure_count": len(run_config["validation_failures"]),
        "fallback_action_count": len(run_config["fallback_actions"]),
        "transition_rejection_count": len(run_config["transition_rejections"]),
        "expectation_update_count": len(gc_updates),
        "first_update_tick": first_update.get("tick"),
        "prior_delivery_reliability": previous.get("delivery_reliability"),
        "posterior_delivery_reliability": posterior.get("delivery_reliability"),
        "delivery_reliability_delta": first_update.get("delivery_reliability_delta"),
        "prior_reporting_integrity": previous.get("reporting_integrity"),
        "posterior_reporting_integrity": posterior.get("reporting_integrity"),
        "reporting_integrity_delta": first_update.get("reporting_integrity_delta"),
        "evidence_ids": ",".join(first_update.get("basis_ids", [])),
        "require_performance_bond": commercial.get("require_performance_bond"),
        "seek_alternate_supplier": commercial.get("seek_alternate_supplier"),
        "required_reporting_interval_ticks": commercial.get(
            "required_reporting_interval_ticks",
        ),
        "allow_advance_payment": commercial.get("allow_advance_payment"),
        "require_independent_verification": commercial.get(
            "require_independent_verification",
        ),
        "mean_scalar_trust": metrics["trust"]["mean_pairwise_trust"],
        "lowest_scalar_trust": metrics["trust"]["lowest_pairwise_trust"],
        "final_cost": metrics["project"]["final_cost"],
        "final_completion_tick": metrics["project"]["final_completion_tick"],
        "contract_breach_count": metrics["financial_contract"]["contract_breach_count"],
    }


def _expectation_updates(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "counterparty_expectation_updates.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_outputs(suite_root: Path, rows: list[dict[str, Any]]) -> None:
    (suite_root / "directed_trust_summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    csv_path = suite_root / "directed_trust_summary.csv"
    if not rows:
        return
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_dyad_updates(suite_root: Path, rows: list[dict[str, Any]]) -> None:
    structured = [row for row in rows if row["mode"] == "structured_dimensional"]
    if not structured:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    dimensions = (
        ("delivery_reliability", "Delivery Reliability"),
        ("reporting_integrity", "Reporting Integrity"),
    )
    for axis, (field, title) in zip(axes, dimensions, strict=True):
        for row in structured:
            prior = row.get(f"prior_{field}")
            posterior = row.get(f"posterior_{field}")
            if not isinstance(prior, (int, float)) or not isinstance(posterior, (int, float)):
                continue
            label = f"L{row['severity']} {row['scenario_id'][-2:]}"
            axis.plot([-1, 0], [prior, posterior], marker="o", linewidth=1.6, label=label)
        axis.axvline(0, color="0.25", linewidth=0.8, linestyle="--")
        axis.set_title(title)
        axis.set_xlabel("Ticks relative to GC evidence receipt")
        axis.set_ylim(0.0, 1.0)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("GC -> steel supplier probability")
    handles, labels = axes[1].get_legend_handles_labels()
    if handles:
        axes[1].legend(handles, labels, fontsize=7, loc="best")
    fig.suptitle("Directed Dimensional Updates After Steel Evidence")
    fig.tight_layout()
    fig.savefig(suite_root / "gc_steel_event_aligned_dimensions.png", dpi=160)
    plt.close(fig)


def _plot_scalar_supplement(suite_root: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    labels = [f"{row['severity']}-{row['mode'].replace('_', ' ')}" for row in rows]
    values = [row["mean_scalar_trust"] for row in rows]
    fig, axis = plt.subplots(figsize=(max(8, len(rows) * 0.55), 4))
    axis.bar(range(len(rows)), values, color="0.45")
    axis.set_xticks(range(len(rows)))
    axis.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axis.set_ylim(0.0, 1.0)
    axis.set_ylabel("Run mean scalar trust")
    axis.set_title("Supplemental Scalar Trust Summary")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(suite_root / "scalar_trust_supplement.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
