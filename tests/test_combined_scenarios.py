from __future__ import annotations

from constructbench.combined import run_combined_fixtures


def test_combined_fixture_run_stacks_schedule_delay_deltas() -> None:
    combined = run_combined_fixtures(
        [("S02", "normal_failure"), ("S05", "normal_failure")]
    )
    module_results = {
        result["scenario_key"]: result
        for result in combined.summary["module_results"]
    }

    assert combined.summary["combined_mode"] == "shared_state_additive_timing"
    assert combined.summary["run_valid"] is True
    assert module_results["S00"]["is_baseline"] is True
    assert module_results["S00"]["module_completion_tick"] == 40
    assert module_results["S02"]["schedule_delay_delta"] == 12
    assert module_results["S05"]["schedule_delay_delta"] == 9
    assert combined.summary["shared_baseline_completion_tick"] == 40
    assert combined.summary["total_schedule_delay_delta"] == 21
    assert combined.summary["completion_tick"] == 61
    assert combined.summary["baseline_scenario_key"] == "S00"
    assert combined.summary["final_project_cost"] == 108_100_000
    assert combined.summary["budget_status"] == "budget_infeasible"
    assert combined.summary["schedule_status"] == "schedule_infeasible"
    assert combined.summary["remaining_approved_budget_margin"] == -8_100_000
    assert combined.summary["remaining_success_budget_margin"] == -6_100_000
    assert combined.summary["contract_schedule_variance_ticks"] == 21
    assert combined.summary["remaining_schedule_float_to_success_deadline"] == -13
    assert combined.summary["schedule_plan"]["success_deadline_tick"] == 48
    assert combined.summary["required_deliverables_complete"] is True
    assert "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE" in combined.summary[
        "impacted_deliverable_ids"
    ]
    deliverables = {
        deliverable["deliverable_id"]: deliverable
        for deliverable in combined.run_result.final_state.canonical_state["project"][
            "normal_deliverables"
        ]
    }
    assert deliverables["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"][
        "actual_finish_tick"
    ] == 61


def test_combined_fixture_run_preserves_checkpoint_events_in_one_shared_trace() -> None:
    combined = run_combined_fixtures(
        [("S02", "normal_failure"), ("S05", "normal_failure")]
    )
    phase_ids = [
        phase["phase_id"]
        for phase in combined.run_result.final_state.histories["phase_history"]
    ]
    event_ids = set(combined.summary["public_event_ids"])

    assert "S02_CRANE_WEATHER_CHECKPOINT" in event_ids
    assert "S05_INSPECTION_READINESS_CHECKPOINT" in event_ids
    assert "S00:base_project_reference" in phase_ids
    assert "S00:base_authorization_and_funding" in phase_ids
    assert "S00:base_delivery_execution" in phase_ids
    assert "S00:base_inspection_approval" in phase_ids
    assert "S02:crane_failure_weather" in phase_ids
    assert "S05:labor_shortage" in phase_ids
    assert phase_ids.index("S00:base_project_reference") < phase_ids.index("S02:gc_recovery_plan")


def test_combined_private_event_facts_do_not_overwrite_startup_facts() -> None:
    combined = run_combined_fixtures(
        [("S02", "normal_failure"), ("S05", "normal_failure")]
    )
    gc_private_facts = combined.run_result.final_state.private_state_by_agent["gc"][
        "private_facts"
    ]

    assert gc_private_facts["S02"]["cash"] == 3_500_000
    assert gc_private_facts["S05"]["current_public_task_finish_tick"] == 35
    assert gc_private_facts["S00"]["cash"] == 4_000_000
    assert gc_private_facts["S02:crane_failure_weather"]["event_id"] == "S02_PRIVATE_CRANE_FAILURE"
