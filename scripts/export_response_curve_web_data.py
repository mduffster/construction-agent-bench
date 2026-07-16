from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "response_curve"
WEB_DATA_PATH = ROOT / "web" / "src" / "game-data" / "s01_response_curve.json"
WEB_CHART_PATH = ROOT / "web" / "public" / "images" / "s01-response-curve.png"
SONNET_CONFIRMATION_ROOT = (
    ROOT / "outputs" / "s01_response_curve_sonnet_no_history_confirmation_v1_20260715"
)
SONNET_CONFIRMATION_REPORT = ROOT / "docs" / "s01_response_curve_sonnet_confirmation_results.md"


def main() -> None:
    manifest_path = EVIDENCE_DIR / "evidence_manifest.json"
    table_path = EVIDENCE_DIR / "response_curve_by_level.csv"
    chart_path = EVIDENCE_DIR / "response_curve.png"
    intervention_path = EVIDENCE_DIR / "intervention_summary.json"
    sonnet_confirmation_path = SONNET_CONFIRMATION_ROOT / "response_curve_analysis.json"
    sonnet_rows_path = SONNET_CONFIRMATION_ROOT / "response_curve_rows.jsonl"
    manifest = json.loads(manifest_path.read_text())
    interventions = json.loads(intervention_path.read_text())
    levels = _read_levels(table_path)
    sonnet_confirmation = json.loads(sonnet_confirmation_path.read_text())
    sonnet_rows = _read_jsonl(sonnet_rows_path)
    levels = _merge_sonnet_confirmation(levels, sonnet_rows)
    haiku = _public_sample(manifest["samples"]["haiku_confirmation"])
    sonnet = _public_sample(manifest["samples"]["sonnet_modal"])
    payload = {
        "schema_version": "constructsim.web_response_curve.v2",
        "experiment_id": manifest["experiment_id"],
        "title": "Does the supplier price its own replaceability?",
        "question": (
            "As a qualified replacement gets cheaper, does an AI steel supplier "
            "reduce the price relief it asks for?"
        ),
        "design": {
            "focal_role": "steel_supplier",
            "llm_respondent_count_per_run": 1,
            "deterministic_counterparty_count": 5,
            "replacement_cost_level_count": len(levels),
            "relationship_history_condition_count": 2,
            "deterministic_reference_trajectory_count": 130,
            "minimum_safe_request_usd": min(level["maximum_safe_relief_usd"] for level in levels),
            "maximum_safe_request_usd": max(level["maximum_safe_relief_usd"] for level in levels),
        },
        "haiku_confirmation": haiku,
        "sonnet_modal": sonnet,
        "sonnet_confirmation": _public_confirmation_sample(sonnet_confirmation),
        "mechanism_test": {
            "question": interventions["question"],
            "conditions": interventions["conditions"],
            "trusted_threshold_effect": interventions["trusted_threshold_effect"],
            "interpretation": interventions["interpretation"],
            "limitations": interventions["limitations"],
        },
        "haiku_request_counts": manifest["metrics"]["haiku_request_counts"],
        "levels": levels,
        "limitations": [
            "Five Haiku samples per treatment cell are preliminary evidence, not a precise behavioral distribution.",
            "Four Haiku runs were invalid and remain in the reported denominator.",
            "The Sonnet confirmation has three repeated no-history runs per price level.",
            "Both evaluated models are from one provider and there is not yet a human baseline.",
        ],
        "source": {
            "evidence_path": "docs/evidence/response_curve/evidence_package.md",
            "evidence_manifest_sha256": _sha256(manifest_path),
            "response_table_sha256": _sha256(table_path),
            "chart_sha256": _sha256(chart_path),
            "intervention_summary_sha256": _sha256(intervention_path),
            "sonnet_confirmation_report_path": "docs/s01_response_curve_sonnet_confirmation_results.md",
            "sonnet_confirmation_report_sha256": _sha256(SONNET_CONFIRMATION_REPORT),
            "sonnet_confirmation_analysis_sha256": _sha256(sonnet_confirmation_path),
            "sonnet_confirmation_rows_sha256": _sha256(sonnet_rows_path),
        },
    }
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    WEB_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    WEB_CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(chart_path, WEB_CHART_PATH)
    print(f"wrote {WEB_DATA_PATH.relative_to(ROOT)}")
    print(f"wrote {WEB_CHART_PATH.relative_to(ROOT)}")


def _public_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Keep operational spend metadata out of the public web artifact."""
    return {key: value for key, value in sample.items() if key != "model_cost_usd"}


def _public_confirmation_sample(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        key: sample[key]
        for key in (
            "model",
            "temperature",
            "run_count",
            "valid_run_count",
            "invalid_run_count",
            "valid_rate",
            "replacement_rate",
            "mean_attainable_regret_usd",
            "request_monotonicity_violations",
        )
    }


def _merge_sonnet_confirmation(
    levels: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows_by_level = {
        level["response_curve_level"]: [
            row for row in rows if row["response_curve_level"] == level["response_curve_level"]
        ]
        for level in levels
    }
    for level in levels:
        group = rows_by_level[level["response_curve_level"]]
        valid = [row for row in group if row["run_valid"]]
        level.update(
            {
                "sonnet_confirmation_valid_n": len(valid),
                "sonnet_confirmation_mean_request_usd": _mean(valid, "requested_relief_usd"),
                "sonnet_confirmation_replacement_rate": _rate(valid, "supplier_replaced"),
                "sonnet_confirmation_mean_attainable_regret_usd": _mean(
                    valid, "attainable_regret_usd"
                ),
            }
        )
    return levels


def _read_levels(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        {
            "response_curve_level": row["response_curve_level"],
            "replacement_cost_usd": int(row["replacement_cost_usd"]),
            "replacement_threshold_usd": int(row["replacement_threshold_usd"]),
            "maximum_safe_relief_usd": int(row["maximum_safe_relief_usd"]),
            "haiku_no_history_valid_n": int(row["haiku_no_history_valid_n"]),
            "haiku_no_history_mean_request_usd": float(row["haiku_no_history_mean_request_usd"]),
            "haiku_no_history_replacement_rate": float(row["haiku_no_history_replacement_rate"]),
            "haiku_no_history_mean_attainable_regret_usd": float(
                row["haiku_no_history_mean_attainable_regret_usd"]
            ),
            "haiku_history_valid_n": int(row["haiku_history_valid_n"]),
            "haiku_history_mean_request_usd": float(row["haiku_history_mean_request_usd"]),
            "haiku_history_replacement_rate": float(row["haiku_history_replacement_rate"]),
            "haiku_history_mean_attainable_regret_usd": float(
                row["haiku_history_mean_attainable_regret_usd"]
            ),
            "sonnet_no_history_valid_n": int(row["sonnet_no_history_valid_n"]),
            "sonnet_no_history_mean_request_usd": float(row["sonnet_no_history_mean_request_usd"]),
            "sonnet_no_history_replacement_rate": float(row["sonnet_no_history_replacement_rate"]),
            "sonnet_no_history_mean_attainable_regret_usd": float(
                row["sonnet_no_history_mean_attainable_regret_usd"]
            ),
        }
        for row in rows
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _mean(rows: list[dict[str, Any]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def _rate(rows: list[dict[str, Any]], field: str) -> float:
    return sum(row[field] is True for row in rows) / len(rows)


if __name__ == "__main__":
    main()
