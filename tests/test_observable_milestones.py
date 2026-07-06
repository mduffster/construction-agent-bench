from __future__ import annotations

from constructbench.agents import policies_for_fixture
from constructbench.runner import run_fixture, run_policy


def _event_ids(result):
    return {
        fact.get("event_id")
        for fact in result.final_state.public_facts
        if isinstance(fact, dict)
    }


def test_private_supplier_cost_burden_does_not_leak_when_delivery_occurs_on_time() -> None:
    result = run_fixture("S01", "normal_success")

    event_ids = _event_ids(result)
    public_text = " ".join(
        str(fact)
        for fact in result.final_state.public_facts
    )

    assert "S01_STEEL_DELIVERY_CHECKPOINT" not in event_ids
    assert "current_input_cost" not in public_text
    assert "current_source_expedite_fee" not in public_text


def test_missed_steel_delivery_checkpoint_becomes_public_and_unlocks_response() -> None:
    result = run_policy(
        "S01",
        "normal",
        policies_for_fixture(
            {
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
                "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
                "S01_LABOR_MOBILIZATION": ("mobilize_tick_14", {}),
                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("issue_recovery_notice", {}),
                "S01_LABOR_STEEL_DELAY_RESPONSE": ("submit_idle_cost_notice", {}),
                "S01_GC_EMERGENCY_PROCUREMENT": ("wait_for_existing_source", {}),
            }
        ),
    )

    event_ids = _event_ids(result)
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }
    project = result.final_state.canonical_state["project"]

    assert result.final_state.run_valid
    assert "S01_STEEL_DELIVERY_CHECKPOINT" in event_ids
    assert "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE" in decision_nodes
    assert "S01_LABOR_STEEL_DELAY_RESPONSE" in decision_nodes
    assert project["missed_delivery_observed"] is True
    assert project["missed_delivery_gc_response"] == "issue_recovery_notice"
    assert project["missed_delivery_labor_response"] == "submit_idle_cost_notice"


def test_missed_owner_payment_checkpoint_precedes_payment_cascade() -> None:
    result = run_policy(
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

    event_ids = _event_ids(result)
    phase_ids = [
        phase["phase_id"]
        for phase in result.final_state.histories["phase_history"]
    ]
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }

    assert result.final_state.run_valid
    assert "S03_PAYMENT_DUE_CHECKPOINT" in event_ids
    assert "payment_due_checkpoint" in phase_ids
    assert "S03_GC_SHORT_PAYMENT_RESPONSE" in decision_nodes
    assert phase_ids.index("payment_due_checkpoint") < phase_ids.index("payment_followup_2")


def test_s02_weather_damage_checkpoint_unlocks_recovery_response() -> None:
    result = run_fixture("S02", "normal_failure")

    event_ids = _event_ids(result)
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }
    project = result.final_state.canonical_state["project"]

    assert result.final_state.run_valid
    assert "S02_CRANE_WEATHER_CHECKPOINT" in event_ids
    assert "S02_GC_WEATHER_DAMAGE_RESPONSE" in decision_nodes
    assert "S02_LABOR_WEATHER_DAMAGE_RESPONSE" in decision_nodes
    assert project["weather_damage_observed"] is True
    assert project["weather_damage_gc_response"] == "stabilize_and_resequence"
    assert project["weather_damage_labor_response"] == "submit_idle_cost_notice"


def test_s04_structural_release_checkpoint_blocks_silent_finalization() -> None:
    result = run_policy(
        "S04",
        "normal",
        policies_for_fixture(
            {
                "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("proceed_without_correction", {}),
                "S04_GC_SECOND_CORRECTIVE_STRATEGY": ("repair_remaining_identified_welds", {}),
                "S04_INSPECTOR_FINAL_RELEASE_REVIEW": ("approve", {}),
                "S04_LENDER_DRAW_RESPONSE": ("release_draw", {}),
            }
        ),
    )

    event_ids = _event_ids(result)
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }
    phase_ids = [
        phase["phase_id"]
        for phase in result.final_state.histories["phase_history"]
    ]

    assert result.final_state.run_valid
    assert "S04_STRUCTURAL_RELEASE_CHECKPOINT" in event_ids
    assert "S04_GC_SECOND_CORRECTIVE_STRATEGY" in decision_nodes
    assert "S04_INSPECTOR_FINAL_RELEASE_REVIEW" in decision_nodes
    assert phase_ids.index("structural_release_checkpoint") < phase_ids.index("final_release_review")


def test_s05_missed_reserved_inspection_checkpoint_unlocks_response() -> None:
    result = run_fixture("S05", "normal_failure")

    event_ids = _event_ids(result)
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }
    project = result.final_state.canonical_state["project"]

    assert result.final_state.run_valid
    assert "S05_INSPECTION_READINESS_CHECKPOINT" in event_ids
    assert "S05_GC_MISSED_INSPECTION_RESPONSE" in decision_nodes
    assert project["inspection_readiness_missed"] is True
    assert project["missed_inspection_response"] == "accept_next_standard_slot"
