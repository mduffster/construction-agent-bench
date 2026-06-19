"""Agent submission validation."""

from __future__ import annotations

from constructbench.enums import AgentRole, CommunicationVisibility, DecisionType
from constructbench.models import AgentObservation, AgentSubmission, StateStore, ValidationResult


class SubmissionValidator:
    """Validate role permissions for already parsed AgentSubmission objects."""

    def validate(
        self,
        agent_id: str,
        submission: AgentSubmission,
        state: StateStore,
        observation: AgentObservation | None = None,
    ) -> ValidationResult:
        try:
            role = AgentRole(agent_id)
        except ValueError:
            return ValidationResult(valid=False, errors=[f"unknown_agent:{agent_id}"])

        if role not in state.role_configs:
            return ValidationResult(valid=False, errors=[f"missing_role_config:{agent_id}"])

        role_config = state.role_configs[role]
        errors: list[str] = []

        decision = submission.decision
        if decision.type != DecisionType.NONE:
            permitted = [
                item
                for item in role_config.permitted_decisions
                if item.decision_type == decision.type
            ]
            if not permitted:
                errors.append(f"decision_type_not_permitted:{decision.type.value}")
            elif decision.object_type is not None and not any(
                decision.object_type in item.object_types
                for item in permitted
            ):
                errors.append(f"object_type_not_permitted:{decision.object_type}")
            if observation is not None:
                errors.extend(self._validate_decision_menu_option(submission, observation))

        if submission.communication is not None:
            communication = submission.communication
            if communication.visibility == CommunicationVisibility.PRIVATE:
                invalid_recipients = [
                    recipient.value
                    for recipient in communication.recipients
                    if recipient not in state.role_configs
                ]
                if invalid_recipients:
                    errors.append(
                        "invalid_private_recipients:" + ",".join(sorted(invalid_recipients)),
                    )
                if not communication.recipients:
                    errors.append("private_communication_requires_recipient")

        for assessment in submission.counterparty_assessments:
            if assessment.target not in state.role_configs:
                errors.append(f"unknown_counterparty_assessment_target:{assessment.target.value}")

        received_evidence_ids = {
            evidence.evidence_id
            for evidence in (observation.received_evidence if observation is not None else [])
        }
        for update in submission.counterparty_expectation_updates:
            if update.target not in state.role_configs:
                errors.append(f"unknown_counterparty_expectation_target:{update.target.value}")
            if update.target == role:
                errors.append("counterparty_expectation_cannot_target_self")
            if observation is not None:
                for evidence in update.evidence_assessment:
                    if evidence.evidence_id not in received_evidence_ids:
                        errors.append(
                            f"unknown_expectation_evidence_id:{evidence.evidence_id}",
                        )
                for basis_id in update.basis_ids:
                    if basis_id not in received_evidence_ids:
                        errors.append(f"unknown_expectation_basis_id:{basis_id}")

        return ValidationResult(valid=not errors, errors=errors)

    def _validate_decision_menu_option(
        self,
        submission: AgentSubmission,
        observation: AgentObservation,
    ) -> list[str]:
        decision = submission.decision
        if decision.type == DecisionType.NONE:
            return []

        matching_options = [
            option
            for option in observation.decision_menu_options
            if option.decision_type == decision.type
            and (
                decision.object_type is None
                or option.object_type == decision.object_type
            )
            and (
                decision.object_id is None
                or option.object_id is None
                or option.object_id == decision.object_id
            )
        ]
        option_id = decision.parameters.get("option_id")
        if not matching_options and option_id is None:
            return []
        if not isinstance(option_id, str):
            return ["decision_menu_option_required"]
        visible_option = next(
            (
                option
                for option in observation.decision_menu_options
                if option.option_id == option_id
            ),
            None,
        )
        if visible_option is None:
            return [f"decision_menu_option_not_visible:{option_id}"]
        errors: list[str] = []
        if visible_option.decision_type != decision.type:
            errors.append(f"decision_menu_type_mismatch:{option_id}")
        if visible_option.object_type != decision.object_type:
            errors.append(f"decision_menu_object_type_mismatch:{option_id}")
        if (
            decision.object_id is not None
            and visible_option.object_id is not None
            and visible_option.object_id != decision.object_id
        ):
            errors.append(f"decision_menu_object_id_mismatch:{option_id}")
        return errors
