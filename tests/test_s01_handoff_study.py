from __future__ import annotations

import pytest

from constructbench.handoff_study import analyze_handoff_study


def _row(
    arm: str,
    level: str,
    *,
    success: bool,
    regret: int,
    repair_attempt_count: int = 0,
) -> dict:
    return {
        "handoff_condition": arm,
        "response_curve_level": level,
        "run_valid": True,
        "repair_attempt_count": repair_attempt_count,
        "gc_calculation_exact": success,
        "threshold_transmission_exact": success,
        "safe_action_relative_to_truth": success,
        "end_to_end_success": success,
        "mutually_viable_deal": success,
        "supplier_replaced": not success,
        "supplier_attainable_regret_usd": regret,
        "model_cost_usd": 0.01,
    }


def test_study_analysis_equal_weights_levels_and_builds_predeclared_contrasts() -> None:
    rows = []
    for level in ["R1", "R3", "R5"]:
        rows.append(_row("scripted-structured", level, success=True, regret=0))
        rows.append(_row("scripted-prose", level, success=True, regret=100_000))
        rows.append(_row("scripted-silent", level, success=False, regret=500_000))

    analysis = analyze_handoff_study(rows)

    assert analysis["run_count"] == 9
    assert analysis["arm_summaries"]["scripted-structured"]["end_to_end_success_rate"] == 1.0
    assert analysis["arm_summaries"]["scripted-silent"]["safe_action_itt_rate"] == 0.0
    contrast = analysis["contrasts"]["structured_vs_silent"]
    assert contrast["end_to_end_success_rate_difference"] == 1.0
    assert contrast["mean_regret_usd_difference"] == -500_000
    assert analysis["total_model_cost_usd"] == pytest.approx(0.09)


def test_invalid_runs_remain_in_itt_denominators() -> None:
    valid = _row("live-structured", "R1", success=True, regret=0)
    invalid = _row("live-structured", "R1", success=True, regret=0)
    invalid.update(
        {
            "run_valid": False,
            "threshold_transmission_exact": None,
            "safe_action_relative_to_truth": None,
            "end_to_end_success": False,
        }
    )

    analysis = analyze_handoff_study([valid, invalid])
    cell = analysis["cell_summaries"][0]

    assert cell["exact_transfer_itt_rate"] == 0.5
    assert cell["safe_action_itt_rate"] == 0.5
    assert cell["end_to_end_success_rate"] == 0.5
    assert cell["invalid_run_count"] == 1
