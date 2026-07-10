from __future__ import annotations

from scripts.run_s01_response_curve import _compare_arms


def test_response_curve_arm_comparison_matches_cells_not_replicate_counts() -> None:
    baseline = {
        "run_count": 50,
        "replicates_per_cell": 5,
        "valid_rate": 0.92,
        "mean_attainable_regret_usd": 600_000,
        "replacement_rate": 0.5,
        "request_monotonicity_violations": 4,
    }
    intervention = {
        "run_count": 30,
        "replicates_per_cell": 3,
        "valid_rate": 1.0,
        "mean_attainable_regret_usd": 72_000,
        "replacement_rate": 0.0,
        "request_monotonicity_violations": 0,
        "intervention_id": "trusted_replacement_threshold_v1",
    }

    comparison = _compare_arms(baseline, intervention)

    assert comparison["baseline_cell_count"] == 10
    assert comparison["intervention_cell_count"] == 10
    assert comparison["mechanism_gate"]["checks"]["same_cell_count"]
    assert comparison["mechanism_gate"]["passed"]
