from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from constructbench.agents import AgentPolicy
from constructbench.runner import run_policy
from constructbench.s01_v2_ladder import (
    LADDER_STAGES,
    LINEAGE_LIVE_FIELDS_BY_NODE,
    LINEAGE_LIVE_PROFILE_ID,
    S01_V2_LADDER_EXPERIMENT_ID,
    BudgetConfig,
    LineageCorePolicy,
    StateAwareEfficientPolicy,
    build_mixed_policies,
    deterministic_background_policies,
    lineage_gate,
    stages_through,
)
from constructbench.scenarios import SCENARIOS
from constructbench.state import AGENT_IDS, AgentObservation, AgentSubmission


class _MarkerPolicy:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        return AgentSubmission()


def test_multiplayer_ladder_adds_roles_cumulatively() -> None:
    assert [stage.stage_id for stage in LADDER_STAGES] == [
        "supplier_gc",
        "add_inspector",
        "add_owner_lender",
        "full_six",
    ]
    assert LADDER_STAGES[0].live_roles == ("steel_supplier", "gc")
    for earlier, later in zip(LADDER_STAGES, LADDER_STAGES[1:], strict=False):
        assert set(earlier.live_roles) < set(later.live_roles)
    assert set(LADDER_STAGES[-1].live_roles) == set(AGENT_IDS)
    assert stages_through("add_inspector") == list(LADDER_STAGES[:2])


def test_mixed_policies_use_live_factory_only_for_selected_roles() -> None:
    created: list[str] = []

    def factory(agent_id: str) -> AgentPolicy:
        created.append(agent_id)
        return _MarkerPolicy(agent_id)

    policies = build_mixed_policies(["steel_supplier", "gc"], live_policy_factory=factory)
    assert created == ["gc", "steel_supplier"]
    assert isinstance(policies["gc"], LineageCorePolicy)
    assert isinstance(policies["gc"].live_policy, _MarkerPolicy)
    assert isinstance(policies["steel_supplier"], LineageCorePolicy)
    assert isinstance(policies["steel_supplier"].live_policy, _MarkerPolicy)
    assert all(
        isinstance(policy, StateAwareEfficientPolicy)
        for agent_id, policy in policies.items()
        if agent_id not in {"gc", "steel_supplier"}
    )


def test_lineage_live_projection_covers_every_node_and_does_not_mask_omission() -> None:
    scenario = SCENARIOS["S01_V2"]
    assert set(LINEAGE_LIVE_FIELDS_BY_NODE) == set(scenario.actors)
    for node_id, fields in LINEAGE_LIVE_FIELDS_BY_NODE.items():
        assert fields
        assert set(fields) <= set(scenario._request(node_id).parameter_specs)

    policies = build_mixed_policies(
        ["steel_supplier"],
        live_policy_factory=lambda agent_id: _MarkerPolicy(agent_id),
    )
    result = run_policy("S01_V2", "normal", policies, repair_budget=0)
    assert result.final_state.terminal_status == "INVALID_AGENT_OUTPUT"


def test_state_aware_efficient_background_is_valid_and_successful() -> None:
    result = run_policy(
        "S01_V2",
        "normal",
        deterministic_background_policies(),
        model_settings={"policy": "test_s01_v2_ladder_reference"},
    )
    analysis = result.final_state.canonical_state["s01_v2_state"]["analysis"]
    assert result.final_state.run_valid is True
    assert result.final_state.terminal_status == "PROJECT_SUCCESS"
    assert analysis["decision_count"] == 18
    assert analysis["coalition_success"] is True
    assert analysis["lineage"]["lineage_complete"] is True
    assert analysis["lineage"]["expected_exposure"]["rate"] == 1.0


def test_state_aware_counterparties_follow_a_supplier_offer_rejection() -> None:
    decisions = deepcopy(
        SCENARIOS["S01_V2"].fixtures["efficient_phased_coalition_success"][
            "decisions"
        ]
    )
    option_id, supplier = decisions["S01_B1_SUPPLIER_COMMITMENT"]
    decisions["S01_B1_SUPPLIER_COMMITMENT"] = (
        option_id,
        {**supplier, "provisional_offer_actions": []},
    )
    policies = deterministic_background_policies()
    policies["steel_supplier"] = StateAwareEfficientPolicy(decisions)

    result = run_policy("S01_V2", "normal", policies)
    analysis = result.final_state.canonical_state["s01_v2_state"]["analysis"]

    assert result.final_state.run_valid is True
    assert analysis["lineage"]["lineage_complete"] is True
    assert analysis["lineage"]["viability_preserving_chain"] is False
    assert result.final_state.decisions["S01_B4_OWNER_PACKAGE_DECISION"][
        "parameters"
    ]["package_action"] == "REJECT"
    assert result.final_state.decisions["S01_B5_LENDER_RELEASE_DECISION"][
        "parameters"
    ]["release_action"] == "HOLD"


def test_budget_defaults_leave_user_reserve_and_guard_next_stage() -> None:
    budget = BudgetConfig()
    budget.validate()
    assert S01_V2_LADDER_EXPERIMENT_ID == "s01_v2_live_multiplayer_ladder_v2"
    assert LINEAGE_LIVE_PROFILE_ID == "s01_v2_lineage_core_fields_v2"
    assert budget.program_prior_cost_usd == 7.108282
    assert budget.program_prior_cost_usd + sum(
        budget.stage_reserve_usd(stage.live_roles) for stage in LADDER_STAGES
    ) == pytest.approx(9.028282)
    assert budget.hard_total_cap_usd == 9.5
    assert budget.user_limit_reserve_usd == 0.5
    budget.assert_can_start(
        spent_new_usd=1.0,
        live_roles=LADDER_STAGES[-1].live_roles,
    )
    with pytest.raises(RuntimeError, match="new-model allocation stop"):
        budget.assert_can_start(
            spent_new_usd=1.5,
            live_roles=LADDER_STAGES[-1].live_roles,
        )


def test_budget_rejects_cap_that_does_not_stay_below_user_limit() -> None:
    with pytest.raises(ValueError, match="strictly below"):
        BudgetConfig(hard_total_cap_usd=10.0).validate()


@pytest.mark.parametrize(
    ("analysis", "expected"),
    [
        ({}, {"available": False, "passed": None, "source": None}),
        (
            {"lineage": {"complete_chain": True}},
            {
                "available": True,
                "passed": True,
                "source": "s01_v2_analysis.lineage.complete_chain",
                "earliest_failed_edge": None,
            },
        ),
        (
            {
                "lineage": {
                    "lineage_complete": False,
                    "earliest_failed_edge_id": "E4_RELEASABLE_VALUE_TO_DRAW",
                }
            },
            {
                "available": True,
                "passed": False,
                "source": "s01_v2_analysis.lineage.lineage_complete",
                "earliest_failed_edge": "E4_RELEASABLE_VALUE_TO_DRAW",
            },
        ),
        (
            {
                "decision_lineage": {
                    "complete_chain": False,
                    "earliest_failed_edge": "gc_to_inspector",
                }
            },
            {
                "available": True,
                "passed": False,
                "source": "s01_v2_analysis.decision_lineage.complete_chain",
                "earliest_failed_edge": "gc_to_inspector",
            },
        ),
        (
            {"lineage_metrics": {"expected_edge_exposure_rate": 0.75}},
            {
                "available": True,
                "passed": False,
                "source": ("s01_v2_analysis.lineage_metrics.expected_edge_exposure_rate"),
                "earliest_failed_edge": None,
            },
        ),
    ],
)
def test_lineage_gate_is_forward_compatible(
    analysis: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert lineage_gate({"s01_v2_analysis": analysis}) == expected
