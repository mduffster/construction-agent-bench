from __future__ import annotations

import json

import pytest

from constructbench.models import LLMPolicy
from constructbench.runner import _apply_event_phase, _build_observation, _validate_submission
from constructbench.scenarios import get_scenario
from constructbench.state import AgentObservation, AssessmentEvidence


class FakeAdapter:
    model = "fake-5b"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.responses.pop(0)


class FakeUsageAdapter(FakeAdapter):
    model = "claude-haiku-4-5-20251001"

    def __init__(self, responses: list[str], usage: dict[str, int]) -> None:
        super().__init__(responses)
        self.usage = usage

    def drain_usage(self) -> dict[str, int]:
        return self.usage


def _supplier_observation():
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    state.histories["phase_history"].append(
        {"phase_index": 1, "phase_id": "market_shock", "phase_type": "event_phase", "summary": ""}
    )
    phase = scenario.next_phase(state)
    assert phase is not None
    state.phase_index = 2
    return _build_observation(state, phase, phase.turns[0])


def _observation_for(scenario_key: str, phase_id: str, agent_id: str):
    scenario = get_scenario(scenario_key)
    state = scenario.create_state(run_id="test", variant="normal")
    events = []
    while True:
        phase = scenario.next_phase(state)
        assert phase is not None
        state.phase_index += 1
        if phase.phase_type == "event_phase":
            _apply_event_phase(state, events, phase)
            continue
        assert phase.phase_id == phase_id
        turn = next(turn for turn in phase.turns if turn.agent_id == agent_id)
        return _build_observation(state, phase, turn)


def _valid_supplier_json() -> str:
    return json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": "current_expedited",
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": None,
                    "parameters": {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                    },
                },
            ],
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Preserve delivery if possible.",
        }
    )


def test_llm_policy_parses_fenced_json() -> None:
    observation = _supplier_observation()
    policy = LLMPolicy(FakeAdapter(["```json\n" + _valid_supplier_json() + "\n```"]), "steel_supplier")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []


def test_llm_policy_records_anthropic_usage_and_cost() -> None:
    observation = _supplier_observation()
    policy = LLMPolicy(
        FakeUsageAdapter(
            [_valid_supplier_json()],
            {"input_tokens": 10, "output_tokens": 5},
        ),
        "steel_supplier",
    )

    submission = policy.decide(observation)
    records = policy.drain_model_io()

    assert _validate_submission(observation, submission) == []
    assert records[0]["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert records[0]["cost_usd"] == pytest.approx(0.000035)


def test_llm_policy_targeted_repair_can_produce_valid_submission() -> None:
    observation = _supplier_observation()
    policy = LLMPolicy(FakeAdapter(["{}", _valid_supplier_json()]), "steel_supplier")

    first = policy.decide(observation)
    errors = _validate_submission(observation, first)
    repaired = policy.repair(observation, errors)

    assert errors
    assert _validate_submission(observation, repaired) == []


def test_llm_policy_normalizes_haiku_style_private_message() -> None:
    observation = _supplier_observation()
    response = json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": "current_expedited",
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": "__parameters__",
                    "parameters": {
                        "price_amendment_request": 900000,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 500000,
                    },
                },
            ],
            "communications": [
                {
                    "type": "private_message",
                    "recipients": ["gc"],
                    "message": "Proceeding with expedited sourcing and requesting commercial terms.",
                }
            ],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Preserve schedule with commercial request.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "steel_supplier")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.communications[0].communication_type == "private_message"
    assert submission.communications[0].recipient_ids == ["gc"]


def test_llm_policy_normalizes_message_body_field() -> None:
    observation = _supplier_observation()
    response = json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": "current_standard",
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": "__parameters__",
                    "parameters": {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": 18,
                        "advance_payment_request": 0,
                    },
                },
            ],
            "communications": [
                {
                    "communication_type": "private_message",
                    "recipient_ids": ["gc"],
                    "message_body": "Steel will arrive on the current standard schedule.",
                }
            ],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Use standard delivery.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "steel_supplier")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.communications[0].summary == "Steel will arrive on the current standard schedule."


def test_llm_policy_normalizes_recipient_agent_ids_field() -> None:
    observation = _supplier_observation()
    response = json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": "current_standard",
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": "__parameters__",
                    "parameters": {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": 18,
                        "advance_payment_request": 0,
                    },
                },
            ],
            "communications": [
                {
                    "communication_type": "private_message",
                    "recipient_agent_ids": ["gc"],
                    "body": "Steel will arrive on the current standard schedule.",
                }
            ],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Use standard delivery.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "steel_supplier")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.communications[0].recipient_ids == ["gc"]


def test_gemma_compact_policy_parses_decisions_by_node() -> None:
    observation = _supplier_observation()
    compact_response = json.dumps(
        {
            "decisions_by_node": {
                "S01_SUPPLIER_SOURCE_PLAN": "approved_alternate",
                "S01_SUPPLIER_COMMERCIAL_REQUEST": "__parameters__",
            },
            "parameters_by_node": {
                "S01_SUPPLIER_COMMERCIAL_REQUEST": {
                    "price_amendment_request": 0,
                    "delivery_date_amendment_request": None,
                    "advance_payment_request": 0,
                }
            },
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Use a compact supplier action shape.",
        }
    )
    policy = LLMPolicy(
        FakeAdapter([compact_response]),
        "steel_supplier",
        prompt_style="gemma_compact",
    )

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []


def test_gemma_compact_policy_parses_parameter_nodes_from_parameters_by_node() -> None:
    observation = _observation_for("S02", "gc_recovery_plan", "gc")
    compact_response = json.dumps(
        {
            "decisions_by_node": {
                "S02_GC_RECOVERY_PLAN": "rent_replacement_crane",
            },
            "parameters_by_node": {
                "S02_GC_INTERIM_PLAN": {
                    "crew_plan": "retain_idle",
                    "delivery_plan": "accept_as_scheduled",
                    "protect_exposed_work": True,
                },
                "S02_GC_RECOVERY_COST_REQUEST": {
                    "requested_reimbursement_fraction": "0.5",
                },
            },
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Rent a replacement crane and request partial reimbursement.",
        }
    )
    policy = LLMPolicy(FakeAdapter([compact_response]), "gc", prompt_style="gemma_compact")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    reimbursement = next(
        decision
        for decision in submission.decisions
        if decision.node_id == "S02_GC_RECOVERY_COST_REQUEST"
    )
    assert reimbursement.parameters["requested_reimbursement_fraction"] == 0.5


def test_gemma_compact_policy_converts_flat_unchanged_assessment_to_review() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=4,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="owner",
        role_briefing=state.briefings_by_agent["owner"],
        current_business_context="Review steel delivery outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S01_DELIVERY_OUTCOME",
                summary="Steel delivery realized at tick 16; contract baseline was tick 14.",
                possible_counterparty_ids=["steel_supplier"],
                diagnosticity="delivery_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["owner"],
        private_memory="",
    )
    compact_response = json.dumps(
        {
            "decisions_by_node": {},
            "parameters_by_node": {},
            "communications": [],
            "assessment_updates": [
                {
                    "evidence_id": "S01_DELIVERY_OUTCOME",
                    "counterparty_id": "steel_supplier",
                    "performance_reliability": 0.75,
                    "information_reliability": 0.75,
                    "contractual_reliability": 0.75,
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Late delivery does not change my score because the cause is not clear.",
        }
    )
    policy = LLMPolicy(FakeAdapter([compact_response]), "owner", prompt_style="gemma_compact")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates == []
    assert submission.assessment_reviews[0].evidence_ids == ["S01_DELIVERY_OUTCOME"]


def test_llm_policy_normalizes_dimension_specific_assessment_update() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=4,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="owner",
        role_briefing=state.briefings_by_agent["owner"],
        current_business_context="Review steel delivery outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S01_DELIVERY_OUTCOME",
                summary="Steel delivery realized at tick 14; contract baseline was tick 14.",
                possible_counterparty_ids=["steel_supplier"],
                diagnosticity="delivery_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["owner"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "steel_supplier",
                    "evidence_id": "S01_DELIVERY_OUTCOME",
                    "assessment_dimension": "performance_reliability",
                    "prior_score": 0.75,
                    "updated_score": 0.85,
                    "rationale": "On-time delivery under shock improves delivery reliability.",
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Supplier performed well.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "owner")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates[0].prior.performance_reliability == 0.75
    assert submission.assessment_updates[0].updated.performance_reliability == 0.85


def test_llm_policy_normalizes_flat_trust_score_assessment_update() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=4,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="owner",
        role_briefing=state.briefings_by_agent["owner"],
        current_business_context="Review steel delivery outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S01_DELIVERY_OUTCOME",
                summary="Steel delivery realized at tick 14; contract baseline was tick 14.",
                possible_counterparty_ids=["steel_supplier"],
                diagnosticity="delivery_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["owner"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "steel_supplier",
                    "evidence_ids": ["S01_DELIVERY_OUTCOME"],
                    "contractual_reliability": 0.85,
                    "performance_reliability": 0.85,
                    "information_reliability": 0.75,
                    "reason": "On-time steel delivery under shock improves supplier assessment.",
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Supplier performed well.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "owner")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates[0].updated.contractual_reliability == 0.85


def test_llm_policy_infers_single_assessment_evidence_id() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=4,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="gc",
        role_briefing=state.briefings_by_agent["gc"],
        current_business_context="Review payment outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S03_PAYMENT_OUTCOME",
                summary="Owner payment arrived late.",
                possible_counterparty_ids=["owner"],
                diagnosticity="payment_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["gc"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "owner",
                    "contractual_reliability": 0.55,
                    "information_reliability": 0.60,
                    "performance_reliability": 0.50,
                    "rationale": "Late payment reduces confidence.",
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Owner paid late.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "gc")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates[0].evidence_ids == ["S03_PAYMENT_OUTCOME"]


def test_llm_policy_merges_dimension_alias_updates() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=4,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="gc",
        role_briefing=state.briefings_by_agent["gc"],
        current_business_context="Review payment outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S03_PAYMENT_OUTCOME",
                summary="Owner payment arrived late.",
                possible_counterparty_ids=["owner"],
                diagnosticity="payment_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["gc"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "owner",
                    "dimension": "contractual_reliability",
                    "prior_score": 0.75,
                    "updated_score": 0.55,
                    "evidence_ids": ["S03_PAYMENT_OUTCOME"],
                    "rationale": "Late payment reduces contract confidence.",
                },
                {
                    "counterparty_id": "owner",
                    "dimension": "information_reliability",
                    "prior_score": 0.75,
                    "updated_score": 0.60,
                    "evidence_ids": ["S03_PAYMENT_OUTCOME"],
                    "rationale": "Funding timing claims were unreliable.",
                },
            ],
            "assessment_reviews": [],
            "private_notes": "Owner paid late.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "gc")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert len(submission.assessment_updates) == 1
    update = submission.assessment_updates[0].updated
    assert update.contractual_reliability == 0.55
    assert update.information_reliability == 0.60
    assert update.performance_reliability == 0.75


def test_llm_policy_normalizes_score_dimension_alias_update() -> None:
    scenario = get_scenario("S05")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=5,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="labor_subcontractor",
        role_briefing=state.briefings_by_agent["labor_subcontractor"],
        current_business_context="Review labor inspection outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S05_LABOR_INSPECTION_OUTCOME",
                summary="Labor task finished and inspection passed.",
                possible_counterparty_ids=["gc", "inspector"],
                diagnosticity="inspection_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["labor_subcontractor"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "gc",
                    "evidence_ids": ["S05_LABOR_INSPECTION_OUTCOME"],
                    "score_dimension": "performance_reliability",
                    "updated_score": 0.82,
                    "rationale": "GC accepted the recovery plan and kept inspection on path.",
                },
                {
                    "counterparty_id": "inspector",
                    "evidence_ids": ["S05_LABOR_INSPECTION_OUTCOME"],
                    "dimension": "performance_reliability",
                    "new_score": 0.80,
                    "rationale": "Inspector preserved the reserved inspection slot.",
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Outcome supports confidence in GC coordination.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "labor_subcontractor")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates[0].updated.performance_reliability == 0.82
    assert submission.assessment_updates[1].updated.performance_reliability == 0.80


def test_llm_policy_normalizes_nested_score_updates_aliases_and_no_op_review() -> None:
    scenario = get_scenario("S04")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=10,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="labor_subcontractor",
        role_briefing=state.briefings_by_agent["labor_subcontractor"],
        current_business_context="Review compliance outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S04_COMPLIANCE_OUTCOME",
                summary="The weld remediation was completed and the inspector released the work.",
                possible_counterparty_ids=["gc", "inspector", "lender"],
                diagnosticity="compliance_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["labor_subcontractor"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_id": "gc",
                    "evidence_ids": ["S04_COMPLIANCE_OUTCOME"],
                    "score_updates": {
                        "performance_reliability": 0.82,
                        "information_reliability": 0.78,
                        "contractual_reliability": 0.80,
                    },
                    "rationale": "GC coordinated remediation through final release.",
                },
                {
                    "counterparty_id": "lender",
                    "evidence_ids": ["S04_COMPLIANCE_OUTCOME"],
                    "updated_scores": {
                        "performance_reliability": 0.75,
                        "information_reliability": 0.75,
                        "contractual_reliability": 0.75,
                    },
                    "rationale": "The compliance outcome did not change my lender assessment.",
                },
            ],
            "assessment_reviews": [],
            "private_notes": "Outcome differentiates GC coordination from unrelated lender behavior.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "labor_subcontractor")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert submission.assessment_updates[0].updated.performance_reliability == 0.82
    assert submission.assessment_reviews[0].counterparty_ids == ["lender"]


def test_llm_policy_splits_multi_counterparty_assessment_update() -> None:
    scenario = get_scenario("S05")
    state = scenario.create_state(run_id="test", variant="normal")
    observation = AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=5,
        phase_id="final_assessment",
        phase_type="assessment_phase",
        agent_id="inspector",
        role_briefing=state.briefings_by_agent["inspector"],
        current_business_context="Review labor inspection outcome.",
        known_facts=[],
        received_messages=[],
        required_decisions=[],
        assessment_evidence=[
            AssessmentEvidence(
                evidence_id="S05_LABOR_INSPECTION_OUTCOME",
                summary="Labor task finished and inspection passed.",
                possible_counterparty_ids=["labor_subcontractor", "gc"],
                diagnosticity="inspection_outcome",
            )
        ],
        trust_prior_by_counterparty=state.trust_state["inspector"],
        private_memory="",
    )
    response = json.dumps(
        {
            "decisions": [],
            "communications": [],
            "assessment_updates": [
                {
                    "counterparty_ids": ["labor_subcontractor", "gc"],
                    "evidence_ids": ["S05_LABOR_INSPECTION_OUTCOME"],
                    "assessment_dimension": "performance_reliability",
                    "prior_score": 0.75,
                    "updated_score": 0.82,
                    "rationale": "Both parties executed the recovery path.",
                }
            ],
            "assessment_reviews": [],
            "private_notes": "Outcome supports confidence.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "inspector")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    assert [update.counterparty_id for update in submission.assessment_updates] == [
        "labor_subcontractor",
        "gc",
    ]


def test_validation_accepts_current_source_alias_for_current_standard() -> None:
    observation = _supplier_observation()
    response = json.dumps(
        {
            "decisions_by_node": {
                "S01_SUPPLIER_SOURCE_PLAN": "current_source",
                "S01_SUPPLIER_COMMERCIAL_REQUEST": "__parameters__",
            },
            "parameters_by_node": {
                "S01_SUPPLIER_COMMERCIAL_REQUEST": {
                    "price_amendment_request": 600000,
                    "delivery_date_amendment_request": 18,
                    "advance_payment_request": 0,
                }
            },
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Current source standard delivery means tick 18.",
        }
    )
    policy = LLMPolicy(FakeAdapter([response]), "steel_supplier", prompt_style="gemma_compact")

    submission = policy.decide(observation)

    assert _validate_submission(observation, submission) == []
    source_plan = next(
        decision for decision in submission.decisions if decision.node_id == "S01_SUPPLIER_SOURCE_PLAN"
    )
    assert source_plan.option_id == "current_standard"
