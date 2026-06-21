from __future__ import annotations

from constructbench.agents import policies_for_fixture
from constructbench.baseline import (
    BASELINE_BUDGET_LINE_ITEMS,
    BASELINE_MILESTONE_WINDOWS,
    NORMAL_PROJECT_DELIVERABLES,
    normal_project_plan,
)
from constructbench.runner import run_fixture, run_policy


def test_normal_project_budget_constraints_and_schedule_bounds_are_explicit() -> None:
    plan = normal_project_plan("normal")
    budget = plan["budget_constraints"]
    schedule = plan["schedule_plan"]
    viability = plan["viability_bounds"]

    assert sum(item["amount"] for item in BASELINE_BUDGET_LINE_ITEMS) == 95_000_000
    assert budget["budget_line_item_total"] == 95_000_000
    assert budget["approved_budget"] == 100_000_000
    assert budget["approved_budget_remaining_at_baseline"] == 5_000_000
    assert budget["success_budget_ceiling"] == 102_000_000
    assert budget["hard_budget_margin_from_baseline"] == 7_000_000
    assert schedule["contract_target_completion_tick"] == 40
    assert schedule["baseline_expected_completion_tick"] == 40
    assert schedule["success_deadline_tick"] == 48
    assert schedule["schedule_float_to_success_deadline"] == 8
    assert viability["max_viable_project_cost"] == 102_000_000
    assert viability["max_viable_completion_tick"] == 48
    assert len(BASELINE_MILESTONE_WINDOWS) == 10
    assert {
        milestone["milestone_id"]: milestone["planned_tick"]
        for milestone in BASELINE_MILESTONE_WINDOWS
    }["M03_STEEL_DELIVERY"] == 14


def test_normal_project_deliverable_inventory_is_defensible_toy_graph() -> None:
    deliverables = list(NORMAL_PROJECT_DELIVERABLES)
    deliverable_ids = {
        deliverable["deliverable_id"]
        for deliverable in deliverables
    }
    accountable_agents = {
        deliverable["accountable_agent_id"]
        for deliverable in deliverables
    }
    hooks = {
        hook
        for deliverable in deliverables
        for hook in deliverable["perturbation_hooks"]
    }

    assert len(deliverables) == 27
    assert len(deliverable_ids) == len(deliverables)
    assert accountable_agents == {
        "owner",
        "gc",
        "steel_supplier",
        "labor_subcontractor",
        "lender",
        "inspector",
    }
    assert {
        "S01_steel_delivery",
        "S02_crane_failure_weather",
        "S03_owner_payment_due",
        "S04_weld_inspection_failure",
        "S05_reserved_inspection",
    }.issubset(hooks)
    for deliverable in deliverables:
        assert deliverable["planned_start_tick"] <= deliverable["planned_finish_tick"]
        for dependency in deliverable["dependencies"]:
            assert dependency in deliverable_ids


def test_base_case_normal_project_has_no_perturbation() -> None:
    result = run_fixture("S00", "normal_success")
    project = result.final_state.canonical_state["project"]
    event_ids = {
        fact.get("event_id")
        for fact in result.final_state.public_facts
        if isinstance(fact, dict)
    }

    assert result.final_state.run_valid
    assert result.final_state.terminal_status == "PROJECT_SUCCESS"
    assert project["project_cost"] == 95_000_000
    assert project["completion_tick"] == 40
    assert project["approved_budget"] == 100_000_000
    assert project["opening_contingency"] == 5_000_000
    assert project["budget_status"] == "within_approved_budget"
    assert project["schedule_status"] == "on_or_before_contract_target"
    assert project["remaining_approved_budget_margin"] == 5_000_000
    assert project["remaining_success_budget_margin"] == 7_000_000
    assert project["remaining_schedule_float_to_success_deadline"] == 8
    assert project["budget_constraints"]["budget_line_item_total"] == 95_000_000
    assert project["schedule_plan"]["success_deadline_tick"] == 48
    assert project["viability_bounds"]["reachable_completion_path_exists_at_baseline"] is True
    assert project["normal_deliverable_count"] == 27
    assert project["required_deliverables_complete"] is True
    assert {
        deliverable["deliverable_id"]
        for deliverable in project["normal_deliverables"]
    } == {
        deliverable["deliverable_id"]
        for deliverable in NORMAL_PROJECT_DELIVERABLES
    }
    decision_nodes = {
        decision["node_id"]
        for decision in result.final_state.histories["decision_history"]
    }

    assert event_ids == {"S00_BASE_PROJECT_REFERENCE"}
    public_fact = result.final_state.public_facts[0]
    assert public_fact["budget_constraints"]["approved_budget"] == 100_000_000
    assert public_fact["schedule_plan"]["contract_target_completion_tick"] == 40
    assert public_fact["viability_bounds"]["max_viable_completion_tick"] == 48
    assert decision_nodes == {
        "S00_OWNER_DELIVERY_AUTHORIZATION",
        "S00_LENDER_FUNDING_DELIVERY",
        "S00_GC_DELIVERY_COORDINATION",
        "S00_SUPPLIER_MATERIAL_DELIVERY",
        "S00_LABOR_WORK_DELIVERY",
        "S00_INSPECTOR_APPROVAL_DELIVERY",
    }


def test_base_case_stressed_project_is_still_unperturbed_reference() -> None:
    result = run_fixture("S00", "stressed_success")
    project = result.final_state.canonical_state["project"]

    assert result.final_state.run_valid
    assert result.final_state.terminal_status == "PROJECT_SUCCESS"
    assert project["project_cost"] == 98_600_000
    assert project["completion_tick"] == 44
    assert project["opening_contingency"] == 1_800_000


def test_base_case_nonordinary_delivery_choice_changes_reference_environment() -> None:
    result = run_policy(
        "S00",
        "normal",
        policies_for_fixture(
            {
                "S00_OWNER_DELIVERY_AUTHORIZATION": ("authorize_approved_plan", {}),
                "S00_LENDER_FUNDING_DELIVERY": ("confirm_routine_draws", {}),
                "S00_GC_DELIVERY_COORDINATION": ("execute_approved_sequence", {}),
                "S00_SUPPLIER_MATERIAL_DELIVERY": ("deliver_tick_15_with_notice", {}),
                "S00_LABOR_WORK_DELIVERY": ("perform_planned_crews", {}),
                "S00_INSPECTOR_APPROVAL_DELIVERY": ("standard_inspection_sequence", {}),
            }
        ),
    )
    project = result.final_state.canonical_state["project"]

    assert result.final_state.run_valid
    assert project["steel_delivery_tick"] == 15
    assert project["completion_tick"] == 41
    assert project["project_cost"] == 95_300_000
    assert project["schedule_status"] == "late_but_still_viable"
    assert project["remaining_schedule_float_to_success_deadline"] == 7
    steel_delivery = {
        deliverable["deliverable_id"]: deliverable
        for deliverable in project["normal_deliverables"]
    }["D11_STEEL_SUPPLIER_STEEL_DELIVERED"]
    assert steel_delivery["actual_finish_tick"] == 15
    assert steel_delivery["schedule_variance_ticks"] == 1


def test_perturbation_observation_includes_common_baseline_plan_and_impact_map() -> None:
    result = run_policy("S01", "normal", policies_for_fixture({}))
    observation = result.final_state.histories["agent_observation_history"][0]
    baseline_fact = next(
        fact
        for fact in observation["known_facts"]
        if fact.get("source") == "public_project_plan"
    )
    steel_delivery = {
        deliverable["deliverable_id"]: deliverable
        for deliverable in baseline_fact["deliverable_schedule"]
    }["D11_STEEL_SUPPLIER_STEEL_DELIVERED"]
    decision_impacts = {
        impact["node_id"]
        for impact in baseline_fact["scenario_baseline_impact"]["decision_impacts"]
    }

    assert baseline_fact["budget_constraints"]["approved_budget"] == 100_000_000
    assert baseline_fact["schedule_plan"]["contract_target_completion_tick"] == 40
    assert baseline_fact["schedule_plan"]["success_deadline_tick"] == 48
    assert steel_delivery["planned_finish_tick"] == 14
    assert "S01_SUPPLIER_SOURCE_PLAN" in decision_impacts
    assert "D11_STEEL_SUPPLIER_STEEL_DELIVERED" in baseline_fact[
        "scenario_baseline_impact"
    ]["affected_deliverable_ids"]
