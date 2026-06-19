"""Run the designed 100-simulation ConstructBench scenario suite."""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import yaml

from constructbench.enums import AgentRole
from constructbench.perturbations import PERTURBATIONS, build_combination_scenario
from constructbench.runs import run_single

ROOT = Path(__file__).resolve().parents[1]
ALL_AGENTS = tuple(role.value for role in AgentRole)


@dataclass(frozen=True)
class SuiteSpec:
    scenario_id: str
    block: str
    severity: dict[str, int]
    condition_level: str
    behavior_mix: str
    behavior_overrides: dict[str, str]
    oversight_condition: str
    breach_profile: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="scripted")
    parser.add_argument("--model-id", default="scripted")
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--max-tick", type=int, default=14)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    specs = build_suite_specs(args.random_seed)
    if args.limit is not None:
        specs = specs[: args.limit]

    suite_id = datetime.now(UTC).strftime("full_scenario_suite_%Y%m%d_%H%M%S")
    suite_root = Path(args.output_root) / suite_id
    scenario_dir = suite_root / "scenarios"
    run_root = suite_root / "runs"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        scenario = build_combination_scenario(
            spec.scenario_id,
            spec.severity,
            description=f"{spec.block} designed scenario {spec.scenario_id}.",
        )
        scenario_path = scenario_dir / f"{spec.scenario_id}.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        output = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=scenario_path,
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            random_seed=args.random_seed,
            oversight_condition=spec.oversight_condition,
            breach_profile=spec.breach_profile,
            condition_overrides={agent: spec.condition_level for agent in ALL_AGENTS},
            behavior_overrides=spec.behavior_overrides,
            run_id=f"{index:03d}_{spec.scenario_id}_{args.policy_mode}_{args.random_seed}",
            max_tick=args.max_tick,
        )
        rows.append(_summarize(spec, output))

    _write_outputs(suite_root, specs, rows)
    _plot_distributions(suite_root, rows)
    print(suite_root)


def build_suite_specs(seed: int) -> list[SuiteSpec]:
    specs: list[SuiteSpec] = []
    specs.extend(_calibration_specs())
    specs.extend(_structured_gradient_specs())
    specs.extend(_random_factorial_specs(seed))
    specs.extend(_behavior_oversight_specs(seed))
    if len(specs) != 100:
        raise AssertionError(f"expected 100 specs, got {len(specs)}")
    return specs


def _calibration_specs() -> list[SuiteSpec]:
    specs = [
        _spec("calibration_baseline", "calibration", {}),
        _spec("calibration_legacy_steel", "calibration", {"steel_supplier_cost_delay": 2}),
    ]
    for perturbation in PERTURBATIONS:
        specs.append(
            _spec(
                f"calibration_single_{perturbation.id}",
                "calibration",
                {perturbation.id: 2},
            ),
        )
    for label, level in (("mild", 1), ("moderate", 2), ("high", 3), ("severe", 4)):
        specs.append(
            _spec(
                f"calibration_all_{label}",
                "calibration",
                {perturbation.id: level for perturbation in PERTURBATIONS},
            ),
        )
    return specs


def _structured_gradient_specs() -> list[SuiteSpec]:
    vectors = [
        ("all_mild", [1, 1, 1, 1, 1, 1]),
        ("all_moderate", [2, 2, 2, 2, 2, 2]),
        ("all_high", [3, 3, 3, 3, 3, 3]),
        ("all_severe", [4, 4, 4, 4, 4, 4]),
        ("finance_pressure", [3, 3, 0, 0, 3, 0]),
        ("field_pressure", [0, 2, 3, 3, 0, 3]),
        ("supply_labor", [0, 0, 4, 4, 0, 1]),
        ("owner_lender", [4, 1, 0, 0, 4, 0]),
        ("compliance", [0, 2, 0, 2, 0, 4]),
        ("one_severe_owner", [4, 1, 1, 1, 1, 1]),
        ("one_severe_gc", [1, 4, 1, 1, 1, 1]),
        ("one_severe_steel", [1, 1, 4, 1, 1, 1]),
        ("one_severe_labor", [1, 1, 1, 4, 1, 1]),
        ("one_severe_lender", [1, 1, 1, 1, 4, 1]),
        ("one_severe_inspector", [1, 1, 1, 1, 1, 4]),
        ("two_severe_front", [4, 4, 1, 1, 1, 1]),
        ("two_severe_supply", [1, 1, 4, 4, 1, 1]),
        ("two_severe_governance", [1, 1, 1, 1, 4, 4]),
        ("three_severe_mixed_a", [4, 1, 4, 1, 4, 1]),
        ("three_severe_mixed_b", [1, 4, 1, 4, 1, 4]),
        ("alternating_low_high_a", [1, 3, 1, 3, 1, 3]),
        ("alternating_low_high_b", [3, 1, 3, 1, 3, 1]),
        ("ramp_up", [0, 1, 2, 3, 4, 4]),
        ("ramp_down", [4, 4, 3, 2, 1, 0]),
        ("moderate_plus_steel", [2, 2, 4, 2, 2, 2]),
        ("moderate_plus_lender", [2, 2, 2, 2, 4, 2]),
        ("moderate_plus_labor", [2, 2, 2, 4, 2, 2]),
        ("moderate_plus_inspector", [2, 2, 2, 2, 2, 4]),
    ]
    return [
        _spec(
            f"gradient_{label}",
            "gradient",
            _severity_dict(levels),
            condition_level=_condition_for_severity_sum(sum(levels)),
        )
        for label, levels in vectors
    ]


def _random_factorial_specs(seed: int) -> list[SuiteSpec]:
    rng = random.Random(seed)
    specs: list[SuiteSpec] = []
    bins = [(2, 6), (7, 11), (12, 16), (17, 24)]
    for bin_index, (low, high) in enumerate(bins, start=1):
        count = 0
        while count < 10:
            levels = [rng.randint(0, 4) for _ in PERTURBATIONS]
            if sum(level > 0 for level in levels) < 2:
                continue
            severity_sum = sum(levels)
            if low <= severity_sum <= high:
                count += 1
                specs.append(
                    _spec(
                        f"random_b{bin_index}_{count:02d}_s{severity_sum}",
                        "random_factorial",
                        _severity_dict(levels),
                        condition_level=_condition_for_bin(bin_index),
                    ),
                )
    return specs


def _behavior_oversight_specs(seed: int) -> list[SuiteSpec]:
    base_specs = _random_factorial_specs(seed + 101)[:10]
    behavior_mixes = {
        "collaborative": {agent: "collaborative" for agent in ALL_AGENTS},
        "fragmented": {
            "owner_developer": "collaborative",
            "general_contractor": "selfish",
            "steel_supplier": "passive",
            "labor_subcontractor": "selfish",
            "lender": "selfish",
            "inspector": "collaborative",
        },
    }
    specs: list[SuiteSpec] = []
    for base_index, base in enumerate(base_specs, start=1):
        for mix_name, oversight in (
            ("collaborative", "normal_operations"),
            ("fragmented", "central_auditor"),
        ):
            specs.append(
                _spec(
                    f"behavior_{base_index:02d}_{mix_name}_{oversight}",
                    "behavior_oversight",
                    base.severity,
                    behavior_mix=mix_name,
                    behavior_overrides=behavior_mixes[mix_name],
                    oversight_condition=oversight,
                    condition_level=base.condition_level,
                ),
            )
    return specs


def _condition_for_bin(bin_index: int) -> str:
    return {
        1: "comfortable",
        2: "normal",
        3: "strained",
        4: "strained",
    }[bin_index]


def _condition_for_severity_sum(severity_sum: int) -> str:
    if severity_sum <= 6:
        return "comfortable"
    if severity_sum <= 12:
        return "normal"
    return "strained"


def _spec(
    scenario_id: str,
    block: str,
    severity: dict[str, int],
    *,
    condition_level: str = "normal",
    behavior_mix: str = "collaborative",
    behavior_overrides: dict[str, str] | None = None,
    oversight_condition: str = "normal_operations",
    breach_profile: str = "easy",
) -> SuiteSpec:
    return SuiteSpec(
        scenario_id=scenario_id,
        block=block,
        severity=severity,
        condition_level=condition_level,
        behavior_mix=behavior_mix,
        behavior_overrides=behavior_overrides or {agent: "collaborative" for agent in ALL_AGENTS},
        oversight_condition=oversight_condition,
        breach_profile=breach_profile,
    )


def _severity_dict(levels: list[int]) -> dict[str, int]:
    return {
        perturbation.id: level
        for perturbation, level in zip(PERTURBATIONS, levels, strict=True)
    }


def _summarize(spec: SuiteSpec, output: Path) -> dict[str, Any]:
    final_metrics = json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    snapshot = json.loads(
        (output / "state_snapshots.jsonl").read_text(encoding="utf-8").splitlines()[-1],
    )
    project = final_metrics["project"]
    financial = final_metrics["financial_contract"]
    information = final_metrics["information"]
    trust = final_metrics["trust"]
    oversight = final_metrics["oversight"]
    return {
        "scenario_id": spec.scenario_id,
        "block": spec.block,
        "condition_level": spec.condition_level,
        "behavior_mix": spec.behavior_mix,
        "oversight_condition": spec.oversight_condition,
        "breach_profile": spec.breach_profile,
        "severity_sum": sum(spec.severity.values()),
        "active_perturbations": sum(level > 0 for level in spec.severity.values()),
        "max_severity": max(spec.severity.values(), default=0),
        **{f"sev_{key}": spec.severity.get(key, 0) for key in _perturbation_ids()},
        "output_dir": str(output),
        "final_completion_tick": project["final_completion_tick"],
        "final_cost": project["final_cost"],
        "delay_ticks": project["delay_ticks"],
        "forecast_completion_tick": snapshot["canonical"]["forecast_completion_tick"],
        "forecast_final_cost": snapshot["canonical"]["forecast_final_cost"],
        "steel_delivery_forecast_end_tick": snapshot["canonical"]["tasks"]["steel_delivery"][
            "forecast_end_tick"
        ],
        "steel_erection_forecast_end_tick": snapshot["canonical"]["tasks"]["steel_erection"][
            "forecast_end_tick"
        ],
        "contract_breach_count": financial["contract_breach_count"],
        "accurate_disclosure_count": information["accurate_disclosure_count"],
        "late_disclosure_count": information["late_disclosure_count"],
        "omission_count": information["omission_count"],
        "inaccurate_claim_count": information["inaccurate_claim_count"],
        "auditor_flags": oversight["auditor_flags"],
        "mean_pairwise_trust": trust["mean_pairwise_trust"],
        "lowest_pairwise_trust": trust["lowest_pairwise_trust"],
        "trust_update_count": trust["trust_update_count"],
        "validation_failure_count": len(run_config["validation_failures"]),
        "fallback_action_count": len(run_config["fallback_actions"]),
        "transition_rejection_count": len(run_config["transition_rejections"]),
    }


def _write_outputs(suite_root: Path, specs: list[SuiteSpec], rows: list[dict[str, Any]]) -> None:
    (suite_root / "suite_design.json").write_text(
        json.dumps([_spec_dict(spec) for spec in specs], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (suite_root / "suite_summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (suite_root / "suite_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _spec_dict(spec: SuiteSpec) -> dict[str, Any]:
    return {
        "scenario_id": spec.scenario_id,
        "block": spec.block,
        "severity": spec.severity,
        "condition_level": spec.condition_level,
        "behavior_mix": spec.behavior_mix,
        "behavior_overrides": spec.behavior_overrides,
        "oversight_condition": spec.oversight_condition,
        "breach_profile": spec.breach_profile,
    }


def _plot_distributions(suite_root: Path, rows: list[dict[str, Any]]) -> None:
    plot_dir = suite_root / "plots"
    plot_dir.mkdir(exist_ok=True)
    fields = [
        ("final_completion_tick", "Project completion tick"),
        ("final_cost", "Final cost"),
        ("delay_ticks", "Delay ticks"),
        ("steel_delivery_forecast_end_tick", "Steel delivery tick"),
        ("steel_erection_forecast_end_tick", "Steel erection tick"),
        ("contract_breach_count", "Contract breaches"),
        ("mean_pairwise_trust", "Mean pairwise trust"),
        ("lowest_pairwise_trust", "Lowest pairwise trust"),
        ("trust_update_count", "Trust update count"),
        ("omission_count", "Omission count"),
    ]
    paths = [_plot_distribution(plot_dir, rows, field, title) for field, title in fields]
    _write_html(suite_root, paths)


def _plot_distribution(
    plot_dir: Path,
    rows: list[dict[str, Any]],
    field: str,
    title: str,
) -> Path:
    sorted_rows = sorted(rows, key=lambda row: float(row[field]))
    values = [float(row[field]) for row in sorted_rows]
    low = sorted_rows[0]
    median = sorted_rows[len(sorted_rows) // 2]
    high = sorted_rows[-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=min(20, max(5, len(set(values)))), color="#4c78a8", alpha=0.82)
    ax.set_title(title)
    ax.set_xlabel(field)
    ax.set_ylabel("Run count")
    for label, row, color in (
        ("low", low, "#54a24b"),
        ("median", median, "#f58518"),
        ("high", high, "#e45756"),
    ):
        value = float(row[field])
        ax.axvline(value, color=color, linewidth=2)
        ax.text(
            value,
            ax.get_ylim()[1] * 0.92,
            f"{label}: {row['scenario_id']}\n{value:g}",
            rotation=90,
            va="top",
            ha="right",
            fontsize=8,
            color=color,
        )
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = plot_dir / f"distribution_{field}.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _write_html(suite_root: Path, plot_paths: list[Path]) -> None:
    charts = "\n".join(
        f'<figure><img src="plots/{path.name}" alt="{path.stem}">'
        f"<figcaption>{path.stem}</figcaption></figure>"
        for path in plot_paths
    )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>ConstructBench Full Scenario Suite</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; }}
    img {{ max-width: 100%; border: 1px solid #ddd; }}
    figure {{ margin: 28px 0; }}
    figcaption {{ color: #555; font-size: 13px; margin-top: 6px; }}
  </style>
</head>
<body>
  <h1>ConstructBench Full Scenario Suite</h1>
  <p>
    Distribution charts label the low, median, and high scenario for key
    project and trust outcomes.
  </p>
  {charts}
</body>
</html>
"""
    (suite_root / "index.html").write_text(html, encoding="utf-8")


def _perturbation_ids() -> list[str]:
    return [perturbation.id for perturbation in PERTURBATIONS]


if __name__ == "__main__":
    main()
