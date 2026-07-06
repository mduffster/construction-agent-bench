from __future__ import annotations

from constructbench.agents import policies_for_fixture
from constructbench.runner import run_fixture, run_policy


def _project(result):
    return result.final_state.canonical_state["project"]


def _organizations(result):
    return result.final_state.canonical_state.get("organizations", {})


def test_applied_decisions_are_discoverable_to_actor_private_state() -> None:
    result = run_fixture("S01", "normal_success")

    private = result.final_state.private_state_by_agent

    assert private["steel_supplier"]["own_decision_records"][0]["node_id"] == (
        "S01_SUPPLIER_SOURCE_PLAN"
    )
    assert private["gc"]["own_decision_records"][0]["node_id"] == "S01_GC_PROCUREMENT_PLAN"
    assert private["labor_subcontractor"]["own_decision_records"][0]["node_id"] == (
        "S01_LABOR_MOBILIZATION"
    )


def test_s01_delivery_date_approval_changes_contract_consequence() -> None:
    base = {
        "S01_SUPPLIER_SOURCE_PLAN": ("current_standard", {}),
        "S01_SUPPLIER_COMMERCIAL_REQUEST": (
            "__parameters__",
            {
                "price_amendment_request": 0,
                "delivery_date_amendment_request": 18,
                "advance_payment_request": 0,
                "claimed_incremental_cost_usd": 800_000,
                "claimed_liquidity_requirement_usd": 0,
                "claimed_on_time_probability": 1.0,
            },
        ),
        "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
        "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
        "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("wait_for_revised_delivery", {}),
        "S01_LABOR_STEEL_DELAY_RESPONSE": ("keep_crews_on_hold", {}),
        "S01_GC_EMERGENCY_PROCUREMENT": ("wait_for_existing_source", {}),
    }
    approved = run_policy(
        "S01",
        "normal",
        policies_for_fixture(
            {
                **base,
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": False,
                        "approve_delivery_date": True,
                        "approve_advance": False,
                    },
                ),
            }
        ),
    )
    rejected = run_policy(
        "S01",
        "normal",
        policies_for_fixture(
            {
                **base,
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": False,
                        "approve_delivery_date": False,
                        "approve_advance": False,
                    },
                ),
            }
        ),
    )

    assert _project(approved)["contractual_delivery_due_tick"] == 18
    assert _project(rejected)["contractual_delivery_due_tick"] == 14
    assert _project(approved)["supplier_liquidated_damages"] == 0
    assert _project(rejected)["supplier_liquidated_damages"] == 100_000


def test_s03_equity_and_routine_draw_choices_change_financing_state() -> None:
    low_equity = run_policy(
        "S03",
        "normal",
        policies_for_fixture(
            {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_full_payment_tick_22", {}),
                "S03_OWNER_FINANCING_SOURCE": (
                    "__parameters__",
                    {
                        "equity_injection": 0,
                        "request_accelerated_draw": True,
                        "bridge_amount": 0,
                    },
                ),
                "S03_LENDER_ACCELERATED_DRAW_RESPONSE": ("approve_full_immediate", {}),
            }
        ),
    )
    high_equity = run_policy(
        "S03",
        "normal",
        policies_for_fixture(
            {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_full_payment_tick_22", {}),
                "S03_OWNER_FINANCING_SOURCE": (
                    "__parameters__",
                    {
                        "equity_injection": 2_000_000,
                        "request_accelerated_draw": True,
                        "bridge_amount": 0,
                    },
                ),
                "S03_LENDER_ACCELERATED_DRAW_RESPONSE": ("approve_full_immediate", {}),
            }
        ),
    )
    assert _project(low_equity)["financing_state"]["owner_cash_after_financing"] == 2_000_000
    assert _project(high_equity)["financing_state"]["owner_cash_after_financing"] == 4_000_000

    full = run_policy(
        "S03",
        "normal",
        policies_for_fixture(
            {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_no_payment", {}),
                "S03_OWNER_FINANCING_SOURCE": (
                    "__parameters__",
                    {
                        "equity_injection": 0,
                        "request_accelerated_draw": False,
                        "bridge_amount": 0,
                    },
                ),
                "S03_GC_SHORT_PAYMENT_RESPONSE": ("reduce_work_rate", {}),
                "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE": ("pay_outstanding_balance_in_full", {}),
            }
        ),
    )
    retained = run_policy(
        "S03",
        "normal",
        policies_for_fixture(
            {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_no_payment", {}),
                "S03_OWNER_FINANCING_SOURCE": (
                    "__parameters__",
                    {
                        "equity_injection": 0,
                        "request_accelerated_draw": False,
                        "bridge_amount": 0,
                    },
                ),
                "S03_GC_SHORT_PAYMENT_RESPONSE": ("reduce_work_rate", {}),
                "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE": ("retain_draw_and_make_no_payment", {}),
            }
        ),
    )
    assert _project(full)["payment_status"] == "late_payment_cured_by_routine_draw"
    assert _project(retained)["payment_status"] == "unpaid_after_routine_draw"
    assert _project(retained)["critical_work_finish_tick"] > _project(full)["critical_work_finish_tick"]


def test_s04_lender_draw_response_changes_project_state() -> None:
    base = {
        "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("targeted_repair_known_welds", {}),
        "S04_LABOR_REPAIR_MODE": ("standard_crew", {}),
        "S04_INSPECTOR_REINSPECTION": ("approve", {}),
    }

    released = run_policy(
        "S04",
        "normal",
        policies_for_fixture({**base, "S04_LENDER_DRAW_RESPONSE": ("release_draw", {})}),
    )
    rejected = run_policy(
        "S04",
        "normal",
        policies_for_fixture({**base, "S04_LENDER_DRAW_RESPONSE": ("reject_draw", {})}),
    )

    assert _project(released)["lender_draw_status"] == "released"
    assert _project(rejected)["lender_draw_status"] == "rejected"
    assert _project(rejected)["project_cost"] > _project(released)["project_cost"]
    assert _project(rejected)["completion_tick"] > _project(released)["completion_tick"]


def test_s05_labor_advance_request_changes_private_ledgers() -> None:
    no_advance = run_policy(
        "S05",
        "normal",
        policies_for_fixture(
            {
                "S05_LABOR_CAPACITY_PLAN": ("overtime_only", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "requested_reimbursement_fraction": 0.0,
                        "advance_requested": False,
                    },
                ),
                "S05_GC_STAFFING_RESPONSE": ("accept_labor_plan", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
            }
        ),
    )
    with_advance = run_policy(
        "S05",
        "normal",
        policies_for_fixture(
            {
                "S05_LABOR_CAPACITY_PLAN": ("overtime_only", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "requested_reimbursement_fraction": 0.0,
                        "advance_requested": True,
                    },
                ),
                "S05_GC_STAFFING_RESPONSE": ("accept_labor_plan", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
                "S05_OWNER_LABOR_COST_RESPONSE": ("approve_requested_amount", {}),
            }
        ),
    )

    assert _project(no_advance)["labor_advance_requested"] is False
    assert _project(with_advance)["labor_advance_requested"] is True
    assert _organizations(no_advance)["labor_subcontractor"]["approved_advance_received"] == 0
    assert _organizations(with_advance)["labor_subcontractor"]["approved_advance_received"] == 500_000
