from __future__ import annotations

from typing import Protocol

from constructbench.state import (
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    Claim,
    Communication,
    DecisionSelection,
)


class AgentPolicy(Protocol):
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        ...


class EmptyPolicy:
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        return AgentSubmission()


class ScriptedPolicy:
    def __init__(
        self,
        decisions_by_node: dict[str, tuple[str, dict]],
        *,
        communications_by_phase_agent: dict[tuple[str, str], list[Communication]] | None = None,
        private_notes_by_phase_agent: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.decisions_by_node = decisions_by_node
        self.communications_by_phase_agent = communications_by_phase_agent or {}
        self.private_notes_by_phase_agent = private_notes_by_phase_agent or {}

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        selections: list[DecisionSelection] = []
        for request in observation.required_decisions:
            if request.node_id not in self.decisions_by_node:
                continue
            option_id, parameters = self.decisions_by_node[request.node_id]
            selections.append(
                DecisionSelection(
                    node_id=request.node_id,
                    option_id=None if option_id == "__parameters__" else option_id,
                    parameters=dict(parameters),
                )
            )
        key = (observation.phase_id, observation.agent_id)
        reviews = [
            AssessmentReview(
                evidence_ids=[evidence.evidence_id],
                counterparty_ids=list(evidence.possible_counterparty_ids),
                reason="Scripted witness records no directed assessment change for this evidence.",
            )
            for evidence in observation.assessment_evidence
        ]
        return AgentSubmission(
            decisions=selections,
            communications=list(self.communications_by_phase_agent.get(key, [])),
            assessment_reviews=reviews,
            private_notes=self.private_notes_by_phase_agent.get(key, ""),
        )


class SingleSubmissionPolicy:
    def __init__(self, submission: AgentSubmission) -> None:
        self.submission = submission

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        return self.submission


def policies_for_fixture(decisions_by_node: dict[str, tuple[str, dict]]) -> dict[str, AgentPolicy]:
    policy = ScriptedPolicy(decisions_by_node)
    return {
        "owner": policy,
        "gc": policy,
        "steel_supplier": policy,
        "labor_subcontractor": policy,
        "lender": policy,
        "inspector": policy,
    }


def communication(
    communication_type: str,
    *,
    recipient_ids: list[str] | None = None,
    summary: str = "",
    claims: list[dict] | None = None,
    decision_record_id: str | None = None,
) -> Communication:
    return Communication(
        communication_type=communication_type,  # type: ignore[arg-type]
        recipient_ids=recipient_ids or [],
        summary=summary,
        claims=[
            Claim(
                subject_id=claim.get("subject_id"),
                field=claim["field"],
                value=claim["value"],
            )
            for claim in (claims or [])
        ],
        decision_record_id=decision_record_id,
    )
