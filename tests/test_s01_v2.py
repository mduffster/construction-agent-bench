from __future__ import annotations

import json
from copy import deepcopy

from constructbench.agents import policies_for_fixture
from constructbench.replay import replay_run
from constructbench.runner import _validate_submission, run_fixture, run_policy
from constructbench.s01_v2_lineage import build_s01_v2_lineage
from constructbench.scenarios import (
    S01_V2_CONTRACT,
    S01_V2_CROSS_ORGANIZATION_RECORDS_BY_TARGET,
    SCENARIOS,
)
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    Communication,
    DecisionSelection,
)


def _scenario():
    return SCENARIOS["S01_V2"]


def _run_efficient_with_overrides(overrides):
    decisions = deepcopy(
        _scenario().fixtures["efficient_phased_coalition_success"]["decisions"]
    )
    for node_id, changed in overrides.items():
        option_id, parameters = decisions[node_id]
        decisions[node_id] = (option_id, {**parameters, **changed})
    return run_policy("S01_V2", "normal", policies_for_fixture(decisions))


def _submission_for_request(request, parameters):
    return AgentSubmission(
        decisions=[
            DecisionSelection(
                node_id=request.node_id,
                option_id="__parameters__",
                parameters=parameters,
            )
        ],
        communications=[
            Communication(
                communication_type="no_communication",
                summary="Test policy explicitly sends no communication.",
            )
        ],
        assessment_reviews=[
            AssessmentReview(
                evidence_ids=[],
                counterparty_ids=[],
                reason="Test policy explicitly leaves assessments unchanged.",
            )
        ],
    )


def _observation_for_node(node_id: str) -> AgentObservation:
    scenario = _scenario()
    actor = scenario.actors[node_id]
    state = scenario.create_state(run_id=f"test_{node_id}", variant="normal")
    return AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=1,
        phase_id=node_id,
        phase_type="agent_execution_phase",
        agent_id=actor,
        role_briefing=state.briefings_by_agent[actor],
        current_business_context=node_id,
        known_facts=[
            {
                "visible_decisions": [
                    {
                        "node_id": "S01_A1_SUPPLIER_APPLICATION",
                        "actor_id": "steel_supplier",
                        "parameters": {"submitted_document_ids": list(SCENARIOS["S01_V2"].fixtures["efficient_phased_coalition_success"]["decisions"]["S01_A1_SUPPLIER_APPLICATION"][1]["submitted_document_ids"])},
                    }
                ],
                "decision_bounds": {
                    "S01_B3_INSPECTOR_DISPOSITION": {
                        "maximum_releasable_value_usd": 950_000,
                    },
                    "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                        "maximum_releasable_value_usd": 1_350_000,
                    },
                },
            }
        ],
        required_decisions=[scenario._request(node_id)],
        trust_prior_by_counterparty=state.trust_state[actor],
        submission_contract=S01_V2_CONTRACT,
    )


def test_s01_v2_witnesses_cover_required_terminal_classes() -> None:
    expected = {
        "efficient_phased_coalition_success": ("PROJECT_SUCCESS", True, True, 41),
        "conservative_project_success": ("PROJECT_SUCCESS", True, True, 42),
        "project_success_private_role_failure": ("PROJECT_SUCCESS", True, False, 41),
        "coordination_failure": ("CRITICAL_PATH_DEADLOCK", False, False, 50),
        "excessive_conservatism_failure": ("SCHEDULE_INFEASIBLE", False, False, 50),
        # On time but over the $102M ceiling: budget failure is a reachable
        # terminal class of its own, distinct from schedule and compliance.
        "budget_blowout_failure": ("BUDGET_INFEASIBLE", False, False, 45),
    }
    welfare = {}
    for fixture_name, (status, project_success, coalition_success, completion) in expected.items():
        result = run_fixture("S01_V2", fixture_name)
        project = result.final_state.canonical_state["project"]
        analysis = result.final_state.canonical_state["s01_v2_state"]["analysis"]

        assert result.final_state.run_valid
        assert result.final_state.terminal_status == status
        assert project["s01_v2_project_success"] is project_success
        assert project["s01_v2_coalition_success"] is coalition_success
        assert project["completion_tick"] == completion
        assert analysis["decision_count"] == 18
        assert len(result.final_state.histories["decision_history"]) == 18
        assert {record["actor_id"] for record in result.final_state.histories["decision_history"]} == set(AGENT_IDS)
        payoff = result.final_state.canonical_state["payoff_ledger"]
        assert len(payoff["payoff_events"]) == 6
        assert set(payoff["realized_payoff_by_organization"]) == set(AGENT_IDS)
        welfare[fixture_name] = (
            payoff["project_welfare"]["normalized_cost_score"]
            + payoff["project_welfare"]["normalized_schedule_score"]
        )

    assert welfare["efficient_phased_coalition_success"] > welfare["conservative_project_success"]


def test_s01_v2_schema_validates_each_node_and_rejects_bad_atoms() -> None:
    scenario = _scenario()
    for node_id in scenario.actors:
        request = scenario._request(node_id)
        valid_params = {
            name: deepcopy(spec.default)
            for name, spec in request.parameter_specs.items()
        }
        observation = _observation_for_node(node_id)
        assert _validate_submission(
            observation,
            _submission_for_request(request, valid_params),
            scenario=scenario,
        ) == []

        enum_name = next(
            (
                name
                for name, spec in request.parameter_specs.items()
                if spec.value_type == "enum"
            ),
            None,
        )
        if enum_name is not None:
            bad_enum = dict(valid_params)
            bad_enum[enum_name] = "NOT_ALLOWED"
            assert _validate_submission(
                observation,
                _submission_for_request(request, bad_enum),
                scenario=scenario,
            )

        numeric_name = next(
            name
            for name, spec in request.parameter_specs.items()
            if spec.value_type in {"integer", "decimal"} and spec.min_value is not None and spec.max_value is not None
        )
        spec = request.parameter_specs[numeric_name]
        below = dict(valid_params)
        below[numeric_name] = spec.min_value - 1
        above = dict(valid_params)
        above[numeric_name] = spec.max_value + 1
        assert _validate_submission(
            observation,
            _submission_for_request(request, below),
            scenario=scenario,
        )
        assert _validate_submission(
            observation,
            _submission_for_request(request, above),
            scenario=scenario,
        )


def test_s01_v2_rejects_invisible_document_reference() -> None:
    scenario = _scenario()
    request = scenario._request("S01_A2_GC_INITIAL_REVIEW")
    params = {
        name: deepcopy(spec.default)
        for name, spec in request.parameter_specs.items()
    }
    params["owner_lender_package_document_ids"] = ["DOC_LOT_B_QC_EXCEPTION"]
    observation = _observation_for_node("S01_A2_GC_INITIAL_REVIEW")
    observation.known_facts[0]["visible_decisions"][0]["parameters"]["submitted_document_ids"] = [
        "DOC_LOT_A_INVOICE",
    ]

    errors = _validate_submission(
        observation,
        _submission_for_request(request, params),
        scenario=scenario,
    )

    assert any("documents not submitted" in error for error in errors)


def test_s01_v2_rejects_cross_field_semantic_mismatches() -> None:
    scenario = _scenario()

    c1_request = scenario._request("S01_C1_SUPPLIER_STATUS_AND_RECOVERY")
    c1_params = {
        name: deepcopy(spec.default)
        for name, spec in c1_request.parameter_specs.items()
    } | {"ship_action": "SHIP_BOTH"}
    c1_observation = _observation_for_node("S01_C1_SUPPLIER_STATUS_AND_RECOVERY")
    c1_observation.known_facts.append(
        {
            "source": "private",
            "private_facts": {
                "s01_v2_actual_readiness": {
                    "actual_lot_a_ready_tick": 14,
                    "actual_lot_b_ready_tick": None,
                }
            },
        }
    )
    c1_errors = _validate_submission(
        c1_observation,
        _submission_for_request(c1_request, c1_params),
        scenario=scenario,
    )
    assert any("Lot B is not ready" in error for error in c1_errors)

    c3_request = scenario._request("S01_C3_INSPECTOR_FINAL_DISPOSITION")
    c3_params = {
        name: deepcopy(spec.default)
        for name, spec in c3_request.parameter_specs.items()
    } | {"approved_shipping_value_usd": 1_350_000}
    c3_observation = _observation_for_node("S01_C3_INSPECTOR_FINAL_DISPOSITION")
    c3_observation.known_facts[0]["decision_bounds"]["S01_C3_INSPECTOR_FINAL_DISPOSITION"] = {
        "maximum_releasable_value_usd": 950_000,
    }
    c3_errors = _validate_submission(
        c3_observation,
        _submission_for_request(c3_request, c3_params),
        scenario=scenario,
    )
    assert any("exceeds available inspected and verified value" in error for error in c3_errors)

    c2_request = scenario._request("S01_C2_GC_RECOVERY_PLAN")
    c2_params = {
        name: deepcopy(spec.default)
        for name, spec in c2_request.parameter_specs.items()
    } | {"recovery_plan": "ACTIVATE_BACKUP"}
    c2_observation = _observation_for_node("S01_C2_GC_RECOVERY_PLAN")
    c2_observation.known_facts[0]["recovery_options"] = {
        "backup": {
            "status": "NONE",
            "activation_cost_usd": 0,
            "delivery_tick_if_activated": None,
        }
    }
    c2_errors = _validate_submission(
        c2_observation,
        _submission_for_request(c2_request, c2_params),
        scenario=scenario,
    )
    assert any("requires a reserved or qualifying backup" in error for error in c2_errors)
    assert any("requires defined activation cost and delivery tick" in error for error in c2_errors)

    c6_request = scenario._request("S01_C6_ERECTOR_MOBILIZATION")
    c6_params = {
        name: deepcopy(spec.default)
        for name, spec in c6_request.parameter_specs.items()
    } | {
        "mobilization_action": "FULL",
    }
    c6_observation = _observation_for_node("S01_C6_ERECTOR_MOBILIZATION")
    c6_observation.known_facts[0]["decision_constraints"] = {
        "rules": [
            {
                "constraint_id": "mobilization_within_binding_capacity",
                "capacity_commitment": "SPLIT",
                "overtime_commitment": "NONE",
            }
        ]
    }
    c6_errors = _validate_submission(
        c6_observation,
        _submission_for_request(c6_request, c6_params),
        scenario=scenario,
    )
    assert any("FULL mobilization exceeds a SPLIT" in error for error in c6_errors)
def test_s01_v2_project_controls_are_visible_without_recommending_actions() -> None:
    efficient = run_fixture("S01_V2", "efficient_phased_coalition_success")
    efficient_c2 = next(
        observation
        for observation in efficient.final_state.histories["agent_observation_history"]
        if observation["phase_id"] == "S01_C2_GC_RECOVERY_PLAN"
    )
    efficient_fact = next(
        fact for fact in efficient_c2["known_facts"] if fact.get("source") == "s01_v2_phase_contract"
    )

    assert efficient_fact["project_controls_snapshot"]["schedule_status"] == "ON_TRACK"
    assert efficient_fact["project_controls_snapshot"]["current_forecast_completion_tick"] == 41
    assert efficient_fact["critical_path_schedule_rules"]["source"] == "public_project_controls"
    assert efficient_fact["decision_impact_tags"]["current_node_tags"] == [
        "schedule",
        "cost",
        "backup_option",
    ]

    failure = run_fixture("S01_V2", "excessive_conservatism_failure")
    failure_c2 = next(
        observation
        for observation in failure.final_state.histories["agent_observation_history"]
        if observation["phase_id"] == "S01_C2_GC_RECOVERY_PLAN"
    )
    failure_fact = next(
        fact for fact in failure_c2["known_facts"] if fact.get("source") == "s01_v2_phase_contract"
    )
    snapshot = failure_fact["project_controls_snapshot"]
    blockers = {blocker["blocker_id"] for blocker in snapshot["open_blockers"]}

    assert snapshot["schedule_status"] == "NONVIABLE_AS_PLANNED"
    assert snapshot["current_forecast_completion_tick"] > snapshot["success_deadline_tick"]
    assert "FULL_SEQUENCE_RELEASE_NOT_AVAILABLE" in blockers
    assert "CURRENT_SEQUENCE_EXCEEDS_SUCCESS_DEADLINE" in blockers
    assert "recommended_action" not in json.dumps(failure_fact)


def test_s01_v2_public_baseline_exposes_plan_and_payment_request_context() -> None:
    state = SCENARIOS["S01_V2"].create_state(
        run_id="s01_v2_public_context",
        variant="normal",
    )
    public_fact = state.public_facts[0]

    assert public_fact["baseline_planned_project_cost_usd"] == 95_000_000
    assert public_fact["current_forecast_project_cost_usd"] == 95_000_000
    assert public_fact["baseline_expected_completion_tick"] == 40
    assert public_fact["current_forecast_completion_tick"] == 40
    payment_context = public_fact["supplier_payment_application_context"]
    assert payment_context["requested_usd"] == 1_800_000
    assert "Lot B correction" in payment_context["public_reason"]


def test_s01_v2_parallel_barriers_and_private_readiness_visibility() -> None:
    result = run_fixture("S01_V2", "efficient_phased_coalition_success")
    observations = result.final_state.histories["agent_observation_history"]

    a3_nodes = {
        "S01_A3_OWNER_PROVISIONAL_POSITION",
        "S01_A3_INSPECTOR_REVIEW_PLAN",
        "S01_A3_ERECTOR_CAPACITY_OFFER",
    }
    for observation in observations:
        if observation["phase_id"] == "S01_A3_PARALLEL_INITIAL_POSITIONS":
            visible_nodes = {
                record["node_id"]
                for fact in observation["known_facts"]
                for record in fact.get("visible_decisions", [])
            }
            assert not (visible_nodes & a3_nodes)

    lender_a4 = next(
        observation
        for observation in observations
        if observation["phase_id"] == "S01_A4_LENDER_PROVISIONAL_POSITION"
    )
    visible_to_lender = {
        record["node_id"]
        for fact in lender_a4["known_facts"]
        for record in fact.get("visible_decisions", [])
    }
    assert a3_nodes <= visible_to_lender

    b3_nodes = {
        "S01_B3_INSPECTOR_DISPOSITION",
        "S01_B3_ERECTOR_BINDING_COMMITMENT",
    }
    for observation in observations:
        if observation["phase_id"] == "S01_B3_PARALLEL_TECHNICAL_AND_LABOR":
            visible_nodes = {
                record["node_id"]
                for fact in observation["known_facts"]
                for record in fact.get("visible_decisions", [])
            }
            assert not (visible_nodes & b3_nodes)

    gc_c2 = next(
        observation
        for observation in observations
        if observation["phase_id"] == "S01_C2_GC_RECOVERY_PLAN"
    )
    assert "actual_lot_a_ready_tick" not in json.dumps(gc_c2["known_facts"])
    supplier_private = result.final_state.private_state_by_agent["steel_supplier"]["private_facts"]
    assert supplier_private["s01_v2_actual_readiness"]["actual_lot_a_ready_tick"] == 14


def test_s01_v2_structured_records_follow_authorized_role_routes() -> None:
    result = run_fixture("S01_V2", "efficient_phased_coalition_success")
    observations = result.final_state.histories["agent_observation_history"]

    for observation in observations:
        target_node = observation["required_decisions"][0]["node_id"]
        actor = observation["agent_id"]
        visible = {
            record["node_id"]
            for fact in observation["known_facts"]
            for record in fact.get("visible_decisions", [])
        }
        cross_role = set(
            S01_V2_CROSS_ORGANIZATION_RECORDS_BY_TARGET.get(target_node, set())
        )
        own_nodes = {
            node_id for node_id, node_actor in _scenario().actors.items() if node_actor == actor
        }
        assert cross_role <= visible
        assert visible <= cross_role | own_nodes

    by_target = {
        observation["required_decisions"][0]["node_id"]: observation
        for observation in observations
    }
    owner_a3 = by_target["S01_A3_OWNER_PROVISIONAL_POSITION"]
    inspector_a3 = by_target["S01_A3_INSPECTOR_REVIEW_PLAN"]
    supplier_b1 = by_target["S01_B1_SUPPLIER_COMMITMENT"]

    owner_a2 = next(
        record
        for fact in owner_a3["known_facts"]
        for record in fact.get("visible_decisions", [])
        if record["node_id"] == "S01_A2_GC_INITIAL_REVIEW"
    )
    inspector_a2 = next(
        record
        for fact in inspector_a3["known_facts"]
        for record in fact.get("visible_decisions", [])
        if record["node_id"] == "S01_A2_GC_INITIAL_REVIEW"
    )
    assert "inspector_package_document_ids" not in owner_a2["parameters"]
    assert "owner_lender_package_document_ids" not in inspector_a2["parameters"]

    supplier_visible = {
        record["node_id"]
        for fact in supplier_b1["known_facts"]
        for record in fact.get("visible_decisions", [])
    }
    assert not {
        "S01_A3_OWNER_PROVISIONAL_POSITION",
        "S01_A3_INSPECTOR_REVIEW_PLAN",
        "S01_A3_ERECTOR_CAPACITY_OFFER",
        "S01_A4_LENDER_PROVISIONAL_POSITION",
    } & supplier_visible

    for target_node, observation in by_target.items():
        serialized = json.dumps(observation["known_facts"])
        if _scenario().actors[target_node] == "gc":
            continue
        assert "activation_cost_usd" not in serialized
        assert "delivery_tick_if_activated" not in serialized


def test_s01_v2_cross_field_constraints_are_visible_on_first_submission() -> None:
    result = run_fixture("S01_V2", "efficient_phased_coalition_success")
    observations = result.final_state.histories["agent_observation_history"]
    rules_by_node = {}
    for observation in observations:
        target_node = observation["required_decisions"][0]["node_id"]
        contract_fact = next(
            fact
            for fact in observation["known_facts"]
            if fact.get("source") == "s01_v2_phase_contract"
        )
        rules_by_node[target_node] = {
            rule["constraint_id"]: rule
            for rule in contract_fact["decision_constraints"]["rules"]
        }

    assert rules_by_node["S01_A2_GC_INITIAL_REVIEW"][
        "route_only_submitted_documents"
    ]["allowed_values"]
    assert rules_by_node["S01_A3_INSPECTOR_REVIEW_PLAN"][
        "inspection_tick_by_scope"
    ]["allowed_values_by_selector"]["FULL_SEQUENCE"] == [13]
    assert rules_by_node["S01_B2_GC_INTEGRATED_PACKAGE"][
        "verified_value_and_draw_bounds"
    ]["maximum_lender_draw_requested_usd"] == 760_000
    assert rules_by_node["S01_B5_LENDER_RELEASE_DECISION"][
        "lender_supported_release"
    ]["maximum_draw_if_reserve_preserved_usd"] == 760_000
    assert rules_by_node["S01_C4_OWNER_FINAL_POSITION"][
        "accepted_cost_share_sum"
    ]["component_fields"] == [
        "owner_cost_share_usd",
        "gc_cost_share_usd",
        "supplier_cost_share_usd",
    ]
    assert rules_by_node["S01_C5_LENDER_SUPPLEMENTAL_POSITION"] == {}
    assert rules_by_node["S01_C6_ERECTOR_MOBILIZATION"][
        "mobilization_within_binding_capacity"
    ]["capacity_commitment"] == "SPLIT"


class _OmitCommunicationPolicy:
    def __init__(self, decisions):
        self.decisions = decisions

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        selections = []
        for request in observation.required_decisions:
            option_id, params = self.decisions[request.node_id]
            selections.append(
                DecisionSelection(
                    node_id=request.node_id,
                    option_id=None if option_id == "__parameters__" else option_id,
                    parameters=params,
                )
            )
        return AgentSubmission(
            decisions=selections,
            assessment_reviews=[
                AssessmentReview(
                    evidence_ids=[],
                    counterparty_ids=[],
                    reason="No assessment change.",
                )
            ],
        )


class _OmitAssessmentPolicy(_OmitCommunicationPolicy):
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        submission = super().decide(observation)
        submission.communications = [
            Communication(
                communication_type="no_communication",
                summary="No communication.",
            )
        ]
        submission.assessment_reviews = []
        return submission


def test_s01_v2_communications_and_assessments_are_optional_without_evidence() -> None:
    fixture = _scenario().fixtures["efficient_phased_coalition_success"]
    no_comm = run_policy(
        "S01_V2",
        "normal",
        {agent_id: _OmitCommunicationPolicy(fixture["decisions"]) for agent_id in AGENT_IDS},
    )
    assert no_comm.final_state.terminal_status == "PROJECT_SUCCESS"

    no_assessment = run_policy(
        "S01_V2",
        "normal",
        {agent_id: _OmitAssessmentPolicy(fixture["decisions"]) for agent_id in AGENT_IDS},
    )
    assert no_assessment.final_state.terminal_status == "PROJECT_SUCCESS"

    valid = run_fixture("S01_V2", "efficient_phased_coalition_success")
    assert valid.final_state.histories["communication_abstention_history"] == []
    assert valid.final_state.histories["assessment_review_history"] == []


def test_s01_v2_resolution_handlers_apply_cash_release_and_no_unreleased_erection() -> None:
    efficient = run_fixture("S01_V2", "efficient_phased_coalition_success")
    r1_event = next(
        event
        for event in efficient.events
        if event.event_type == "consequence_applied"
        and event.details["phase_id"] == "S01_R1_VERIFY_AND_PUBLISH"
    )
    r1_state = r1_event.details["state_after"]["canonical_state"]["s01_v2_state"]
    assert r1_state["payment"]["eligible_stored_value_usd"] == 950_000
    assert r1_state["payment"]["lender_draw_released_usd"] == 0

    final = efficient.final_state.canonical_state["s01_v2_state"]
    assert final["payment"]["lender_draw_released_usd"] == 760_000
    assert final["supplier_execution"]["actual_lot_b_ready_tick"] == 18

    fixture = deepcopy(_scenario().fixtures["efficient_phased_coalition_success"]["decisions"])
    fixture["S01_C3_INSPECTOR_FINAL_DISPOSITION"] = (
        "__parameters__",
        {
            **fixture["S01_C3_INSPECTOR_FINAL_DISPOSITION"][1],
            "lot_b_disposition": "HOLD",
            "approved_shipping_value_usd": 950_000,
        },
    )
    fixture["S01_C6_ERECTOR_MOBILIZATION"] = (
        "__parameters__",
        {
            **fixture["S01_C6_ERECTOR_MOBILIZATION"][1],
            "mobilization_action": "FULL",
        },
    )
    fixture["S01_B3_ERECTOR_BINDING_COMMITMENT"] = (
        "__parameters__",
        {
            **fixture["S01_B3_ERECTOR_BINDING_COMMITMENT"][1],
            "capacity_commitment": "FULL",
            "mobilization_tick": 15,
            "standby_compensation_usd": 100_000,
            "overtime_commitment": "NONE",
        },
    )
    invalid_erection = run_policy("S01_V2", "normal", policies_for_fixture(fixture))
    project = invalid_erection.final_state.canonical_state["project"]
    assert invalid_erection.final_state.terminal_status == "CRITICAL_PATH_DEADLOCK"
    assert project["s01_v2_compliance_failure"] is True


def test_s01_v2_lineage_separates_traceability_from_viability() -> None:
    efficient = run_fixture("S01_V2", "efficient_phased_coalition_success")
    lineage = efficient.final_state.canonical_state["s01_v2_state"]["analysis"][
        "lineage"
    ]
    assert lineage["expected_exposure"] == {"count": 6, "passing": 6, "rate": 1.0}
    assert lineage["first_pass_submission_conformance"]["rate"] == 1.0
    assert lineage["action_realization"]["rate"] == 1.0
    assert lineage["silent_unexplained_clamp_count"] == 0
    assert lineage["lineage_complete"] is True
    assert lineage["viability_preserving_chain"] is True

    failed = run_fixture("S01_V2", "coordination_failure")
    failed_lineage = failed.final_state.canonical_state["s01_v2_state"]["analysis"][
        "lineage"
    ]
    assert failed_lineage["lineage_complete"] is True
    assert failed_lineage["viability_preserving_chain"] is False
    assert (
        failed_lineage["earliest_viability_break_edge_id"]
        == "E2_GC_ROUTING_TO_INSPECTION_REVIEW"
    )


def test_s01_v2_lineage_uses_actual_observation_exposure() -> None:
    result = run_fixture("S01_V2", "efficient_phased_coalition_success")
    observation = next(
        item
        for item in result.final_state.histories["agent_observation_history"]
        if item["required_decisions"][0]["node_id"] == "S01_A2_GC_INITIAL_REVIEW"
    )
    for fact in observation["known_facts"]:
        fact["visible_decisions"] = [
            record
            for record in fact.get("visible_decisions", [])
            if record.get("node_id") != "S01_A1_SUPPLIER_APPLICATION"
        ]

    lineage = build_s01_v2_lineage(result.final_state)

    assert lineage["lineage_complete"] is False
    assert lineage["earliest_failed_edge_id"] == "E1_DOCUMENTS_TO_GC_ROUTING"
    assert lineage["expected_exposure"]["rate"] == 5 / 6


def test_s01_v2_rejects_primary_draws_above_the_visible_chain() -> None:
    excessive_lender = _run_efficient_with_overrides(
        {"S01_B5_LENDER_RELEASE_DECISION": {"draw_release_usd": 1_000_000}}
    )
    assert excessive_lender.final_state.terminal_status == "INVALID_AGENT_OUTPUT"
    assert "visible supported draw" in excessive_lender.final_state.terminal_reason

    missing_gc_request = _run_efficient_with_overrides(
        {"S01_B2_GC_INTEGRATED_PACKAGE": {"lender_draw_requested_usd": 0}}
    )
    assert missing_gc_request.final_state.terminal_status == "INVALID_AGENT_OUTPUT"
    assert "visible supported draw" in missing_gc_request.final_state.terminal_reason


def test_s01_v2_reinspection_cannot_expand_a_zero_inspector_cap() -> None:
    result = _run_efficient_with_overrides(
        {
            "S01_B3_INSPECTOR_DISPOSITION": {
                "disposition": "NO_RELEASE",
                "maximum_releasable_value_usd": 0,
                "reinspection_tick": None,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "HOLD",
                "draw_release_usd": 0,
                "escrow_release_usd": 0,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {"ship_action": "HOLD_ALL"},
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "HOLD",
                "lot_b_disposition": "HOLD",
                "approved_shipping_value_usd": 0,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "RELEASE",
            },
        }
    )
    r2 = next(
        record
        for record in result.final_state.histories[
            "s01_v2_lineage_transition_history"
        ]
        if record["phase_id"] == "S01_R2_COMMIT_AND_PRODUCE"
    )
    assert result.final_state.run_valid is True
    assert r2["maximum_releasable_value_usd"] == 0
    assert result.final_state.canonical_state["project"]["s01_v2_released_lots"] == {
        "lot_a": False,
        "lot_b": False,
    }


def test_s01_v2_outputs_and_replay_remain_contract_compatible(tmp_path) -> None:
    output_dir = tmp_path / "s01_v2"
    result = run_fixture("S01_V2", "efficient_phased_coalition_success", output_dir=output_dir)

    assert {path.name for path in output_dir.iterdir()} == {
        "run_config.json",
        "events.jsonl",
        "turn_summaries.jsonl",
        "run_summary.json",
    }
    summary = json.loads((output_dir / "run_summary.json").read_text())
    assert summary["s01_v2_analysis"]["decision_count"] == 18
    assert summary["s01_v2_analysis"]["lineage"]["lineage_complete"] is True
    assert len(summary["s01_v2_lineage_transition_history"]) == 3
    assert summary["s01_v2_state"]["schema_version"] == "constructbench.s01_v2_state.v1"

    replayed = replay_run(output_dir)
    assert replayed.model_dump(mode="json") == result.final_state.model_dump(mode="json")


class _FlakyRepairPolicy:
    """Wraps a scripted policy; emits empty submissions until failures are spent."""

    def __init__(self, inner, *, fail_times: int, target_phase: str) -> None:
        self.inner = inner
        self.remaining_failures = fail_times
        self.target_phase = target_phase
        self.repair_calls = 0

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        if observation.phase_id == self.target_phase and self.remaining_failures > 0:
            self.remaining_failures -= 1
            return AgentSubmission()
        return self.inner.decide(observation)

    def repair(self, observation: AgentObservation, errors: list[str]) -> AgentSubmission:
        self.repair_calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            return AgentSubmission()
        return self.inner.decide(observation)


def _flaky_policies(fail_times: int) -> dict:
    fixture = _scenario().fixtures["efficient_phased_coalition_success"]["decisions"]
    policies = dict(policies_for_fixture(fixture))
    policies["steel_supplier"] = _FlakyRepairPolicy(
        policies["steel_supplier"],
        fail_times=fail_times,
        target_phase="S01_A1_SUPPLIER_APPLICATION",
    )
    return policies


def test_repair_budget_allows_multiple_repair_rounds() -> None:
    policies = _flaky_policies(fail_times=2)
    result = run_policy("S01_V2", "normal", policies, repair_budget=2)

    assert result.final_state.terminal_status == "PROJECT_SUCCESS"
    attempts = result.final_state.histories["repair_attempts"]
    assert [record["attempt"] for record in attempts] == [1, 2]
    assert all(
        record["phase_id"] == "S01_A1_SUPPLIER_APPLICATION" for record in attempts
    )
    assert policies["steel_supplier"].repair_calls == 2


def test_repair_budget_exhaustion_marks_run_invalid() -> None:
    policies = _flaky_policies(fail_times=2)
    result = run_policy("S01_V2", "normal", policies, repair_budget=1)

    assert result.final_state.terminal_status == "INVALID_AGENT_OUTPUT"
    attempts = result.final_state.histories["repair_attempts"]
    assert [record["attempt"] for record in attempts] == [1]


def test_repair_summary_reports_repaired_and_unrepaired_turns(tmp_path) -> None:
    output_dir = tmp_path / "repaired"
    policies = _flaky_policies(fail_times=1)
    run_policy("S01_V2", "normal", policies, repair_budget=1, output_dir=output_dir)

    summary = json.loads((output_dir / "run_summary.json").read_text())
    assert summary["terminal_status"] == "PROJECT_SUCCESS"
    assert summary["repair_summary"] == {
        "attempt_count": 1,
        "turns_with_repair_attempts": 1,
        "repaired_turn_count": 1,
        "unrepaired_turn_count": 0,
    }
    assert len(summary["repair_attempts"]) == 1
