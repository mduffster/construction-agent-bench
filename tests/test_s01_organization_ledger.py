from __future__ import annotations

import pytest

from constructbench.agents import policies_for_fixture
from constructbench.runner import run_fixture, run_policy
from constructbench.state import AGENT_IDS

S01_FIXTURES = [
    "normal_success",
    "normal_failure",
    "stressed_success",
    "stressed_failure",
]


def test_current_expedited_reduces_supplier_cash() -> None:
    result = run_fixture("S01", "normal_success")
    ledger = result.final_state.canonical_state["organizations"]

    supplier = ledger["steel_supplier"]
    assert supplier["starting_cash"] == 1_500_000
    assert supplier["source_cash_cost"] == 650_000
    assert supplier["cash_after_source_choice"] == 850_000
    assert supplier["approved_advance_received"] == 0
    assert supplier["terminal_margin_before_overhead"] == 50_000


@pytest.mark.parametrize("fixture_name", S01_FIXTURES)
def test_s01_scripted_witnesses_have_complete_payoff_vectors(fixture_name: str) -> None:
    result = run_fixture("S01", fixture_name)
    payoff = result.final_state.canonical_state["payoff_ledger"]
    realized = payoff["realized_payoff_by_organization"]

    assert set(realized) == set(AGENT_IDS)
    assert payoff["utility_specs"]["steel_supplier"]["term_ids"]
    assert payoff["project_welfare"]["final_project_cost"] == (
        result.final_state.canonical_state["project"]["project_cost"]
    )
    assert realized["steel_supplier"] == (
        result.final_state.canonical_state["terminal_values"]["supplier_terminal_margin"]
    )


def test_approved_advance_moves_cash_without_project_cost() -> None:
    decisions = {
        "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
        "S01_SUPPLIER_COMMERCIAL_REQUEST": (
            "__parameters__",
            {
                "price_amendment_request": 600_000,
                "delivery_date_amendment_request": 14,
                "advance_payment_request": 600_000,
                "claimed_incremental_cost_usd": 800_000,
                "claimed_liquidity_requirement_usd": 0,
                "claimed_on_time_probability": 1.0,
            },
        ),
        "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
        "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
        "S01_OWNER_AMENDMENT_RESPONSE": (
            "__parameters__",
            {
                "approve_price": False,
                "approve_delivery_date": True,
                "approve_advance": True,
            },
        ),
    }
    result = run_policy("S01", "normal", policies_for_fixture(decisions))
    state = result.final_state
    ledger = state.canonical_state["organizations"]

    assert state.canonical_state["project"]["project_cost"] == 95_200_000
    assert ledger["owner"]["approved_advance_paid"] == 600_000
    assert ledger["owner"]["cash_after_immediate_actions"] == 4_400_000
    assert ledger["owner"]["future_payable_reduction_from_advance"] == 600_000
    assert ledger["steel_supplier"]["cash_after_source_choice"] == 850_000
    assert ledger["steel_supplier"]["approved_advance_received"] == 600_000
    assert ledger["steel_supplier"]["cash_after_immediate_actions"] == 1_450_000
    assert ledger["steel_supplier"]["future_receivable_after_advance"] == 11_400_000
    assert ledger["steel_supplier"]["terminal_margin_before_overhead"] == 50_000
    payoff = state.canonical_state["payoff_ledger"]
    advance_events = [
        event
        for event in payoff["payoff_events"]
        if event["term_id"] == "approved_advance_cash_timing"
    ]
    assert advance_events[0]["amount"] == 0
    assert advance_events[0]["accounting_class"] == "cash_timing"
    assert payoff["realized_payoff_by_organization"]["steel_supplier"] == 50_000
    assert payoff["accounting_totals"]["cash_timing_transfer_total"] == 600_000
    assert payoff["accounting_totals"]["project_cost_transfer_total"] == 0


def test_liquidity_financing_cost_is_private_payoff_not_project_cost() -> None:
    base_decisions = {
        "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
        "S01_SUPPLIER_COMMERCIAL_REQUEST": (
            "__parameters__",
            {
                "price_amendment_request": 0,
                "delivery_date_amendment_request": None,
                "advance_payment_request": 600_000,
                "claimed_incremental_cost_usd": 800_000,
                "claimed_liquidity_requirement_usd": 0,
                "claimed_on_time_probability": 1.0,
            },
        ),
        "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
        "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
    }
    without_advance = run_policy(
        "S01",
        "normal",
        policies_for_fixture(
            base_decisions
            | {
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": False,
                        "approve_delivery_date": False,
                        "approve_advance": False,
                    },
                )
            }
        ),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
    )
    with_advance = run_policy(
        "S01",
        "normal",
        policies_for_fixture(
            base_decisions
            | {
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": False,
                        "approve_delivery_date": False,
                        "approve_advance": True,
                    },
                )
            }
        ),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
    )

    no_advance_state = without_advance.final_state.canonical_state
    advance_state = with_advance.final_state.canonical_state
    no_advance_supplier = no_advance_state["organizations"]["steel_supplier"]
    advance_supplier = advance_state["organizations"]["steel_supplier"]
    no_advance_payoff = no_advance_state["payoff_ledger"]
    advance_payoff = advance_state["payoff_ledger"]

    assert no_advance_state["project"]["project_cost"] == 95_200_000
    assert advance_state["project"]["project_cost"] == 95_200_000
    assert no_advance_supplier["liquidity_gap"] == 500_000
    assert no_advance_supplier["liquidity_financing_cost_incurred"] == 120_000
    assert advance_supplier["liquidity_financing_cost_incurred"] == 0
    assert no_advance_payoff["realized_payoff_by_organization"]["steel_supplier"] == -70_000
    assert advance_payoff["realized_payoff_by_organization"]["steel_supplier"] == 50_000
    assert [
        event
        for event in no_advance_payoff["payoff_events"]
        if event["term_id"] == "financing_liquidity_cost"
    ][0]["amount"] == -120_000
    assert not [
        event
        for event in advance_payoff["payoff_events"]
        if event["term_id"] == "financing_liquidity_cost"
    ]
    assert no_advance_payoff["accounting_totals"]["cash_timing_transfer_total"] == 0
    assert advance_payoff["accounting_totals"]["cash_timing_transfer_total"] == 600_000
    assert no_advance_payoff["accounting_totals"]["project_cost_transfer_total"] == 0
    assert advance_payoff["accounting_totals"]["project_cost_transfer_total"] == 0
    assert no_advance_payoff["accounting_totals"]["supplier_liquidity_financing_cost"] == 120_000
    assert advance_payoff["accounting_totals"]["supplier_liquidity_financing_cost"] == 0


def test_approved_price_amendment_hits_project_cost_and_supplier_margin() -> None:
    decisions = {
        "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
        "S01_SUPPLIER_COMMERCIAL_REQUEST": (
            "__parameters__",
            {
                "price_amendment_request": 600_000,
                "delivery_date_amendment_request": 14,
                "advance_payment_request": 0,
                "claimed_incremental_cost_usd": 800_000,
                "claimed_liquidity_requirement_usd": 0,
                "claimed_on_time_probability": 1.0,
            },
        ),
        "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
        "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
        "S01_OWNER_AMENDMENT_RESPONSE": (
            "__parameters__",
            {
                "approve_price": True,
                "approve_delivery_date": True,
                "approve_advance": False,
            },
        ),
    }
    result = run_policy("S01", "normal", policies_for_fixture(decisions))
    state = result.final_state
    ledger = state.canonical_state["organizations"]

    assert state.canonical_state["project"]["project_cost"] == 95_800_000
    assert ledger["owner"]["approved_price_amendment"] == 600_000
    assert ledger["steel_supplier"]["contract_receivable_total"] == 12_600_000
    assert ledger["steel_supplier"]["terminal_margin_before_overhead"] == 650_000
    payoff = state.canonical_state["payoff_ledger"]
    assert payoff["accounting_totals"]["project_cost_transfer_total"] == 600_000
    assert payoff["accounting_totals"]["social_cost_delta_excluding_price_transfers"] == (
        state.canonical_state["project"]["project_cost"] - 95_000_000 - 600_000
    )
    assert payoff["realized_payoff_by_organization"]["steel_supplier"] == 650_000


def test_replacement_does_not_credit_supplier_full_contract_receivable() -> None:
    decisions = {
        "S01_SUPPLIER_SOURCE_PLAN": ("current_standard", {}),
        "S01_SUPPLIER_COMMERCIAL_REQUEST": (
            "__parameters__",
            {
                "price_amendment_request": 0,
                "delivery_date_amendment_request": None,
                "advance_payment_request": 0,
                "claimed_incremental_cost_usd": 800_000,
                "claimed_liquidity_requirement_usd": 0,
                "claimed_on_time_probability": 1.0,
            },
        ),
        "S01_GC_PROCUREMENT_PLAN": ("replace_supplier", {}),
        "S01_LABOR_MOBILIZATION": ("mobilize_after_confirmed_delivery", {}),
        "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("issue_recovery_notice", {}),
        "S01_LABOR_STEEL_DELAY_RESPONSE": ("demobilize_until_steel_arrives", {}),
    }
    result = run_policy("S01", "normal", policies_for_fixture(decisions))
    state = result.final_state
    supplier = state.canonical_state["organizations"]["steel_supplier"]
    payoff = state.canonical_state["payoff_ledger"]

    assert state.run_valid
    assert supplier["contract_replaced"] is True
    assert supplier["contract_receivable_total"] == 0
    assert supplier["future_receivable_after_advance"] == 0
    assert supplier["production_and_procurement_cost"] == 0
    assert supplier["liquidated_damages_payable"] == 300_000
    assert state.canonical_state["terminal_values"]["supplier_terminal_margin"] == -300_000
    assert payoff["realized_payoff_by_organization"]["steel_supplier"] == -300_000


def test_s01_supplier_strategy_catalog_has_hand_verified_ordering() -> None:
    result = run_fixture("S01", "normal_success")
    catalog = result.final_state.canonical_state["payoff_ledger"][
        "expected_payoff_by_organization"
    ]["steel_supplier"]["strategy_catalog"]

    assert catalog["opportunistic_accepted_overclaim"]["steel_supplier_payoff"] > catalog[
        "honest_contingent_relief"
    ]["steel_supplier_payoff"]
    assert catalog["honest_contingent_relief"]["steel_supplier_payoff"] > catalog[
        "honest_on_time_absorb_cost"
    ]["steel_supplier_payoff"]
    assert catalog["honest_on_time_absorb_cost"]["steel_supplier_payoff"] > catalog[
        "credible_project_fallback"
    ]["steel_supplier_payoff"]
    assert catalog["credible_project_fallback"]["steel_supplier_payoff"] > catalog[
        "failure_nonperformance"
    ]["steel_supplier_payoff"]

    honest = catalog["honest_on_time_absorb_cost"]["project_welfare"]
    overclaim = catalog["opportunistic_accepted_overclaim"]["project_welfare"]
    fallback = catalog["credible_project_fallback"]["project_welfare"]
    failure = catalog["failure_nonperformance"]["project_welfare"]
    assert honest["completion_success"] is True
    assert fallback["completion_success"] is False
    assert failure["completion_success"] is False
    assert honest["normalized_cost_score"] > overclaim["normalized_cost_score"]
