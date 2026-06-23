from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from constructbench.state import (
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    Claim,
    Communication,
    DecisionSelection,
    RunState,
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
        communications = list(self.communications_by_phase_agent.get(key, []))
        if observation.submission_contract.require_explicit_communication and not communications:
            communications = [
                Communication(
                    communication_type="no_communication",
                    summary="Scripted policy chooses not to send a message this turn.",
                )
            ]
        reviews = [
            AssessmentReview(
                evidence_ids=[evidence.evidence_id],
                counterparty_ids=list(evidence.possible_counterparty_ids),
                reason="Scripted witness records no directed assessment change for this evidence.",
            )
            for evidence in observation.assessment_evidence
        ]
        if (
            observation.submission_contract.require_explicit_assessment_choice
            and not reviews
        ):
            reviews = [
                AssessmentReview(
                    evidence_ids=[],
                    counterparty_ids=[],
                    reason="Scripted witness records no directed assessment change this turn.",
                )
            ]
        return AgentSubmission(
            decisions=selections,
            communications=communications,
            assessment_reviews=reviews,
            private_notes=self.private_notes_by_phase_agent.get(key, ""),
        )


class SingleSubmissionPolicy:
    def __init__(self, submission: AgentSubmission) -> None:
        self.submission = submission

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        return self.submission


class ReplayPolicy:
    def __init__(
        self,
        submissions_by_phase_agent: Mapping[
            tuple[str, str],
            AgentSubmission | dict[str, Any],
        ],
    ) -> None:
        self.submissions_by_phase_agent = {
            key: (
                submission.model_copy(deep=True)
                if isinstance(submission, AgentSubmission)
                else AgentSubmission.model_validate(submission)
            )
            for key, submission in submissions_by_phase_agent.items()
        }

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        submission = self.submissions_by_phase_agent.get(
            (observation.phase_id, observation.agent_id)
        )
        if submission is None:
            return AgentSubmission()
        return submission.model_copy(deep=True)


def replay_submissions_for_agent(
    state: RunState,
    agent_id: str,
) -> dict[tuple[str, str], AgentSubmission]:
    submissions: dict[tuple[str, str], AgentSubmission] = {}
    for record in state.histories.get("agent_submission_history", []):
        if record.get("agent_id") != agent_id:
            continue
        key = (str(record["phase_id"]), str(record["agent_id"]))
        if key in submissions:
            raise ValueError(f"duplicate replay submission for {key}")
        submissions[key] = AgentSubmission.model_validate(record["submission"])
    return submissions


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
    required_proposition_ids: list[str] | None = None,
    withheld_proposition_ids: list[str] | None = None,
    decision_record_id: str | None = None,
) -> Communication:
    return Communication(
        communication_type=communication_type,  # type: ignore[arg-type]
        recipient_ids=recipient_ids or [],
        summary=summary,
        claims=[Claim.model_validate(claim) for claim in (claims or [])],
        required_proposition_ids=required_proposition_ids or [],
        withheld_proposition_ids=withheld_proposition_ids or [],
        decision_record_id=decision_record_id,
    )
