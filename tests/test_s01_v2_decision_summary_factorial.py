from __future__ import annotations

import pytest

from constructbench.s01_v2_decision_summary_factorial import (
    BOTH_SUMMARIES,
    CONTRACTOR_ONLY,
    FACTORIAL_CONDITIONS,
    NO_SUMMARY,
    SUPPLIER_ONLY,
    aggregate_factorial_rows,
    build_factorial_policies,
    exact_binomial_interval,
    summary_recipients,
)
from constructbench.s01_v2_derived_state_packet import DerivedStatePacketPolicy
from constructbench.state import AgentObservation, AgentSubmission
from scripts import run_s01_v2_decision_summary_factorial as runner


class EmptyPolicy:
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        return AgentSubmission()


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (NO_SUMMARY, set()),
        (SUPPLIER_ONLY, {"steel_supplier"}),
        (CONTRACTOR_ONLY, {"gc"}),
        (BOTH_SUMMARIES, {"steel_supplier", "gc"}),
    ],
)
def test_factorial_assigns_decision_summaries_only_to_declared_recipients(
    condition: str, expected: set[str]
) -> None:
    policies = build_factorial_policies(condition, lambda _: EmptyPolicy())

    recipients = {
        agent_id
        for agent_id in ("steel_supplier", "gc")
        if isinstance(policies[agent_id], DerivedStatePacketPolicy)
    }
    assert recipients == expected
    assert set(summary_recipients(condition)) == expected


def test_sequence_is_frozen_to_ten_runs_per_arm_and_budget_under_ten() -> None:
    assert len(runner.STUDY_SEQUENCE) == 40
    for condition in FACTORIAL_CONDITIONS:
        assert sum(item == condition for item, _ in runner.STUDY_SEQUENCE) == 10
    assert runner.FRESH_BUDGET_CAP_USD == 6.8
    assert runner.FRESH_BUDGET_CAP_USD + 3.0 < 10
    runner.FactorialBudget().validate()


def test_exact_binomial_interval_matches_known_clopper_pearson_edges() -> None:
    assert exact_binomial_interval(0, 10) == [0.0, 0.308497]
    assert exact_binomial_interval(10, 10) == [0.691503, 1.0]
    middle = exact_binomial_interval(5, 10)
    assert middle is not None
    assert middle == pytest.approx([0.187086, 0.812914], abs=1e-6)


def test_factorial_aggregate_reports_arm_interaction_and_exact_intervals() -> None:
    rows = []
    successes = {
        NO_SUMMARY: 0,
        SUPPLIER_ONLY: 8,
        CONTRACTOR_ONLY: 2,
        BOTH_SUMMARIES: 9,
    }
    for condition in FACTORIAL_CONDITIONS:
        recipients = summary_recipients(condition)
        for replicate in range(10):
            success = replicate < successes[condition]
            rows.append(
                {
                    "condition": condition,
                    "run_valid": True,
                    "joint_efficient_outcome": success,
                    "coalition_success": success,
                    "backup_activated": not success,
                    "b1_cure_plan": "FULL_SEQUENCE_CURE" if success else "LOT_A_ONLY_CURE",
                    "r2_full_sequence_ready": success,
                    "lineage_complete": True,
                    "packet_exposure_audit_passed": True,
                    "repair_attempt_count": 0,
                    "final_project_cost": 96_000_000,
                    "completion_tick": 41,
                    "model_cost_usd": 0.16,
                    "supplier_summary": "steel_supplier" in recipients,
                    "contractor_summary": "gc" in recipients,
                }
            )

    aggregate = aggregate_factorial_rows(rows)

    assert aggregate["assigned_count"] == 40
    assert aggregate["by_condition"][SUPPLIER_ONLY]["joint_efficient_outcome_count"] == 8
    assert aggregate["supplier_summary_main_effect"]["risk_difference"] == 0.75
    assert aggregate["contractor_summary_main_effect"]["risk_difference"] == pytest.approx(0.15)
    assert aggregate["interaction_risk_difference"] == pytest.approx(-0.1)
    assert aggregate["all_exposure_audits_passed"] is True
