from __future__ import annotations

from constructbench.agents import EmptyPolicy, SingleSubmissionPolicy
from constructbench.runner import run_fixture, run_policy
from constructbench.state import AgentSubmission, DecisionSelection


def _empty_policies():
    empty = EmptyPolicy()
    return {
        "owner": empty,
        "gc": empty,
        "steel_supplier": empty,
        "labor_subcontractor": empty,
        "lender": empty,
        "inspector": empty,
    }


def test_empty_required_decision_stops_without_fake_outcome() -> None:
    result = run_policy("S01", "normal", _empty_policies())
    state = result.final_state

    assert not state.run_valid
    assert state.terminal_status == "INVALID_AGENT_OUTPUT"
    assert "missing required decisions" in state.terminal_reason
    assert state.canonical_state["project"]["completion_tick"] is None


def test_invalid_option_stops_run() -> None:
    invalid_supplier = SingleSubmissionPolicy(
        AgentSubmission(
            decisions=[
                DecisionSelection(node_id="S01_SUPPLIER_SOURCE_PLAN", option_id="invented_option"),
                DecisionSelection(
                    node_id="S01_SUPPLIER_COMMERCIAL_REQUEST",
                    parameters={
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                        "claimed_incremental_cost_usd": 800_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 1.0,
                    },
                ),
            ]
        )
    )
    policies = _empty_policies()
    policies["steel_supplier"] = invalid_supplier

    result = run_policy("S01", "normal", policies)

    assert not result.final_state.run_valid
    assert result.final_state.terminal_status == "INVALID_AGENT_OUTPUT"
    assert "invalid option" in result.final_state.terminal_reason


def test_missing_parameter_stops_run() -> None:
    invalid_supplier = SingleSubmissionPolicy(
        AgentSubmission(
            decisions=[
                DecisionSelection(node_id="S01_SUPPLIER_SOURCE_PLAN", option_id="current_standard"),
                DecisionSelection(
                    node_id="S01_SUPPLIER_COMMERCIAL_REQUEST",
                    parameters={"price_amendment_request": 0},
                ),
            ]
        )
    )
    policies = _empty_policies()
    policies["steel_supplier"] = invalid_supplier

    result = run_policy("S01", "normal", policies)

    assert not result.final_state.run_valid
    assert result.final_state.terminal_status == "INVALID_AGENT_OUTPUT"
    assert "missing parameters" in result.final_state.terminal_reason


def test_modeled_inaction_option_is_valid() -> None:
    result = run_fixture("S02", "normal_failure")

    assert result.final_state.run_valid
    assert any(
        record["node_id"] == "S02_GC_RECOVERY_PLAN"
        and record["option_id"] == "wait_for_diagnostics"
        for record in result.final_state.histories["decision_history"]
    )
