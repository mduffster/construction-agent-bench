from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the lean S01 response-curve evidence packet from frozen outputs."
    )
    parser.add_argument(
        "--modal",
        type=Path,
        default=Path("outputs/s01_response_curve_modal_pilot_20260709"),
    )
    parser.add_argument(
        "--haiku",
        type=Path,
        default=Path("outputs/s01_response_curve_haiku_confirmation_20260709"),
    )
    parser.add_argument(
        "--sonnet",
        type=Path,
        default=Path("outputs/s01_response_curve_sonnet_no_history_promptfix_20260709"),
    )
    parser.add_argument(
        "--interrupted-sonnet",
        type=Path,
        default=Path("outputs/s01_response_curve_sonnet_modal_20260709"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/evidence/response_curve"),
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    modal_analysis = _load_json(args.modal / "response_curve_analysis.json")
    haiku_analysis = _load_json(args.haiku / "response_curve_analysis.json")
    sonnet_analysis = _load_json(args.sonnet / "response_curve_analysis.json")
    references = _load_json(args.haiku / "reference_summary.json")
    haiku_rows = _load_jsonl(args.haiku / "response_curve_rows.jsonl")
    sonnet_rows = _load_jsonl(args.sonnet / "response_curve_rows.jsonl")
    interrupted_summaries = [
        _load_json(path)
        for path in sorted((args.interrupted_sonnet / "raw_runs").glob("*/run_summary.json"))
    ]

    table = _level_table(references, haiku_rows, sonnet_rows)
    _write_csv(output_dir / "response_curve_by_level.csv", table)
    _write_csv(output_dir / "haiku_confirmation_rows.csv", haiku_rows)
    _write_csv(output_dir / "sonnet_modal_rows.csv", sonnet_rows)
    _response_curve_figure(table, output_dir / "response_curve.png")
    _regret_figure(table, output_dir / "attainable_regret.png")

    interrupted_cost = sum(
        float(summary["model_usage_summary"]["total"]["cost_usd"])
        for summary in interrupted_summaries
    )
    recorded_cost = (
        float(modal_analysis["total_model_cost_usd"])
        + float(haiku_analysis["total_model_cost_usd"])
        + float(sonnet_analysis["total_model_cost_usd"])
        + interrupted_cost
    )
    valid_haiku = [row for row in haiku_rows if row["run_valid"]]
    valid_sonnet = [row for row in sonnet_rows if row["run_valid"]]
    request_counts = Counter(int(row["requested_relief_usd"]) for row in valid_haiku)
    haiku_no_history = [
        row
        for row in valid_haiku
        if row["relationship_history_condition"]
        == "no_prior_shared_project_history"
    ]
    metrics = {
        "recorded_cost_usd": round(recorded_cost, 6),
        "interrupted_probe_cost_usd": round(interrupted_cost, 6),
        "haiku_request_counts": dict(sorted(request_counts.items())),
        "haiku_no_history_mean_regret_usd": _mean(
            row["attainable_regret_usd"] for row in haiku_no_history
        ),
        "sonnet_mean_regret_usd": _mean(
            row["attainable_regret_usd"] for row in valid_sonnet
        ),
        "haiku_repair_attempt_count": sum(
            int(row["repair_attempt_count"]) for row in haiku_rows
        ),
        "sonnet_repair_attempt_count": sum(
            int(row["repair_attempt_count"]) for row in sonnet_rows
        ),
    }
    report = _report_markdown(
        modal_analysis=modal_analysis,
        haiku_analysis=haiku_analysis,
        sonnet_analysis=sonnet_analysis,
        table=table,
        metrics=metrics,
    )
    (output_dir / "evidence_package.md").write_text(report)

    source_files = [
        args.modal / "response_curve_analysis.json",
        args.modal / "response_curve_rows.jsonl",
        args.haiku / "response_curve_analysis.json",
        args.haiku / "response_curve_rows.jsonl",
        args.haiku / "reference_summary.json",
        args.sonnet / "response_curve_analysis.json",
        args.sonnet / "response_curve_rows.jsonl",
        *sorted((args.interrupted_sonnet / "raw_runs").glob("*/run_summary.json")),
    ]
    manifest = {
        "schema_version": "constructbench.response_curve_evidence.v1",
        "experiment_id": "s01_replaceability_response_curve_v1",
        "source_files": [
            {"path": str(path), "sha256": _sha256(path)} for path in source_files
        ],
        "generated_files": [
            "evidence_package.md",
            "response_curve_by_level.csv",
            "haiku_confirmation_rows.csv",
            "sonnet_modal_rows.csv",
            "response_curve.png",
            "attainable_regret.png",
        ],
        "metrics": metrics,
        "samples": {
            "haiku_confirmation": {
                "model": haiku_analysis["model"],
                "temperature": haiku_analysis["temperature"],
                "run_count": haiku_analysis["run_count"],
                "valid_run_count": haiku_analysis["valid_run_count"],
                "invalid_run_count": haiku_analysis["invalid_run_count"],
                "valid_rate": haiku_analysis["valid_rate"],
                "replacement_rate": haiku_analysis["replacement_rate"],
                "mean_attainable_regret_usd": haiku_analysis[
                    "mean_attainable_regret_usd"
                ],
                "request_monotonicity_violations": haiku_analysis[
                    "request_monotonicity_violations"
                ],
                "model_cost_usd": haiku_analysis["total_model_cost_usd"],
            },
            "sonnet_modal": {
                "model": sonnet_analysis["model"],
                "temperature": sonnet_analysis["temperature"],
                "run_count": sonnet_analysis["run_count"],
                "valid_run_count": sonnet_analysis["valid_run_count"],
                "invalid_run_count": sonnet_analysis["invalid_run_count"],
                "valid_rate": sonnet_analysis["valid_rate"],
                "replacement_rate": sonnet_analysis["replacement_rate"],
                "mean_attainable_regret_usd": sonnet_analysis[
                    "mean_attainable_regret_usd"
                ],
                "request_monotonicity_violations": sonnet_analysis[
                    "request_monotonicity_violations"
                ],
                "model_cost_usd": sonnet_analysis["total_model_cost_usd"],
            },
        },
        "limitations": {
            "interrupted_request_unpriced": True,
            "note": (
                "Recorded cost excludes any provider charge for the Sonnet request "
                "interrupted before a durable run summary was written."
            ),
        },
    }
    (output_dir / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(f"wrote {output_dir}")
    print(f"recorded_model_cost_usd=${recorded_cost:.4f}")


def _level_table(
    references: list[dict[str, Any]],
    haiku_rows: list[dict[str, Any]],
    sonnet_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    no_history_references = {
        row["response_curve_level"]: row
        for row in references
        if row["relationship_history_condition"]
        == "no_prior_shared_project_history"
    }
    table: list[dict[str, Any]] = []
    for level in ["R1", "R2", "R3", "R4", "R5"]:
        reference = no_history_references[level]
        no_history = _group(haiku_rows, level, "no_prior_shared_project_history")
        history = _group(haiku_rows, level, "prior_success_with_remediated_issue")
        sonnet = _group(sonnet_rows, level, "no_prior_shared_project_history")
        table.append(
            {
                "response_curve_level": level,
                "replacement_cost_usd": reference["replacement_cost_usd"],
                "replacement_threshold_usd": reference[
                    "replacement_threshold_usd"
                ],
                "maximum_safe_relief_usd": reference["maximum_safe_relief_usd"],
                **_group_metrics("haiku_no_history", no_history),
                **_group_metrics("haiku_history", history),
                **_group_metrics("sonnet_no_history", sonnet),
            }
        )
    return table


def _group(
    rows: list[dict[str, Any]],
    level: str,
    history: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["run_valid"]
        and row["response_curve_level"] == level
        and row["relationship_history_condition"] == history
    ]


def _group_metrics(prefix: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        f"{prefix}_valid_n": len(rows),
        f"{prefix}_mean_request_usd": _mean(
            row["requested_relief_usd"] for row in rows
        ),
        f"{prefix}_replacement_rate": (
            sum(1 for row in rows if row["supplier_replaced"]) / len(rows)
            if rows
            else None
        ),
        f"{prefix}_mean_attainable_regret_usd": _mean(
            row["attainable_regret_usd"] for row in rows
        ),
    }


def _response_curve_figure(rows: list[dict[str, Any]], path: Path) -> None:
    x = [int(row["replacement_cost_usd"]) / 1_000_000 for row in rows]
    fig, axis = plt.subplots(figsize=(8, 4.8))
    axis.plot(
        x,
        [int(row["maximum_safe_relief_usd"]) / 1_000_000 for row in rows],
        marker="o",
        linewidth=2.5,
        color="#222222",
        label="Best-response safe request",
    )
    axis.plot(
        x,
        [float(row["haiku_no_history_mean_request_usd"]) / 1_000_000 for row in rows],
        marker="o",
        label="Haiku: no history",
    )
    axis.plot(
        x,
        [float(row["haiku_history_mean_request_usd"]) / 1_000_000 for row in rows],
        marker="s",
        label="Haiku: verified history",
    )
    axis.plot(
        x,
        [float(row["sonnet_no_history_mean_request_usd"]) / 1_000_000 for row in rows],
        marker="^",
        label="Sonnet: no history (modal)",
    )
    axis.set_xlabel("Replacement source premium ($M)")
    axis.set_ylabel("Supplier relief request ($M)")
    axis.set_title("Supplier requests do not track the replaceability frontier")
    axis.set_ylim(0, 1.3)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _regret_figure(rows: list[dict[str, Any]], path: Path) -> None:
    labels = [str(row["response_curve_level"]) for row in rows]
    x = list(range(len(labels)))
    width = 0.26
    fig, axis = plt.subplots(figsize=(8, 4.8))
    axis.bar(
        [value - width for value in x],
        [
            float(row["haiku_no_history_mean_attainable_regret_usd"]) / 1_000_000
            for row in rows
        ],
        width,
        label="Haiku: no history",
    )
    axis.bar(
        x,
        [
            float(row["haiku_history_mean_attainable_regret_usd"]) / 1_000_000
            for row in rows
        ],
        width,
        label="Haiku: verified history",
    )
    axis.bar(
        [value + width for value in x],
        [
            float(row["sonnet_no_history_mean_attainable_regret_usd"]) / 1_000_000
            for row in rows
        ],
        width,
        label="Sonnet: no history (modal)",
    )
    axis.set_xticks(x, labels)
    axis.set_xlabel("Response-curve level (replacement becomes more expensive)")
    axis.set_ylabel("Mean attainable regret ($M)")
    axis.set_title("Bargaining errors create avoidable private losses")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _report_markdown(
    *,
    modal_analysis: dict[str, Any],
    haiku_analysis: dict[str, Any],
    sonnet_analysis: dict[str, Any],
    table: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str:
    request_counts = metrics["haiku_request_counts"]
    lines = [
        "# S01 Replaceability Response-Curve Evidence",
        "",
        "*Preliminary low-cost evidence; generated from replayable run outputs.*",
        "",
        "## Question",
        "",
        "Does an LLM steel supplier reduce its relief demand as a known, qualified replacement becomes cheaper? One LLM controls the supplier; all counterparties are deterministic and use bounded commercial cooperation.",
        "",
        "## Design",
        "",
        "The supplier's private shock and project state are fixed. Five replacement premiums (`R1`-`R5`) are crossed with no prior history versus verified successful history. The safe best-response request rises from $200,000 to $1,200,000. All 130 deterministic reference trajectories were valid and the reference oracle had zero monotonicity violations.",
        "",
        "## Main result",
        "",
        f"In the temperature-1 Haiku confirmation, {haiku_analysis['valid_run_count']}/{haiku_analysis['run_count']} runs were valid ({haiku_analysis['valid_rate']:.0%}). Among valid runs, Haiku requested $800,000 in {request_counts.get(800000, 0)} cases and $600,000 in {request_counts.get(600000, 0)} cases even though the safe frontier moved by $1,000,000. It was replaced in {haiku_analysis['replacement_rate']:.0%} of valid runs, made {haiku_analysis['request_monotonicity_violations']} monotonicity violations across the two mean response curves, and left an average ${haiku_analysis['mean_attainable_regret_usd']:,.0f} in attainable supplier payoff unrealized.",
        "",
        f"The five-cell Sonnet modal probe did not separate positively: all five runs were valid after prompt clarification, but Sonnet was replaced in {sonnet_analysis['replacement_rate']:.0%}, made {sonnet_analysis['request_monotonicity_violations']} monotonicity violation, and averaged ${sonnet_analysis['mean_attainable_regret_usd']:,.0f} attainable regret. This is a small diagnostic comparison, not a model-ranking claim.",
        "",
        "![Supplier request response curve](response_curve.png)",
        "",
        "![Attainable regret by curve level](attainable_regret.png)",
        "",
        "## Outcomes by level",
        "",
        "| Level | Safe request | Haiku no-history request | Haiku history request | Sonnet request |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in table:
        lines.append(
            "| "
            f"{row['response_curve_level']} | "
            f"${row['maximum_safe_relief_usd']:,.0f} | "
            f"${row['haiku_no_history_mean_request_usd']:,.0f} | "
            f"${row['haiku_history_mean_request_usd']:,.0f} | "
            f"${row['sonnet_no_history_mean_request_usd']:,.0f} |"
        )
    lines.extend(
        [
            "",
            "## Validity and cost",
            "",
            f"- Haiku modal pilot: {modal_analysis['valid_run_count']}/{modal_analysis['run_count']} valid; ${modal_analysis['total_model_cost_usd']:.3f}.",
            f"- Haiku confirmation: {haiku_analysis['valid_run_count']}/{haiku_analysis['run_count']} valid; {metrics['haiku_repair_attempt_count']} repair attempts; ${haiku_analysis['total_model_cost_usd']:.3f}.",
            f"- Focused Sonnet modal: {sonnet_analysis['valid_run_count']}/{sonnet_analysis['run_count']} valid; {metrics['sonnet_repair_attempt_count']} repair attempts; ${sonnet_analysis['total_model_cost_usd']:.3f}.",
            f"- Recorded spend including the stopped two-run Sonnet probe: **${metrics['recorded_cost_usd']:.3f}**. A request interrupted before durable telemetry may add a small unrecorded provider charge.",
            "",
            "## Interpretation",
            "",
            "The agents recognize a legitimate cost shock but largely anchor on a fixed documented-relief amount instead of computing the counterparty's reservation value. Verified history changes the selected amount occasionally, but it does not produce a coherent response to replacement economics. Project completion often remains intact because replacement protects the coalition, so the capability failure appears mainly as avoidable private loss to the focal firm.",
            "",
            "## Limitations",
            "",
            "- Five stochastic Haiku samples per cell are a pilot, not a precise behavioral distribution.",
            "- Four Haiku confirmation runs were invalid and remain in the unconditional validity denominator.",
            "- Repairs are an intervention; repaired and unrepaired behavior should be separated in any larger study.",
            "- Sonnet has one modal run per no-history level and required a schema-prompt clarification after an empty-recipient failure.",
            "- Both evaluated models are from one provider; there is no human or construction-practitioner baseline yet.",
            "- Counterparties are deterministic by design, so the result measures focal-agent comparative statics rather than adaptive multi-agent equilibrium behavior.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "uv run python scripts/run_s01_response_curve.py --stage references",
            "uv run python scripts/run_s01_response_curve.py --stage modal-pilot --allow-live-model",
            "uv run python scripts/run_s01_response_curve.py --stage haiku-confirmation --allow-live-model",
            "uv run python scripts/build_response_curve_evidence.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: Any) -> float | None:
    concrete = [float(value) for value in values if value is not None]
    return sum(concrete) / len(concrete) if concrete else None


if __name__ == "__main__":
    main()
