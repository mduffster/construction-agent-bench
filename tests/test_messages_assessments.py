from __future__ import annotations

from constructbench.agents import ScriptedPolicy, communication
from constructbench.runner import run_policy
from constructbench.scenarios import SCENARIOS
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    AssessmentUpdate,
    TrustValues,
)


def test_private_message_delivered_only_to_recipients() -> None:
    scenario = SCENARIOS["S01"]
    fixture = scenario.fixtures["normal_success"]
    policy = ScriptedPolicy(
        fixture["decisions"],
        communications_by_phase_agent={
            ("supplier_source_and_commercial", "steel_supplier"): [
                communication(
                    "private_message",
                    recipient_ids=["gc"],
                    summary="Delivery forecast remains tick 14.",
                    claims=[{"field": "forecast_delivery_tick", "value": 14}],
                )
            ]
        },
    )
    result = run_policy(
        "S01",
        "normal",
        {agent_id: policy for agent_id in AGENT_IDS},
    )
    state = result.final_state

    assert state.run_valid
    assert len(state.messages_by_agent["gc"]) == 1
    assert state.messages_by_agent["owner"] == []
    assert state.messages_by_agent["inspector"] == []
    assert state.histories["message_history"][0]["communication_type"] == "private_message"


class OwnerAssessmentUpdatePolicy(ScriptedPolicy):
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        submission = super().decide(observation)
        if observation.phase_type == "assessment_phase" and observation.agent_id == "owner":
            prior = observation.trust_prior_by_counterparty["steel_supplier"]
            submission.assessment_reviews = []
            submission.assessment_updates = [
                AssessmentUpdate(
                    counterparty_id="steel_supplier",
                    evidence_ids=[observation.assessment_evidence[0].evidence_id],
                    prior=TrustValues(
                        performance_reliability=prior.performance_reliability,
                        information_reliability=prior.information_reliability,
                        contractual_reliability=prior.contractual_reliability,
                    ),
                    updated=TrustValues(
                        performance_reliability=0.5,
                        information_reliability=0.6,
                        contractual_reliability=0.7,
                    ),
                    reason="The final delivery evidence changed owner expectations for the supplier.",
                )
            ]
        return submission


def test_assessment_updates_are_private_and_directed() -> None:
    scenario = SCENARIOS["S01"]
    fixture = scenario.fixtures["normal_success"]
    policy = OwnerAssessmentUpdatePolicy(fixture["decisions"])

    result = run_policy(
        "S01",
        "normal",
        {agent_id: policy for agent_id in AGENT_IDS},
    )
    state = result.final_state

    assert state.run_valid
    assert state.trust_state["owner"]["steel_supplier"].performance_reliability == 0.5
    assert state.trust_state["gc"]["steel_supplier"].performance_reliability == 0.75
    assert state.histories["assessment_history"][0]["assessor_id"] == "owner"
