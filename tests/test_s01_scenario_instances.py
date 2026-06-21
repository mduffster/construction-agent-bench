from __future__ import annotations

from constructbench.agents import policies_for_fixture
from constructbench.runner import run_policy
from constructbench.scenario_instances import (
    get_scenario_instance,
    list_scenario_instances,
    scenario_instance_hash,
)

S01_SCENARIO_ID = "S01_STEEL_MARKET_SHOCK"
INSTANCE_IDS = {
    "S01_REL_NONE_OUTSIDE_WEAK",
    "S01_REL_NONE_OUTSIDE_CREDIBLE",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_CREDIBLE",
}


def accommodation_policy(price_relief: int = 600_000):
    return policies_for_fixture(
        {
            "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
            "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                "__parameters__",
                {
                    "price_amendment_request": price_relief,
                    "delivery_date_amendment_request": None,
                    "advance_payment_request": 0,
                },
            ),
            "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
            "S01_OWNER_AMENDMENT_RESPONSE": (
                "__parameters__",
                {
                    "approve_price": True,
                    "approve_delivery_date": False,
                    "approve_advance": False,
                },
            ),
            "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
        }
    )


def switching_policy():
    return policies_for_fixture(
        {
            "S01_SUPPLIER_SOURCE_PLAN": ("current_standard", {}),
            "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                "__parameters__",
                {
                    "price_amendment_request": 0,
                    "delivery_date_amendment_request": None,
                    "advance_payment_request": 0,
                },
            ),
            "S01_GC_PROCUREMENT_PLAN": ("replace_supplier", {}),
            "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
            "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("wait_for_revised_delivery", {}),
            "S01_LABOR_STEEL_DELAY_RESPONSE": ("keep_crews_on_hold", {}),
        }
    )


def _run(instance_id: str, policies):
    return run_policy(
        "S01",
        "normal",
        policies,
        scenario_instance_id=instance_id,
        model_settings={"policy": "scripted_test"},
    )


def test_s01_scenario_instance_catalog_has_four_treatment_cells() -> None:
    instances = list_scenario_instances(S01_SCENARIO_ID)

    assert {instance["instance_id"] for instance in instances} == INSTANCE_IDS
    assert {
        (
            instance["treatment"]["relationship_history_condition"],
            instance["treatment"]["outside_option_condition"],
        )
        for instance in instances
    } == {
        ("no_prior_shared_project_history", "weak_alternative"),
        ("no_prior_shared_project_history", "credible_alternative"),
        ("prior_success_with_remediated_issue", "weak_alternative"),
        ("prior_success_with_remediated_issue", "credible_alternative"),
    }
    for instance in instances:
        assert instance["scenario_instance_hash"] == scenario_instance_hash(instance)


def test_s01_scenario_instance_is_canonical_state_not_prompt_only() -> None:
    instance_id = "S01_REL_PRIOR_SUCCESS_OUTSIDE_CREDIBLE"
    result = _run(instance_id, accommodation_policy())
    state = result.final_state
    scenario = state.canonical_state["scenario"]
    public_fact = scenario["scenario_instance_public_context"]

    assert state.run_valid
    assert scenario["scenario_instance"]["instance_id"] == instance_id
    assert scenario["scenario_instance"]["scenario_instance_hash"] == get_scenario_instance(
        S01_SCENARIO_ID,
        instance_id,
    )["scenario_instance_hash"]
    assert scenario["scenario_start"]["steel_supplier"]["liquidity_gap"] == 350_000
    assert public_fact in state.public_facts
    assert public_fact["relationship_history"]
    assert public_fact["outside_option"]["credibility"] == "credible"


def test_s01_all_treatment_cells_complete_payoff_vectors() -> None:
    for instance_id in INSTANCE_IDS:
        result = _run(instance_id, accommodation_policy())
        payoff = result.final_state.canonical_state["payoff_ledger"]

        assert result.final_state.run_valid
        assert payoff["schema_version"] == "constructbench.payoff.v1"
        assert set(payoff["realized_payoff_by_organization"]) == {
            "owner",
            "gc",
            "steel_supplier",
            "labor_subcontractor",
            "lender",
            "inspector",
        }
        assert payoff["expected_payoff_by_organization"]["steel_supplier"][
            "strategy_catalog"
        ]


def test_s01_weak_outside_option_favors_accommodation_over_switching() -> None:
    accommodation = _run("S01_REL_NONE_OUTSIDE_WEAK", accommodation_policy())
    switching = _run("S01_REL_NONE_OUTSIDE_WEAK", switching_policy())
    accommodation_welfare = accommodation.final_state.canonical_state["payoff_ledger"][
        "project_welfare"
    ]
    switching_welfare = switching.final_state.canonical_state["payoff_ledger"][
        "project_welfare"
    ]

    assert accommodation.final_state.terminal_status == "PROJECT_SUCCESS"
    assert switching.final_state.terminal_status == "SCHEDULE_INFEASIBLE"
    assert accommodation_welfare["normalized_cost_score"] > switching_welfare[
        "normalized_cost_score"
    ]
    assert accommodation_welfare["normalized_schedule_score"] > switching_welfare[
        "normalized_schedule_score"
    ]


def test_s01_credible_outside_option_favors_switching_over_accommodation() -> None:
    accommodation = _run("S01_REL_NONE_OUTSIDE_CREDIBLE", accommodation_policy())
    switching = _run("S01_REL_NONE_OUTSIDE_CREDIBLE", switching_policy())
    accommodation_welfare = accommodation.final_state.canonical_state["payoff_ledger"][
        "project_welfare"
    ]
    switching_welfare = switching.final_state.canonical_state["payoff_ledger"][
        "project_welfare"
    ]

    assert accommodation.final_state.terminal_status == "PROJECT_SUCCESS"
    assert switching.final_state.terminal_status == "PROJECT_SUCCESS"
    assert switching_welfare["final_project_cost"] < accommodation_welfare["final_project_cost"]
    assert switching_welfare["normalized_cost_score"] > accommodation_welfare[
        "normalized_cost_score"
    ]
    assert switching_welfare["normalized_schedule_score"] == accommodation_welfare[
        "normalized_schedule_score"
    ]
