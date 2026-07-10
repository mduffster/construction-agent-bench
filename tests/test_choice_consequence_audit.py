from constructbench.scenarios import SCENARIOS
from constructbench.state import ParameterSpec
from scripts.audit_choice_consequences import (
    _consequence_signature,
    audit_limits,
    collect_contexts,
    parameters_with_varied_field,
    representative_parameter_values,
    supporting_overrides_for_context,
)


def test_s01_v2_default_audit_limits_cover_every_parameter_value() -> None:
    limits = audit_limits(
        SCENARIOS["S01_V2"],
        contexts_per_node=0,
        branch_limit=0,
        max_parameters=0,
        max_values=0,
    )

    assert limits["max_parameters"] == 1_000_000
    assert limits["max_values"] == 1_000_000


def test_representative_values_include_nondefault_nullable_value() -> None:
    spec = ParameterSpec(
        value_type="enum",
        allowed_values=["ERECTOR_CAPACITY_OFFER"],
        nullable=True,
        default="ERECTOR_CAPACITY_OFFER",
        audit_values=["ERECTOR_CAPACITY_OFFER"],
    )

    assert representative_parameter_values(spec) == ["ERECTOR_CAPACITY_OFFER", None]


def test_s01_v2_consequence_signature_excludes_decision_bookkeeping() -> None:
    state = SCENARIOS["S01_V2"].create_state(run_id="audit_signature", variant="normal")
    alternate = state.model_copy(deep=True)
    alternate_scenario_state = alternate.canonical_state["s01_v2_state"]
    alternate_scenario_state["structured_decision_records"] = {
        "S01_A1_SUPPLIER_APPLICATION": {
            "parameters": {"payment_requested_usd": 1_800_000},
        }
    }
    alternate_scenario_state["analysis"] = {"decision_count": 1}

    assert _consequence_signature(alternate) == _consequence_signature(state)
    assert alternate_scenario_state["structured_decision_records"]
    assert alternate_scenario_state["analysis"]


def test_s01_v2_consequence_signature_retains_business_state() -> None:
    state = SCENARIOS["S01_V2"].create_state(run_id="audit_signature", variant="normal")
    alternate = state.model_copy(deep=True)
    alternate.canonical_state["s01_v2_state"]["payment"]["requested_usd"] += 100_000

    assert _consequence_signature(alternate) != _consequence_signature(state)


def test_s01_v2_audit_contexts_cover_every_witness_prefix() -> None:
    scenario = SCENARIOS["S01_V2"]

    contexts_by_node, _ = collect_contexts(
        scenario,
        "S01_V2",
        "normal",
        contexts_per_node=1,
        branch_limit=6,
        max_steps=10_000,
    )

    expected_fixture_names = set(scenario.fixtures)
    assert set(scenario.choice_audit_fixture_names) == expected_fixture_names
    for contexts in contexts_by_node.values():
        assert {context.fixture_name for context in contexts} == expected_fixture_names


def test_fixture_context_varies_one_field_against_authored_node_parameters() -> None:
    scenario = SCENARIOS["S01_V2"]
    fixture_name = "efficient_phased_coalition_success"
    node_id = "S01_A1_SUPPLIER_APPLICATION"
    contexts_by_node, _ = collect_contexts(
        scenario,
        "S01_V2",
        "normal",
        contexts_per_node=1,
        branch_limit=6,
        max_steps=10_000,
    )
    context = next(
        item for item in contexts_by_node[node_id] if item.fixture_name == fixture_name
    )
    fixture_parameters = scenario.fixtures[fixture_name]["decisions"][node_id][1]

    varied = parameters_with_varied_field(
        context.request,
        context.baseline_selection,
        "payment_requested_usd",
        0,
    )

    assert varied == {**fixture_parameters, "payment_requested_usd": 0}


def test_fixture_context_uses_authored_same_phase_counterparties() -> None:
    scenario = SCENARIOS["S01_V2"]
    fixture_name = "coordination_failure"
    node_id = "S01_A3_INSPECTOR_REVIEW_PLAN"
    contexts_by_node, _ = collect_contexts(
        scenario,
        "S01_V2",
        "normal",
        contexts_per_node=1,
        branch_limit=6,
        max_steps=10_000,
    )
    context = next(
        item for item in contexts_by_node[node_id] if item.fixture_name == fixture_name
    )

    [overrides] = supporting_overrides_for_context(context)

    owner_id = "S01_A3_OWNER_PROVISIONAL_POSITION"
    erector_id = "S01_A3_ERECTOR_CAPACITY_OFFER"
    assert overrides[owner_id].parameters == scenario.fixtures[fixture_name]["decisions"][
        owner_id
    ][1]
    assert overrides[erector_id].parameters == scenario.fixtures[fixture_name]["decisions"][
        erector_id
    ][1]
