from pathlib import Path

import pytest
from pydantic import ValidationError

from constructbench.agents import LLMPolicy
from constructbench.config import load_agent_configs, load_project_config
from constructbench.enums import AgentRole, AssessmentUpdateMode, DecisionType
from constructbench.models import (
    AgentBeliefState,
    AgentRuntimeRecord,
    AgentSubmission,
    AgentTurnResult,
    CommercialResponse,
    CounterpartyExpectationAssessment,
    DecisionSubmission,
    DeliveredEvents,
    EvidenceAssessment,
    ExpectationDimensions,
    ModelSettings,
    PrivateMessage,
    StateStore,
    ValidationResult,
)
from constructbench.observations import ObservationBuilder
from constructbench.state import initialize_state
from constructbench.transitions import TransitionResolver
from constructbench.validation import SubmissionValidator

ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, settings: ModelSettings) -> str:
        self.prompts.append(prompt)
        return """
        {
          "decision": {"type": "none", "object_type": null, "object_id": null, "parameters": {}},
          "communication": null,
          "belief_update": {
            "expected_completion_tick": 40,
            "expected_final_cost": 95000000,
            "probability_on_time": 0.85,
            "probability_within_budget": 0.85,
            "confidence": 0.8,
            "basis_ids": ["baseline_plan"]
          },
          "counterparty_expectation_updates": []
        }
        """


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def _belief() -> AgentBeliefState:
    return AgentBeliefState(
        expected_completion_tick=40,
        expected_final_cost=95_000_000,
        probability_on_time=0.85,
        probability_within_budget=0.85,
        confidence=0.8,
        basis_ids=["baseline_plan"],
    )


def test_dimensional_assessment_validates_probability_and_unchanged_reason() -> None:
    with pytest.raises(ValidationError):
        CounterpartyExpectationAssessment(
            target=AgentRole.STEEL_SUPPLIER,
            updated_assessment=ExpectationDimensions(delivery_reliability=1.2),
            changed_from_prior=True,
            rationale="Invalid probability.",
        )

    with pytest.raises(ValidationError):
        CounterpartyExpectationAssessment(
            target=AgentRole.STEEL_SUPPLIER,
            updated_assessment=ExpectationDimensions(),
            changed_from_prior=False,
            rationale="No movement but no reason.",
        )


def test_initial_directed_expectations_start_at_prior_and_are_separate() -> None:
    state = _state()

    gc_to_supplier = state.expectations_by_agent[AgentRole.GENERAL_CONTRACTOR][
        AgentRole.STEEL_SUPPLIER
    ]
    scalar = state.agent_trust_by_agent[AgentRole.GENERAL_CONTRACTOR][
        AgentRole.STEEL_SUPPLIER
    ]

    assert gc_to_supplier.assessment.delivery_reliability == 0.75
    assert gc_to_supplier.assessment.reporting_integrity == 0.75
    assert scalar.score == 0.75
    assert id(state.expectations_by_agent) != id(state.agent_trust_by_agent)


def test_structured_observation_includes_prior_and_current_evidence_ids() -> None:
    state = _state()
    message = PrivateMessage(
        message_id="steel_supplier_disclosure_tick_10",
        tick=9,
        sender=AgentRole.STEEL_SUPPLIER,
        recipients=[AgentRole.GENERAL_CONTRACTOR],
        summary="Steel delivery forecast moved to tick 18.",
        linked_object_id="steel_contract",
    )
    delivered = DeliveredEvents(
        private_messages_by_agent={AgentRole.GENERAL_CONTRACTOR: [message]},
    )

    structured = ObservationBuilder(
        assessment_update_mode=AssessmentUpdateMode.STRUCTURED_DIMENSIONAL,
    ).build(AgentRole.GENERAL_CONTRACTOR, state, delivered)
    scalar = ObservationBuilder(
        assessment_update_mode=AssessmentUpdateMode.SCALAR_BASELINE,
    ).build(AgentRole.GENERAL_CONTRACTOR, state, delivered)

    assert AgentRole.STEEL_SUPPLIER in structured.counterparty_expectations
    assert structured.received_evidence[0].evidence_id == "steel_supplier_disclosure_tick_10"
    assert structured.commercial_response_options[AgentRole.STEEL_SUPPLIER].allow_advance_payment
    assert structured.assessment_update_mode == AssessmentUpdateMode.STRUCTURED_DIMENSIONAL
    assert scalar.counterparty_expectations == {}
    assert scalar.received_evidence == []


def test_validation_rejects_unknown_evidence_id_for_structured_update() -> None:
    state = _state()
    observation = ObservationBuilder(
        assessment_update_mode=AssessmentUpdateMode.STRUCTURED_DIMENSIONAL,
    ).build(AgentRole.GENERAL_CONTRACTOR, state, DeliveredEvents())
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=None,
        belief_update=_belief(),
        counterparty_expectation_updates=[
            CounterpartyExpectationAssessment(
                target=AgentRole.STEEL_SUPPLIER,
                updated_assessment=ExpectationDimensions(delivery_reliability=0.6),
                evidence_assessment=[
                    EvidenceAssessment(
                        evidence_id="missing_evidence",
                        relevant_dimensions=["delivery_reliability"],
                        causal_attribution="mostly_counterparty",
                        diagnosticity="high",
                    ),
                ],
                basis_ids=["missing_evidence"],
                changed_from_prior=True,
                commercial_response=CommercialResponse(require_performance_bond=True),
                rationale="Update cites evidence not delivered this tick.",
            ),
        ],
    )

    result = SubmissionValidator().validate(
        AgentRole.GENERAL_CONTRACTOR.value,
        submission,
        state,
        observation,
    )

    assert result.valid is False
    assert "unknown_expectation_evidence_id:missing_evidence" in result.errors
    assert "unknown_expectation_basis_id:missing_evidence" in result.errors


def test_expectation_update_affects_only_observer_target_dyad() -> None:
    state = _state()
    observation = ObservationBuilder().build(AgentRole.GENERAL_CONTRACTOR, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=None,
        belief_update=_belief(),
        counterparty_expectation_updates=[
            CounterpartyExpectationAssessment(
                target=AgentRole.STEEL_SUPPLIER,
                updated_assessment=ExpectationDimensions(
                    delivery_reliability=0.55,
                    reporting_integrity=0.78,
                ),
                changed_from_prior=True,
                commercial_response=CommercialResponse(
                    require_performance_bond=True,
                    required_reporting_interval_ticks=1,
                    allow_advance_payment=False,
                ),
                rationale="Proactive delay disclosure reduces delivery confidence.",
            ),
        ],
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.GENERAL_CONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(AgentTurnResult(tick=10, records=[record]), state)

    updated = state.expectations_by_agent[AgentRole.GENERAL_CONTRACTOR][
        AgentRole.STEEL_SUPPLIER
    ]
    reverse = state.expectations_by_agent[AgentRole.STEEL_SUPPLIER][
        AgentRole.GENERAL_CONTRACTOR
    ]
    scalar = state.agent_trust_by_agent[AgentRole.GENERAL_CONTRACTOR][
        AgentRole.STEEL_SUPPLIER
    ]

    assert updated.assessment.delivery_reliability == 0.55
    assert updated.assessment.reporting_integrity == 0.78
    assert reverse.assessment.delivery_reliability == 0.75
    assert scalar.score == 0.75
    assert state.expectation_update_records[0].delivery_reliability_delta == pytest.approx(-0.2)
    assert state.expectation_update_records[0].commercial_response.require_performance_bond


def test_structured_prompt_describes_dimensional_update_requirements() -> None:
    state = _state()
    observation = ObservationBuilder(
        assessment_update_mode=AssessmentUpdateMode.STRUCTURED_DIMENSIONAL,
    ).build(AgentRole.GENERAL_CONTRACTOR, state, DeliveredEvents())
    adapter = FakeAdapter()
    policy = LLMPolicy(adapter=adapter, settings=ModelSettings(model_id="fake"))

    policy.decide(observation)

    assert "assessment_update_mode is structured_dimensional" in adapter.prompts[0]
    assert "delivery_reliability" in adapter.prompts[0]
    assert "reporting_integrity" in adapter.prompts[0]
    assert "unchanged_reason" in adapter.prompts[0]
