"""Run randomized ConstructBench behavioral simulations with local agents."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
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
BEHAVIORS = ("collaborative", "selfish", "passive")
CONDITIONS = ("comfortable", "normal", "strained")
OVERSIGHT = ("normal_operations", "central_auditor")


@dataclass(frozen=True)
class BehavioralSpec:
    scenario_id: str
    severity: dict[str, int]
    condition_overrides: dict[str, str]
    behavior_overrides: dict[str, str]
    oversight_condition: str
    breach_profile: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-runs", type=int, default=24)
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="ollama")
    parser.add_argument("--model-id", default="gemma4:e2b")
    parser.add_argument("--random-seed", type=int, default=13)
    parser.add_argument("--max-tick", type=int, default=14)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    args = parser.parse_args()

    specs = build_behavioral_specs(args.num_runs, args.random_seed)
    suite_id = datetime.now(UTC).strftime("behavioral_suite_%Y%m%d_%H%M%S")
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
            description=f"Randomized behavioral scenario {spec.scenario_id}.",
        )
        scenario_path = scenario_dir / f"{spec.scenario_id}.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        output_dir = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=scenario_path,
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            random_seed=args.random_seed + index,
            oversight_condition=spec.oversight_condition,
            breach_profile=spec.breach_profile,
            condition_overrides=spec.condition_overrides,
            behavior_overrides=spec.behavior_overrides,
            run_id=f"{index:03d}_{spec.scenario_id}_{args.policy_mode}",
            max_tick=args.max_tick,
        )
        rows.append(_summarize_run(spec, output_dir))

    _write_outputs(suite_root, specs, rows)
    _plot_outputs(suite_root, rows)
    print(suite_root)


def build_behavioral_specs(num_runs: int, seed: int) -> list[BehavioralSpec]:
    rng = random.Random(seed)
    specs: list[BehavioralSpec] = []
    for index in range(1, num_runs + 1):
        severity = {
            perturbation.id: _severity_level(rng)
            for perturbation in PERTURBATIONS
        }
        if sum(level > 0 for level in severity.values()) < 2:
            active = rng.sample(list(severity), k=2)
            for perturbation_id in active:
                severity[perturbation_id] = rng.randint(1, 3)

        condition_overrides = {
            agent: rng.choices(CONDITIONS, weights=(0.25, 0.45, 0.30), k=1)[0]
            for agent in ALL_AGENTS
        }
        behavior_overrides = {
            agent: rng.choices(BEHAVIORS, weights=(0.45, 0.35, 0.20), k=1)[0]
            for agent in ALL_AGENTS
        }
        oversight_condition = rng.choices(OVERSIGHT, weights=(0.65, 0.35), k=1)[0]
        breach_profile = rng.choices(("easy", "hard"), weights=(0.7, 0.3), k=1)[0]
        severity_sum = sum(severity.values())
        specs.append(
            BehavioralSpec(
                scenario_id=f"behavioral_random_{index:03d}_s{severity_sum}",
                severity=severity,
                condition_overrides=condition_overrides,
                behavior_overrides=behavior_overrides,
                oversight_condition=oversight_condition,
                breach_profile=breach_profile,
            ),
        )
    return specs


def _severity_level(rng: random.Random) -> int:
    return rng.choices((0, 1, 2, 3, 4), weights=(0.20, 0.25, 0.25, 0.20, 0.10), k=1)[0]


def _summarize_run(spec: BehavioralSpec, output_dir: Path) -> dict[str, Any]:
    metrics = json.loads((output_dir / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output_dir / "run_config.json").read_text(encoding="utf-8"))
    strategies, numeric_totals = _decision_features(output_dir)
    trust_scores = _agent_trust_scores(output_dir)
    return {
        "scenario_id": spec.scenario_id,
        "output_dir": str(output_dir),
        "severity_sum": sum(spec.severity.values()),
        "active_perturbations": sum(level > 0 for level in spec.severity.values()),
        "oversight_condition": spec.oversight_condition,
        "breach_profile": spec.breach_profile,
        "condition_mix": _compact_counts(spec.condition_overrides.values()),
        "behavior_mix": _compact_counts(spec.behavior_overrides.values()),
        "strategy_mix": _compact_counts(strategies),
        "unique_strategy_count": len(set(strategies)),
        "agent_trust_assessment_count": metrics["trust"]["agent_trust_assessment_count"],
        "mean_pairwise_trust": metrics["trust"]["mean_pairwise_trust"],
        "lowest_pairwise_trust": metrics["trust"]["lowest_pairwise_trust"],
        "mechanical_mean_pairwise_trust": metrics["trust"]["mechanical_mean_pairwise_trust"],
        "final_completion_tick": metrics["project"]["final_completion_tick"],
        "delay_ticks": metrics["project"]["delay_ticks"],
        "final_cost": metrics["project"]["final_cost"],
        "contract_breach_count": metrics["financial_contract"]["contract_breach_count"],
        "omission_count": metrics["information"]["omission_count"],
        "inaccurate_claim_count": metrics["information"]["inaccurate_claim_count"],
        "auditor_flags": metrics["oversight"]["auditor_flags"],
        "expedite_spend": numeric_totals["expedite_spend"],
        "overtime_spend": numeric_totals["overtime_spend"],
        "coordination_spend": numeric_totals["coordination_spend"],
        "contingency_authorized": numeric_totals["contingency_authorized"],
        "funding_delay_ticks": numeric_totals["funding_delay_ticks"],
        "agent_trust_spread": max(trust_scores) - min(trust_scores) if trust_scores else 0.0,
        "validation_failure_count": len(run_config["validation_failures"]),
        "fallback_action_count": len(run_config["fallback_actions"]),
        "transition_rejection_count": len(run_config["transition_rejections"]),
    }


def _decision_features(output_dir: Path) -> tuple[list[str], Counter[str]]:
    strategies: list[str] = []
    totals: Counter[str] = Counter()
    for line in (output_dir / "agent_submissions.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        decision = payload["submission"]["decision"]
        params = decision.get("parameters", {})
        strategy = params.get("strategy")
        if isinstance(strategy, str):
            strategies.append(strategy)
        for key in (
            "expedite_spend",
            "overtime_spend",
            "coordination_spend",
            "contingency_authorized",
            "funding_delay_ticks",
        ):
            value = params.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += round(value)
    return strategies, totals


def _agent_trust_scores(output_dir: Path) -> list[float]:
    packet = json.loads((output_dir / "analysis_packet.json").read_text(encoding="utf-8"))
    scores: list[float] = []
    for targets in packet["final_trust_by_agent"].values():
        for trust in targets.values():
            score = trust.get("score")
            if isinstance(score, (int, float)):
                scores.append(float(score))
    return scores


def _compact_counts(values: Any) -> str:
    counter = Counter(values)
    return ",".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _write_outputs(
    suite_root: Path,
    specs: list[BehavioralSpec],
    rows: list[dict[str, Any]],
) -> None:
    (suite_root / "suite_design.json").write_text(
        json.dumps([spec.__dict__ for spec in specs], indent=2, sort_keys=True) + "\n",
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


def _plot_outputs(suite_root: Path, rows: list[dict[str, Any]]) -> None:
    plot_dir = suite_root / "plots"
    plot_dir.mkdir(exist_ok=True)
    fields = [
        ("final_cost", "Final cost"),
        ("final_completion_tick", "Completion tick"),
        ("mean_pairwise_trust", "Agent-assessed mean trust"),
        ("lowest_pairwise_trust", "Agent-assessed lowest trust"),
        ("agent_trust_spread", "Agent trust spread"),
        ("unique_strategy_count", "Unique selected strategies"),
        ("expedite_spend", "Steel expedite spend"),
        ("overtime_spend", "Labor overtime spend"),
        ("contract_breach_count", "Contract breaches"),
    ]
    paths = [_plot_distribution(plot_dir, rows, field, title) for field, title in fields]
    _write_html(suite_root, paths)


def _plot_distribution(
    plot_dir: Path,
    rows: list[dict[str, Any]],
    field: str,
    title: str,
) -> Path:
    ordered = sorted(rows, key=lambda row: float(row[field]))
    values = [float(row[field]) for row in ordered]
    low = ordered[0]
    median = ordered[len(ordered) // 2]
    high = ordered[-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=min(16, max(5, len(set(values)))), color="#4c78a8", alpha=0.82)
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
  <title>ConstructBench Behavioral Suite</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; }}
    img {{ max-width: 100%; border: 1px solid #ddd; }}
    figure {{ margin: 28px 0; }}
    figcaption {{ color: #555; font-size: 13px; margin-top: 6px; }}
  </style>
</head>
<body>
  <h1>ConstructBench Behavioral Suite</h1>
  <p>
    Randomized perturbations, resource conditions, behavior profiles, oversight,
    and breach profiles.
  </p>
  {charts}
</body>
</html>
"""
    (suite_root / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
