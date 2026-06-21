from __future__ import annotations

from constructbench.baseline import project_deliverables_from_impacts
from constructbench.runner import run_fixture


def _deliverable(project: dict, deliverable_id: str) -> dict:
    return {
        deliverable["deliverable_id"]: deliverable
        for deliverable in project["normal_deliverables"]
    }[deliverable_id]


def test_baseline_graph_cascades_dependency_delay_from_steel_delivery() -> None:
    deliverables = project_deliverables_from_impacts(
        actual_finish_overrides={"D11_STEEL_SUPPLIER_STEEL_DELIVERED": 18}
    )
    by_id = {
        deliverable["deliverable_id"]: deliverable
        for deliverable in deliverables
    }

    assert by_id["D11_STEEL_SUPPLIER_STEEL_DELIVERED"]["actual_finish_tick"] == 18
    assert by_id["D12_GC_CRANE_LIFT_OPERATIONS_READY"]["actual_finish_tick"] == 22
    assert by_id["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"]["actual_finish_tick"] == 44
    assert by_id["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"][
        "dependency_delay_ticks"
    ] == 4


def test_baseline_graph_blocks_downstream_deliverables_from_blocked_dependency() -> None:
    deliverables = project_deliverables_from_impacts(
        actual_finish_overrides={},
        blocked_deliverable_ids={"D11_STEEL_SUPPLIER_STEEL_DELIVERED"},
    )
    by_id = {
        deliverable["deliverable_id"]: deliverable
        for deliverable in deliverables
    }

    assert by_id["D11_STEEL_SUPPLIER_STEEL_DELIVERED"]["status"] == "blocked"
    assert by_id["D12_GC_CRANE_LIFT_OPERATIONS_READY"]["status"] == "blocked"
    assert by_id["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"]["status"] == "blocked"
    assert by_id["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"][
        "blocked_reason"
    ] == "dependency_blocked"


def test_s01_projects_steel_delivery_choice_onto_baseline_deliverables() -> None:
    project = run_fixture("S01", "normal_failure").final_state.canonical_state["project"]

    assert _deliverable(project, "D11_STEEL_SUPPLIER_STEEL_DELIVERED")[
        "actual_finish_tick"
    ] == 23
    assert _deliverable(project, "D13_LABOR_STRUCTURAL_STEEL_ERECTED")[
        "actual_finish_tick"
    ] == 31
    assert _deliverable(project, "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE")[
        "actual_finish_tick"
    ] == 49
    assert project["required_deliverables_complete"] is True


def test_s02_projects_crane_recovery_onto_baseline_deliverables() -> None:
    project = run_fixture("S02", "normal_failure").final_state.canonical_state["project"]

    assert _deliverable(project, "D12_GC_CRANE_LIFT_OPERATIONS_READY")[
        "actual_finish_tick"
    ] == 32
    assert _deliverable(project, "D13_LABOR_STRUCTURAL_STEEL_ERECTED")[
        "actual_finish_tick"
    ] == 34
    assert _deliverable(project, "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE")[
        "actual_finish_tick"
    ] == 52


def test_s03_projects_payment_cascade_onto_baseline_deliverables() -> None:
    project = run_fixture("S03", "normal_failure").final_state.canonical_state["project"]

    assert _deliverable(project, "D14_OWNER_PROGRESS_PAYMENT_CURRENT")[
        "actual_finish_tick"
    ] == 29
    assert _deliverable(project, "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE")[
        "actual_finish_tick"
    ] == 35
    assert _deliverable(project, "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE")[
        "actual_finish_tick"
    ] == 49


def test_s04_projects_structural_release_onto_baseline_deliverables() -> None:
    project = run_fixture("S04", "normal_success").final_state.canonical_state["project"]

    assert _deliverable(project, "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE")[
        "actual_finish_tick"
    ] == 29
    assert _deliverable(project, "D16_LENDER_STRUCTURAL_DRAW_RELEASE")[
        "actual_finish_tick"
    ] == 30
    assert _deliverable(project, "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE")[
        "actual_finish_tick"
    ] == 41


def test_s05_projects_labor_readiness_and_inspection_onto_baseline_deliverables() -> None:
    project = run_fixture("S05", "normal_failure").final_state.canonical_state["project"]

    assert _deliverable(project, "D19_LABOR_CRITICAL_INSPECTION_TASK_READY")[
        "actual_finish_tick"
    ] == 39
    assert _deliverable(project, "D20_INSPECTOR_RESERVED_INSPECTION_PASS")[
        "actual_finish_tick"
    ] == 45
    assert _deliverable(project, "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE")[
        "actual_finish_tick"
    ] == 49
