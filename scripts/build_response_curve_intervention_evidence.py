from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the public-safe response-curve intervention summary."
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("outputs/s01_response_curve_haiku_confirmation_20260709"),
    )
    parser.add_argument(
        "--worksheet",
        type=Path,
        default=Path("outputs/s01_response_curve_threshold_scaffold_modal_20260709"),
    )
    parser.add_argument(
        "--trusted-modal",
        type=Path,
        default=Path("outputs/s01_response_curve_trusted_threshold_modal_20260709"),
    )
    parser.add_argument(
        "--trusted-confirmation",
        type=Path,
        default=Path("outputs/s01_response_curve_trusted_threshold_confirmation_20260709"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/response_curve/intervention_summary.json"),
    )
    args = parser.parse_args()

    baseline_path = args.baseline / "response_curve_analysis.json"
    worksheet_path = args.worksheet / "response_curve_analysis.json"
    worksheet_comparison_path = args.worksheet / "intervention_comparison.json"
    worksheet_audit_path = args.worksheet / "threshold_worksheet_audit.json"
    trusted_modal_path = args.trusted_modal / "response_curve_analysis.json"
    trusted_modal_comparison_path = args.trusted_modal / "intervention_comparison.json"
    trusted_confirmation_path = args.trusted_confirmation / "response_curve_analysis.json"
    trusted_confirmation_comparison_path = (
        args.trusted_confirmation / "intervention_comparison.json"
    )

    baseline = _load(baseline_path)
    worksheet = _load(worksheet_path)
    worksheet_comparison = _load(worksheet_comparison_path)
    worksheet_audit = _load(worksheet_audit_path)
    trusted_modal_comparison = _load(trusted_modal_comparison_path)
    trusted_confirmation = _load(trusted_confirmation_path)
    trusted_confirmation_comparison = _load(trusted_confirmation_comparison_path)

    payload = {
        "schema_version": "constructbench.response_curve_interventions.v1",
        "experiment_id": "s01_replaceability_response_curve_v1",
        "question": (
            "Does explicit calculation support repair the supplier's failure to "
            "price its own replaceability?"
        ),
        "conditions": [
            {
                **_condition("unassisted", "Unassisted", baseline),
                "evidence_tier": "five_per_cell_confirmation",
                "description": "The supplier receives the replacement facts but no decision aid.",
                "mechanism_gate_passed": None,
            },
            {
                **_condition("threshold_worksheet", "Formula worksheet", worksheet),
                "evidence_tier": "one_per_cell_modal_diagnostic",
                "description": (
                    "The prompt supplies the formula and requires an auditable calculation."
                ),
                "mechanism_gate_passed": worksheet_comparison["mechanism_gate"]["passed"],
                "correct_threshold_count": worksheet_audit["correct_threshold_count"],
                "parseable_calculation_count": worksheet_audit[
                    "valid_with_parseable_calculation_count"
                ],
                "stated_ceiling_override_count": worksheet_audit[
                    "explicit_stated_ceiling_override_count"
                ],
            },
            {
                **_condition(
                    "trusted_threshold",
                    "Trusted computed threshold",
                    trusted_confirmation,
                ),
                "evidence_tier": "three_per_cell_confirmation",
                "description": (
                    "The harness supplies the correct threshold as a fact, but not the action."
                ),
                "mechanism_gate_passed": trusted_confirmation_comparison["mechanism_gate"][
                    "passed"
                ],
            },
        ],
        "trusted_threshold_effect": {
            "mean_attainable_regret_reduction_fraction": trusted_confirmation_comparison[
                "mean_attainable_regret_reduction_fraction"
            ],
            "mean_attainable_regret_reduction_usd": trusted_confirmation_comparison[
                "mean_attainable_regret_reduction_usd"
            ],
            "modal_gate_passed": trusted_modal_comparison["mechanism_gate"]["passed"],
            "confirmation_gate_passed": trusted_confirmation_comparison["mechanism_gate"]["passed"],
            "residual_high_level_anchor_usd": 800_000,
        },
        "interpretation": (
            "A formula alone did not repair the response curve. Supplying the computed "
            "reservation value eliminated replacement and restored monotonicity, localizing "
            "much of the failure to fact binding and arithmetic. Persistent high-level "
            "under-asking indicates a separate anchoring effect."
        ),
        "limitations": [
            "The worksheet condition is a one-run-per-cell modal diagnostic.",
            "The trusted threshold is an oracle-information intervention, not unassisted reasoning.",
            "All model conditions use one provider and there is not yet a practitioner baseline.",
        ],
        "source_files": [
            _source(path)
            for path in [
                baseline_path,
                worksheet_path,
                worksheet_comparison_path,
                worksheet_audit_path,
                trusted_modal_path,
                trusted_modal_comparison_path,
                trusted_confirmation_path,
                trusted_confirmation_comparison_path,
            ]
        ],
    }
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")


def _condition(condition_id: str, label: str, analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "condition_id": condition_id,
        "label": label,
        "run_count": analysis["run_count"],
        "valid_run_count": analysis["valid_run_count"],
        "valid_rate": analysis["valid_rate"],
        "mean_attainable_regret_usd": analysis["mean_attainable_regret_usd"],
        "replacement_rate": analysis["replacement_rate"],
        "request_monotonicity_violations": analysis["request_monotonicity_violations"],
    }


def _source(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


if __name__ == "__main__":
    main()
