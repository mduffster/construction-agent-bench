"""Generate matplotlib visualizations for ConstructBench batch outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
AGENT_ORDER = [
    "owner_developer",
    "general_contractor",
    "steel_supplier",
    "labor_subcontractor",
    "lender",
    "inspector",
]


@dataclass(frozen=True)
class RunSummary:
    batch_label: str
    scenario_id: str
    output_dir: Path
    metrics: dict[str, Any]
    batch_row: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dirs", nargs="+", help="One or more perturbation batch directories.")
    parser.add_argument(
        "--labels",
        default=None,
        help="Comma-separated labels matching batch_dirs.",
    )
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    batch_dirs = [Path(path).resolve() for path in args.batch_dirs]
    labels = _labels(args.labels, batch_dirs)
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir is not None
        else ROOT / "outputs" / f"visual_report_{'_vs_'.join(labels)}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = _load_runs(batch_dirs, labels)
    _write_flat_csv(output_dir, runs)
    chart_paths = [
        _plot_outcome_bars(output_dir, runs, "forecast_completion_tick", "Completion tick"),
        _plot_outcome_bars(output_dir, runs, "forecast_final_cost", "Final cost forecast"),
        _plot_outcome_bars(output_dir, runs, "contract_breach_count", "Contract breaches"),
        _plot_outcome_bars(output_dir, runs, "mean_pairwise_trust", "Mean pairwise trust"),
        _plot_stacked_safety_counts(output_dir, runs),
        _plot_decision_counts(output_dir, runs),
    ]
    chart_paths.extend(_plot_trust_heatmaps(output_dir, runs))
    chart_paths.extend(_plot_trust_update_networks(output_dir, runs))
    _write_html_report(output_dir, runs, [path for path in chart_paths if path is not None])
    print(output_dir)


def _labels(raw_labels: str | None, batch_dirs: list[Path]) -> list[str]:
    if raw_labels is not None:
        labels = [label.strip() for label in raw_labels.split(",") if label.strip()]
        if len(labels) != len(batch_dirs):
            raise ValueError("--labels must have the same number of entries as batch_dirs")
        return labels
    return [path.name.replace("perturbation_batch_", "") for path in batch_dirs]


def _load_runs(batch_dirs: list[Path], labels: list[str]) -> list[RunSummary]:
    runs: list[RunSummary] = []
    for batch_dir, label in zip(batch_dirs, labels, strict=True):
        rows = json.loads((batch_dir / "batch_summary.json").read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise TypeError(f"batch_summary.json must be a list: {batch_dir}")
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("batch summary rows must be objects")
            output_dir = Path(str(row["output_dir"]))
            metrics = json.loads((output_dir / "final_metrics.json").read_text(encoding="utf-8"))
            runs.append(
                RunSummary(
                    batch_label=label,
                    scenario_id=str(row["scenario_id"]),
                    output_dir=output_dir,
                    metrics=metrics,
                    batch_row=row,
                ),
            )
    return runs


def _write_flat_csv(output_dir: Path, runs: list[RunSummary]) -> None:
    rows = [_flat_row(run) for run in runs]
    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _flat_row(run: RunSummary) -> dict[str, Any]:
    project = run.metrics["project"]
    information = run.metrics["information"]
    oversight = run.metrics["oversight"]
    trust = run.metrics["trust"]
    financial = run.metrics["financial_contract"]
    return {
        "batch_label": run.batch_label,
        "scenario_id": run.scenario_id,
        "output_dir": str(run.output_dir),
        "final_completion_tick": project["final_completion_tick"],
        "final_cost": project["final_cost"],
        "delay_ticks": project["delay_ticks"],
        "contract_breach_count": financial["contract_breach_count"],
        "accurate_disclosure_count": information["accurate_disclosure_count"],
        "late_disclosure_count": information["late_disclosure_count"],
        "omission_count": information["omission_count"],
        "inaccurate_claim_count": information["inaccurate_claim_count"],
        "auditor_flags": oversight["auditor_flags"],
        "required_attestations_missed": oversight["required_attestations_missed"],
        "mean_pairwise_trust": trust["mean_pairwise_trust"],
        "lowest_pairwise_trust": trust["lowest_pairwise_trust"],
        "trust_update_count": trust["trust_update_count"],
    }


def _plot_outcome_bars(
    output_dir: Path,
    runs: list[RunSummary],
    field: str,
    title: str,
) -> Path:
    rows = _sorted_rows(runs)
    values = [_value_for_field(run, field) for run in rows]
    labels = [f"{run.batch_label}\n{_short_scenario(run.scenario_id)}" for run in rows]
    fig_width = max(12, len(rows) * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    colors = [_color_for_label(run.batch_label) for run in rows]
    ax.bar(range(len(rows)), values, color=colors)
    ax.set_title(title)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=70, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = output_dir / f"{field}.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_stacked_safety_counts(output_dir: Path, runs: list[RunSummary]) -> Path:
    rows = _sorted_rows(runs)
    labels = [f"{run.batch_label}\n{_short_scenario(run.scenario_id)}" for run in rows]
    fields = [
        ("accurate_disclosure_count", "accurate"),
        ("late_disclosure_count", "late"),
        ("omission_count", "omitted"),
        ("inaccurate_claim_count", "inaccurate"),
        ("auditor_flags", "audit flags"),
        ("contract_breach_count", "breaches"),
    ]
    bottoms = [0.0 for _ in rows]
    fig, ax = plt.subplots(figsize=(max(12, len(rows) * 0.65), 6))
    for index, (field, label) in enumerate(fields):
        values = [_value_for_field(run, field) for run in rows]
        ax.bar(range(len(rows)), values, bottom=bottoms, label=label, color=plt.cm.tab20(index))
        bottoms = [bottom + value for bottom, value in zip(bottoms, values, strict=True)]
    ax.set_title("Safety event counts")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=70, ha="right", fontsize=8)
    ax.legend(ncol=3, fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = output_dir / "safety_event_counts.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_decision_counts(output_dir: Path, runs: list[RunSummary]) -> Path:
    rows = _sorted_rows(runs)
    counts = [_decision_count(run) for run in rows]
    labels = [f"{run.batch_label}\n{_short_scenario(run.scenario_id)}" for run in rows]
    fig, ax = plt.subplots(figsize=(max(12, len(rows) * 0.65), 6))
    ax.bar(range(len(rows)), counts, color=[_color_for_label(run.batch_label) for run in rows])
    ax.set_title("Non-none agent decisions")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=70, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = output_dir / "decision_counts.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_trust_heatmaps(output_dir: Path, runs: list[RunSummary]) -> list[Path]:
    paths: list[Path] = []
    for run in runs:
        trust = _final_trust(run)
        if not trust:
            continue
        matrix: list[list[float]] = []
        for observer in AGENT_ORDER:
            matrix.append(
                [
                    1.0 if observer == target else trust.get(observer, {}).get(target, 0.75)
                    for target in AGENT_ORDER
                ],
            )
        fig, ax = plt.subplots(figsize=(7, 6))
        image = ax.imshow(matrix, vmin=0, vmax=1, cmap="viridis")
        ax.set_title(f"Trust matrix: {run.batch_label} / {_short_scenario(run.scenario_id)}")
        ax.set_xticks(range(len(AGENT_ORDER)))
        ax.set_yticks(range(len(AGENT_ORDER)))
        ax.set_xticklabels([_short_agent(agent) for agent in AGENT_ORDER], rotation=45, ha="right")
        ax.set_yticklabels([_short_agent(agent) for agent in AGENT_ORDER])
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        path = output_dir / f"trust_heatmap_{run.batch_label}_{run.scenario_id}.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    return paths


def _plot_trust_update_networks(output_dir: Path, runs: list[RunSummary]) -> list[Path]:
    paths: list[Path] = []
    for run in runs:
        updates = _trust_updates(run)
        if not updates:
            continue
        edge_weights: Counter[tuple[str, str]] = Counter()
        for update in updates:
            edge_weights[(str(update["observer"]), str(update["target"]))] += 1
        angles = {
            agent: 2 * 3.141592653589793 * index / len(AGENT_ORDER)
            for index, agent in enumerate(AGENT_ORDER)
        }
        positions = {
            agent: (
                0.5 + 0.38 * math.cos(angle),
                0.5 + 0.38 * math.sin(angle),
            )
            for agent, angle in angles.items()
        }
        fig, ax = plt.subplots(figsize=(6, 6))
        for agent, (x_pos, y_pos) in positions.items():
            ax.scatter([x_pos], [y_pos], s=850, color="#f2f2f2", edgecolor="#333333", zorder=3)
            ax.text(x_pos, y_pos, _short_agent(agent), ha="center", va="center", fontsize=8)
        for (observer, target), weight in edge_weights.items():
            x1, y1 = positions[observer]
            x2, y2 = positions[target]
            ax.annotate(
                "",
                xy=(x2, y2),
                xytext=(x1, y1),
                arrowprops={
                    "arrowstyle": "->",
                    "lw": 0.7 + weight * 0.45,
                    "alpha": 0.55,
                    "color": "#9b2d30",
                    "shrinkA": 20,
                    "shrinkB": 20,
                },
            )
        ax.set_title(
            f"Trust update network: {run.batch_label} / {_short_scenario(run.scenario_id)}",
        )
        ax.axis("off")
        fig.tight_layout()
        path = output_dir / f"trust_network_{run.batch_label}_{run.scenario_id}.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    return paths


def _write_html_report(output_dir: Path, runs: list[RunSummary], chart_paths: list[Path]) -> None:
    rows = [_flat_row(run) for run in _sorted_rows(runs)]
    table_rows = "\n".join(
        "<tr>"
        + "".join(f"<td>{row[key]}</td>" for key in rows[0])
        + "</tr>"
        for row in rows
    )
    header = "".join(f"<th>{key}</th>" for key in rows[0])
    charts = "\n".join(
        f'<figure><img src="{path.name}" alt="{path.stem}">'
        f"<figcaption>{path.stem}</figcaption></figure>"
        for path in chart_paths
    )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>ConstructBench Results Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; text-align: left; }}
    th {{ background: #f2f2f2; position: sticky; top: 0; }}
    img {{ max-width: 100%; border: 1px solid #ddd; }}
    figure {{ margin: 28px 0; }}
    figcaption {{ color: #555; font-size: 13px; margin-top: 6px; }}
  </style>
</head>
<body>
  <h1>ConstructBench Results Report</h1>
  <p>
    Generated from {len(runs)} runs. Charts emphasize outcomes, safety events,
    disclosure, oversight, and pairwise trust.
  </p>
  <h2>Summary Table</h2>
  <table><thead><tr>{header}</tr></thead><tbody>{table_rows}</tbody></table>
  <h2>Charts</h2>
  {charts}
</body>
</html>
"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def _sorted_rows(runs: list[RunSummary]) -> list[RunSummary]:
    return sorted(runs, key=lambda run: (run.scenario_id, run.batch_label))


def _value_for_field(run: RunSummary, field: str) -> float:
    flat = _flat_row(run)
    value = flat.get(field, run.batch_row.get(field))
    if value is None:
        return 0.0
    return float(value)


def _decision_count(run: RunSummary) -> int:
    path = run.output_dir / "agent_decision_reports.jsonl"
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["decision"]["type"] != "none"
    )


def _final_trust(run: RunSummary) -> dict[str, dict[str, float]]:
    packet = json.loads((run.output_dir / "analysis_packet.json").read_text(encoding="utf-8"))
    trust = packet.get("final_trust_by_agent", {})
    return {
        observer: {
            target: float(data["score"])
            for target, data in targets.items()
            if isinstance(data, dict) and "score" in data
        }
        for observer, targets in trust.items()
        if isinstance(targets, dict)
    }


def _trust_updates(run: RunSummary) -> list[dict[str, Any]]:
    path = run.output_dir / "trust_updates.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _short_scenario(scenario_id: str) -> str:
    return (
        scenario_id.replace("single_", "")
        .replace("combined_", "combo_")
        .replace("_", "\n")
    )


def _short_agent(agent_id: str) -> str:
    return {
        "owner_developer": "Owner",
        "general_contractor": "GC",
        "steel_supplier": "Steel",
        "labor_subcontractor": "Labor",
        "lender": "Lender",
        "inspector": "Inspect",
    }.get(agent_id, agent_id)


def _color_for_label(label: str) -> str:
    palette = ["#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756", "#72b7b2"]
    return palette[abs(hash(label)) % len(palette)]


if __name__ == "__main__":
    main()
