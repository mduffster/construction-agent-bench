from __future__ import annotations

from constructbench.agents import policies_for_fixture
from constructbench.runner import run_policy
from constructbench.scenario_instances import (
    get_scenario_instance,
    list_scenario_instances,
    scenario_instance_hash,
    scenario_treatment_record_hash,
)

S01_SCENARIO_ID = "S01_STEEL_MARKET_SHOCK"
INSTANCE_IDS = {
    "S01_REL_NONE_OUTSIDE_WEAK",
    "S01_REL_NONE_OUTSIDE_CREDIBLE",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK",
    "S01_REL_PRIOR_SUCCESS_OUTSIDE_CREDIBLE",
}
REQUIRED_SUPPLIER_PARAMETERS = {
    "current_input_cost",
    "liquidity_gap",
    "liquidity_financing_cost",
    "current_source_standard_delivery_tick",
    "current_source_expedite_fee",
    "current_source_expedited_delivery_tick",
    "approved_alternate_deposit",
    "approved_alternate_delivery_tick",
    "nonapproved_alternate_deposit",
    "nonapproved_alternate_delivery_tick",
}
REQUIRED_OWNER_PARAMETERS = {
    "price_relief_options",
    "advance_payment_options",
}
REQUIRED_PROJECT_PARAMETERS = {
    "replacement_supplier_cost",
    "replacement_supplier_lead_time_ticks",
    "secondary_supplier_cost",
    "secondary_supplier_lead_time_ticks",
    "source_testing_cost",
    "source_testing_delay_ticks",
    "project_delay_overhead_per_tick",
}
REQUIRED_OUTSIDE_OPTION_FIELDS = {
    "option_id",
    "qualification_required",
    "switch_cost",
    "expected_delay_ticks",
    "delivery_risk",
    "termination_cost",
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
    assert public_fact["treatment_record_hash"] == scenario["scenario_instance"][
        "treatment_record_hash"
    ]
    assert "relationship_history" not in public_fact
    assert "outside_option" not in public_fact
    assert scenario["scenario_instance"]["relationship_history"][0]["events"][0][
        "type"
    ] == "delivery"
    assert scenario["scenario_instance"]["outside_option"]["switch_cost"] == 0


def test_s01_scenario_instances_fully_specify_minimum_experimental_parameters() -> None:
    for instance in list_scenario_instances(S01_SCENARIO_ID):
        assert "relationship_history" in instance
        assert REQUIRED_OUTSIDE_OPTION_FIELDS <= set(instance["outside_option"])
        assert instance["treatment_record_hash"] == scenario_treatment_record_hash(instance)
        for variant in ["normal", "stressed"]:
            overrides = instance["variant_overrides"][variant]
            assert REQUIRED_SUPPLIER_PARAMETERS <= set(overrides["steel_supplier"])
            assert REQUIRED_OWNER_PARAMETERS <= set(overrides["owner"])
            assert REQUIRED_PROJECT_PARAMETERS <= set(overrides["project_parameters"])


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


def test_s01_relationship_history_changes_expected_payoff_table() -> None:
    no_history = _run("S01_REL_NONE_OUTSIDE_WEAK", accommodation_policy())
    prior_success = _run("S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK", accommodation_policy())
    no_history_catalog = no_history.final_state.canonical_state["payoff_ledger"][
        "expected_payoff_by_organization"
    ]["steel_supplier"]["strategy_catalog"]
    prior_success_catalog = prior_success.final_state.canonical_state["payoff_ledger"][
        "expected_payoff_by_organization"
    ]["steel_supplier"]["strategy_catalog"]

    no_history_relief = no_history_catalog["honest_contingent_relief"]
    prior_success_relief = prior_success_catalog["honest_contingent_relief"]

    assert prior_success_relief["relationship_history_signal"][
        "delivery_success_count"
    ] == 1
    assert prior_success_relief["expected_steel_supplier_payoff"] > no_history_relief[
        "expected_steel_supplier_payoff"
    ]
    assert prior_success_relief["relief_approval_probability"] > no_history_relief[
        "relief_approval_probability"
    ]


def test_s01_outside_option_records_change_expected_fallback_table() -> None:
    weak = _run("S01_REL_NONE_OUTSIDE_WEAK", accommodation_policy())
    credible = _run("S01_REL_NONE_OUTSIDE_CREDIBLE", accommodation_policy())
    weak_fallback = weak.final_state.canonical_state["payoff_ledger"][
        "expected_payoff_by_organization"
    ]["steel_supplier"]["strategy_catalog"]["credible_project_fallback"]
    credible_fallback = credible.final_state.canonical_state["payoff_ledger"][
        "expected_payoff_by_organization"
    ]["steel_supplier"]["strategy_catalog"]["credible_project_fallback"]

    assert weak_fallback["outside_option_record"]["switch_cost"] > credible_fallback[
        "outside_option_record"
    ]["switch_cost"]
    assert weak_fallback["expected_project_cost"] > credible_fallback[
        "expected_project_cost"
    ]


def test_s01_prompt_paraphrase_does_not_change_treatment_record_hash() -> None:
    instance = get_scenario_instance(S01_SCENARIO_ID, "S01_REL_NONE_OUTSIDE_WEAK")
    paraphrased = {
        **instance,
        "public_context": {
            "summary": "Different wording for the same treatment cell.",
        },
    }

    assert scenario_treatment_record_hash(paraphrased) == instance[
        "treatment_record_hash"
    ]


def test_s01_treatment_context_visibility_is_role_scoped() -> None:
    result = _run("S01_REL_PRIOR_SUCCESS_OUTSIDE_CREDIBLE", accommodation_policy())
    observations = result.final_state.histories["agent_observation_history"]

    supplier_context = _private_treatment_context(
        observations,
        phase_id="supplier_source_and_commercial",
        agent_id="steel_supplier",
    )
    gc_context = _private_treatment_context(
        observations,
        phase_id="source_response",
        agent_id="gc",
    )
    labor_context = _private_treatment_context(
        observations,
        phase_id="source_response",
        agent_id="labor_subcontractor",
    )

    assert supplier_context["relationship_history"][0]["events"]
    assert "outside_option_economics" not in supplier_context
    assert "switch_cost" not in supplier_context["outside_option"]
    assert gc_context["outside_option_economics"]["switch_cost"] == 0
    assert gc_context["relationship_history"][0]["events"]
    assert labor_context is None


def _private_treatment_context(
    observations: list[dict],
    *,
    phase_id: str,
    agent_id: str,
) -> dict | None:
    observation = next(
        record
        for record in observations
        if record["phase_id"] == phase_id and record["agent_id"] == agent_id
    )
    private_fact = next(
        fact for fact in observation["known_facts"] if fact.get("source") == "private"
    )
    return private_fact["private_facts"].get("scenario_treatment_context")
