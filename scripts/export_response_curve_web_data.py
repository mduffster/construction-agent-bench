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


def main() -> None:
    manifest_path = EVIDENCE_DIR / "evidence_manifest.json"
    table_path = EVIDENCE_DIR / "response_curve_by_level.csv"
    chart_path = EVIDENCE_DIR / "response_curve.png"
    intervention_path = EVIDENCE_DIR / "intervention_summary.json"
    manifest = json.loads(manifest_path.read_text())
    interventions = json.loads(intervention_path.read_text())
    levels = _read_levels(table_path)
    haiku = _public_sample(manifest["samples"]["haiku_confirmation"])
    sonnet = _public_sample(manifest["samples"]["sonnet_modal"])
    payload = {
        "schema_version": "constructsim.web_response_curve.v1",
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
            "The Sonnet comparison has one modal run per no-history level.",
            "Both evaluated models are from one provider and there is not yet a human baseline.",
        ],
        "source": {
            "evidence_path": "docs/evidence/response_curve/evidence_package.md",
            "evidence_manifest_sha256": _sha256(manifest_path),
            "response_table_sha256": _sha256(table_path),
            "chart_sha256": _sha256(chart_path),
            "intervention_summary_sha256": _sha256(intervention_path),
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


if __name__ == "__main__":
    main()
