"""Deterministic transition resolution for validated agent submissions."""

from __future__ import annotations

from typing import Any

from constructbench.enums import (
    AgentRole,
    CommunicationVisibility,
    DecisionType,
    InspectionStatus,
    LedgerEntryType,
    PaymentStatus,
    TaskStatus,
)
from constructbench.models import (
    AgentRuntimeRecord,
    AgentTrustAssessmentRecord,
    AgentTurnResult,
    AppliedTransition,
    Claim,
    CounterpartyExpectationUpdateRecord,
    Inspection,
    Payment,
    PrivateMessage,
    PrivateMessageEnvelope,
    PublicLedgerEntry,
    StateStore,
    TransitionResult,
)


class TransitionResolver:
    """Apply valid, structured submissions to harness-owned state."""

    def apply(
        self,
        agent_turn: AgentTurnResult,
        state: StateStore,
        message_delay_ticks: int = 1,
    ) -> TransitionResult:
        result = TransitionResult(tick=agent_turn.tick)
        for record in agent_turn.records:
            self._reset_resolved_parameters(record)
            if not record.validation.valid:
                result.rejected.append(
                    {
                        "agent_id": record.agent_id.value,
                        "errors": record.validation.errors,
                    },
                )
                continue

            self._apply_counterparty_assessments(record, state, result)
            self._apply_counterparty_expectation_updates(record, state, result)
            self._apply_communication(record, state, result, message_delay_ticks)
            self._apply_decision(record, state, result)

        return result

    def _reset_resolved_parameters(self, record: AgentRuntimeRecord) -> None:
        record.submission.decision_parameters_used = {}

    def _apply_counterparty_assessments(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        for index, assessment in enumerate(record.submission.counterparty_assessments):
            if assessment.target == record.agent_id:
                continue
            trust_state = state.agent_trust_by_agent.get(record.agent_id, {}).get(
                assessment.target,
            )
            if trust_state is None:
                continue
            trust_state.score = assessment.trust_score
            for basis_id in assessment.basis_ids:
                if basis_id not in trust_state.basis_ids:
                    trust_state.basis_ids.append(basis_id)
            assessment_record = AgentTrustAssessmentRecord(
                assessment_id=self._id(
                    "agent_trust",
                    result.tick,
                    record.agent_id.value,
                    len(state.agent_trust_assessments) + index,
                ),
                tick=result.tick,
                observer=record.agent_id,
                target=assessment.target,
                trust_score=assessment.trust_score,
                confidence=assessment.confidence,
                basis_ids=assessment.basis_ids,
                reason=assessment.reason,
            )
            state.agent_trust_assessments.append(assessment_record)
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="agent_trust_assessed",
                    target_store="private",
                    object_id=assessment_record.assessment_id,
                    description="Updated agent-owned counterparty trust assessment.",
                ),
            )

    def _apply_counterparty_expectation_updates(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        for index, update in enumerate(record.submission.counterparty_expectation_updates):
            if update.target == record.agent_id:
                continue
            expectation_state = state.expectations_by_agent.get(record.agent_id, {}).get(
                update.target,
            )
            if expectation_state is None:
                continue

            previous = expectation_state.assessment.model_copy(deep=True)
            posterior = update.updated_assessment.model_copy(deep=True)
            expectation_state.assessment = posterior
            for basis_id in update.basis_ids:
                if basis_id not in expectation_state.basis_ids:
                    expectation_state.basis_ids.append(basis_id)

            update_record = CounterpartyExpectationUpdateRecord(
                update_id=self._id(
                    "expectation",
                    result.tick,
                    record.agent_id.value,
                    len(state.expectation_update_records) + index,
                ),
                tick=result.tick,
                observer=record.agent_id,
                target=update.target,
                mode=update.mode,
                previous_assessment=previous,
                updated_assessment=posterior,
                delivery_reliability_delta=(
                    posterior.delivery_reliability - previous.delivery_reliability
                ),
                reporting_integrity_delta=(
                    posterior.reporting_integrity - previous.reporting_integrity
                ),
                evidence_assessment=update.evidence_assessment,
                basis_ids=update.basis_ids,
                changed_from_prior=update.changed_from_prior,
                unchanged_reason=update.unchanged_reason,
                commercial_response=update.commercial_response,
                rationale=update.rationale,
            )
            state.expectation_update_records.append(update_record)
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="counterparty_expectation_updated",
                    target_store="private",
                    object_id=update_record.update_id,
                    description="Updated directed dimensional counterparty expectation.",
                ),
            )

    def _apply_communication(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
        message_delay_ticks: int,
    ) -> None:
        communication = record.submission.communication
        if communication is None:
            return

        if communication.visibility == CommunicationVisibility.PUBLIC:
            entry = self._public_entry(
                tick=result.tick,
                source=record.agent_id.value,
                entry_type=LedgerEntryType.AGENT_CLAIM,
                linked_object_id=communication.linked_object_id,
                data={"summary": communication.summary},
                claims=communication.claims,
                index=len(state.public.ledger),
            )
            state.public.ledger.append(entry)
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="public_communication",
                    target_store="public",
                    object_id=entry.entry_id,
                    description="Published public communication to the ledger.",
                ),
            )
            return

        message = PrivateMessage(
            message_id=self._id(
                "message",
                result.tick,
                record.agent_id.value,
                len(state.private_messages),
            ),
            tick=result.tick,
            sender=record.agent_id,
            recipients=communication.recipients,
            summary=communication.summary,
            linked_object_id=communication.linked_object_id,
            claims=communication.claims,
        )
        state.private_messages.append(
            PrivateMessageEnvelope(
                message=message,
                deliver_tick=result.tick + message_delay_ticks,
            ),
        )
        result.applied.append(
            AppliedTransition(
                agent_id=record.agent_id,
                transition_type="private_message_queued",
                target_store="private",
                object_id=message.message_id,
                description="Queued private message for configured delivery tick.",
            ),
        )

    def _apply_decision(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        decision = record.submission.decision
        if decision.type == DecisionType.NONE:
            return

        if decision.type == DecisionType.SUBMIT_FORECAST:
            self._apply_forecast(record, state, result)
        elif decision.type == DecisionType.SCHEDULE:
            self._apply_schedule(record, state, result)
        elif decision.type == DecisionType.INSPECT:
            self._apply_inspection(record, state, result)
        elif decision.type == DecisionType.PAY:
            self._apply_payment(record, state, result)
        elif decision.type in {DecisionType.REQUEST_INFORMATION, DecisionType.SUBMIT_REQUEST}:
            self._apply_request(record, state, result)
        elif decision.type in {
            DecisionType.APPROVE,
            DecisionType.REJECT,
            DecisionType.DECLARE_STATUS,
        }:
            self._apply_status_decision(record, state, result)

    def _apply_forecast(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        decision = record.submission.decision
        task_id = self._task_id_from_decision(decision.object_id, decision.object_type, state)
        params = decision.parameters
        if task_id is not None:
            task = state.canonical.tasks[task_id]
            params = self._resolve_task_strategy(record, task_id, state)
            parameters_used: dict[str, Any] = {}
            forecast_tick = self._first_int(
                params,
                ("forecast_end_tick", "expected_delivery_tick", "expected_steel_delivery_tick"),
            )
            if forecast_tick is not None:
                parameters_used["forecast_end_tick"] = forecast_tick
            forecast_cost = self._first_int(params, ("forecast_cost", "expected_cost"))
            if forecast_cost is not None:
                parameters_used["forecast_cost"] = forecast_cost
            task_locked = self._task_locked_by_cascade(
                task_id,
                state,
            ) and not self._uses_menu_option(record)
            if forecast_tick is not None and not task_locked:
                task.forecast_end_tick = forecast_tick
            if forecast_cost is not None and forecast_cost >= 0 and not task_locked:
                task.forecast_cost = forecast_cost
            if parameters_used:
                record.submission.decision_parameters_used.update(parameters_used)
            if (forecast_tick is not None or forecast_cost is not None) and not task_locked:
                result.applied.append(
                    AppliedTransition(
                        agent_id=record.agent_id,
                        transition_type="task_forecast_updated",
                        target_store="canonical",
                        object_id=task_id,
                        description="Updated task forecast from structured forecast submission.",
                    ),
                )

        if task_id is None:
            self._apply_project_forecast(record, state, result)

        entry = self._public_entry(
            tick=result.tick,
            source=record.agent_id.value,
            entry_type=LedgerEntryType.PROJECT_FORECAST,
            linked_object_id=decision.object_id or decision.object_type,
            data={
                "decision": decision.model_dump(mode="json"),
                "belief_update": record.submission.belief_update.model_dump(mode="json"),
                "decision_parameters_used": record.submission.decision_parameters_used,
            },
            claims=[],
            index=len(state.public.ledger),
        )
        state.public.ledger.append(entry)
        result.applied.append(
            AppliedTransition(
                agent_id=record.agent_id,
                transition_type="forecast_published",
                target_store="public",
                object_id=entry.entry_id,
                description="Published forecast submission to the public ledger.",
            ),
        )

    def _apply_schedule(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        decision = record.submission.decision
        task_id = self._task_id_from_decision(decision.object_id, decision.object_type, state)
        if task_id is not None:
            task = state.canonical.tasks[task_id]
            params = self._resolve_task_strategy(record, task_id, state)
            start_tick = self._first_int(params, ("planned_start_tick", "start_tick"))
            end_tick = self._first_int(params, ("forecast_end_tick", "end_tick"))
            if start_tick is not None:
                task.planned_start_tick = start_tick
                record.submission.decision_parameters_used["planned_start_tick"] = start_tick
            if end_tick is not None:
                task.planned_end_tick = end_tick
                task.forecast_end_tick = end_tick
                record.submission.decision_parameters_used["planned_end_tick"] = end_tick
                record.submission.decision_parameters_used["forecast_end_tick"] = end_tick
            if task.status == TaskStatus.NOT_STARTED:
                task.status = TaskStatus.IN_PROGRESS
                record.submission.decision_parameters_used["status"] = task.status.value
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="task_schedule_updated",
                    target_store="canonical",
                    object_id=task_id,
                    description="Updated task schedule/status from schedule decision.",
                ),
            )

        self._publish_decision(record, state, result, LedgerEntryType.MILESTONE_STATUS)

    def _apply_inspection(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        decision = record.submission.decision
        task_id = self._task_id_from_decision(decision.object_id, decision.object_type, state)
        if task_id is not None:
            inspection_id = self._id(
                "inspection",
                result.tick,
                task_id,
                len(state.canonical.inspections),
            )
            params = self._resolve_inspection_strategy(record, state)
            status_value = params.get("status", InspectionStatus.REQUESTED.value)
            inspection = Inspection(
                inspection_id=inspection_id,
                task_id=task_id,
                requested_by=record.agent_id,
                status=InspectionStatus(status_value),
                scheduled_tick=self._first_int(params, ("scheduled_tick",)),
                completed_tick=self._first_int(params, ("completed_tick",)),
                outcome=params.get("outcome"),
            )
            state.canonical.inspections[inspection_id] = inspection
            record.submission.decision_parameters_used.update(
                {
                    "inspection_id": inspection_id,
                    "task_id": task_id,
                    "status": inspection.status.value,
                },
            )
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="inspection_recorded",
                    target_store="canonical",
                    object_id=inspection_id,
                    description="Recorded inspection decision.",
                ),
            )

        self._publish_decision(record, state, result, LedgerEntryType.INSPECTION_OUTCOME)

    def _apply_payment(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        decision = record.submission.decision
        amount = self._first_int(decision.parameters, ("amount", "payment_amount"))
        recipient = decision.parameters.get("recipient")
        if amount is not None and isinstance(recipient, str):
            recipient_role = AgentRole(recipient)
            payment_id = self._id(
                "payment",
                result.tick,
                record.agent_id.value,
                len(state.canonical.payments),
            )
            payment = Payment(
                payment_id=payment_id,
                payer=record.agent_id,
                recipient=recipient_role,
                amount=amount,
                due_tick=result.tick,
                status=PaymentStatus.PAID,
                paid_tick=result.tick,
                linked_contract_id=decision.object_id,
                data=decision.parameters,
            )
            state.canonical.payments[payment_id] = payment
            payer_finance = state.canonical.agent_finances.get(record.agent_id)
            recipient_finance = state.canonical.agent_finances.get(payment.recipient)
            if payer_finance is not None:
                payer_finance.cash_available -= amount
            if recipient_finance is not None:
                recipient_finance.cash_available += amount
            record.submission.decision_parameters_used.update(
                {
                    "payment_id": payment_id,
                    "amount": amount,
                    "recipient": recipient_role.value,
                },
            )
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="payment_recorded",
                    target_store="canonical",
                    object_id=payment_id,
                    description="Recorded payment and updated agent finances.",
                ),
            )

        self._publish_decision(record, state, result, LedgerEntryType.PAYMENT_CONFIRMATION)

    def _apply_request(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        self._apply_funding_delay(record, state, result)
        self._publish_decision(record, state, result, LedgerEntryType.AGENT_CLAIM)

    def _apply_status_decision(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        self._apply_funding_delay(record, state, result)
        self._publish_decision(record, state, result, LedgerEntryType.MILESTONE_STATUS)

    def _apply_project_forecast(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        params = self._resolve_project_strategy(record, state)
        completion_tick = self._first_int(
            params,
            ("forecast_completion_tick", "expected_completion_tick", "completion_tick"),
        )
        final_cost = self._first_int(
            params,
            ("forecast_final_cost", "expected_final_cost", "final_cost"),
        )

        project_locked = self._project_forecast_locked_by_cascade(
            state,
        ) and not self._uses_menu_option(record)
        changed = False
        if completion_tick is not None and not project_locked:
            state.canonical.forecast_completion_tick = completion_tick
            record.submission.decision_parameters_used["forecast_completion_tick"] = completion_tick
            changed = True
        if final_cost is not None and not project_locked:
            state.canonical.forecast_final_cost = final_cost
            record.submission.decision_parameters_used["forecast_final_cost"] = final_cost
            changed = True
        if completion_tick is not None and project_locked:
            record.submission.decision_parameters_used["forecast_completion_tick"] = completion_tick
        if final_cost is not None and project_locked:
            record.submission.decision_parameters_used["forecast_final_cost"] = final_cost
        if changed:
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="project_forecast_updated",
                    target_store="canonical",
                    object_id="project_forecast",
                    description="Updated project forecast from role forecast submission.",
                ),
            )

    def _publish_decision(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
        entry_type: LedgerEntryType,
    ) -> None:
        decision = record.submission.decision
        entry = self._public_entry(
            tick=result.tick,
            source=record.agent_id.value,
            entry_type=entry_type,
            linked_object_id=decision.object_id or decision.object_type,
            data={
                "decision": decision.model_dump(mode="json"),
                "decision_parameters_used": record.submission.decision_parameters_used,
            },
            claims=[],
            index=len(state.public.ledger),
        )
        state.public.ledger.append(entry)
        result.applied.append(
            AppliedTransition(
                agent_id=record.agent_id,
                transition_type="decision_published",
                target_store="public",
                object_id=entry.entry_id,
                description=f"Published {decision.type.value} decision to public ledger.",
            ),
        )

    def _public_entry(
        self,
        tick: int,
        source: str,
        entry_type: LedgerEntryType,
        linked_object_id: str | None,
        data: dict[str, Any],
        claims: list[Claim],
        index: int,
    ) -> PublicLedgerEntry:
        return PublicLedgerEntry(
            entry_id=self._id("public", tick, source, index),
            tick=tick,
            source=source,
            entry_type=entry_type,
            linked_object_id=linked_object_id,
            data=data,
            claims=claims,
        )

    def _uses_menu_option(self, record: AgentRuntimeRecord) -> bool:
        return isinstance(record.submission.decision.parameters.get("option_id"), str)

    def _task_locked_by_cascade(self, task_id: str, state: StateStore) -> bool:
        return any(
            event.linked_object_id == task_id
            and event.event_type in {"task_forecast_set", "task_delay_propagated"}
            for event in state.cascade_events
        )

    def _project_forecast_locked_by_cascade(self, state: StateStore) -> bool:
        return any(
            event.event_type in {"project_completion_propagated", "task_forecast_set"}
            for event in state.cascade_events
        )

    def _task_id_from_decision(
        self,
        object_id: str | None,
        object_type: str | None,
        state: StateStore,
    ) -> str | None:
        candidates = [value for value in (object_id, object_type) if value is not None]
        aliases = {
            "foundation": "foundation_work",
            "steel_installation": "steel_erection",
            "final": "final_inspection",
            "labor_crew": "steel_erection",
            "crew_schedule": "steel_erection",
        }
        for candidate in candidates:
            if candidate in state.canonical.tasks:
                return candidate
            if candidate in aliases and aliases[candidate] in state.canonical.tasks:
                return aliases[candidate]
        return None

    def _resolve_task_strategy(
        self,
        record: AgentRuntimeRecord,
        task_id: str,
        state: StateStore,
    ) -> dict[str, Any]:
        params = dict(record.submission.decision.parameters)
        if record.agent_id == AgentRole.STEEL_SUPPLIER and task_id == "steel_delivery":
            params.update(self._resolve_steel_expedite(record, state, params))
        if record.agent_id == AgentRole.LABOR_SUBCONTRACTOR and task_id == "steel_erection":
            params.update(self._resolve_labor_overtime(record, state, params))
        return params

    def _resolve_project_strategy(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
    ) -> dict[str, Any]:
        params = dict(record.submission.decision.parameters)
        if record.agent_id == AgentRole.GENERAL_CONTRACTOR:
            params.update(self._resolve_gc_acceleration(record, state, params))
        if record.agent_id == AgentRole.OWNER_DEVELOPER:
            params.update(self._resolve_owner_contingency(record, state, params))
        return params

    def _resolve_inspection_strategy(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
    ) -> dict[str, Any]:
        params = dict(record.submission.decision.parameters)
        if record.agent_id != AgentRole.INSPECTOR:
            return params
        strategy = str(params.get("strategy", "delay_for_evidence"))
        private_state = state.private_by_agent.get(record.agent_id)
        private = private_state.data if private_state is not None else {}
        delay = self._first_int(params, ("inspection_delay",))
        if delay is None:
            delay = self._first_int(private, ("inspection_delay",)) or 0
        if strategy == "request_rework":
            params.setdefault("status", InspectionStatus.REQUIRES_REWORK.value)
        elif strategy == "pass_if_supported":
            params.setdefault("status", InspectionStatus.PASSED.value)
        else:
            status = private.get("inspection_outcome_status", InspectionStatus.REQUESTED.value)
            params.setdefault("status", status)
        if delay > 0:
            closeout = state.canonical.tasks.get("closeout")
            if closeout is not None:
                closeout.forecast_end_tick = max(
                    closeout.forecast_end_tick,
                    closeout.planned_end_tick + delay,
                )
                state.canonical.forecast_completion_tick = max(
                    state.canonical.forecast_completion_tick,
                    closeout.forecast_end_tick,
                )
            record.submission.decision_parameters_used["inspection_delay"] = delay
        return params

    def _first_int(self, data: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return round(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def _resolve_steel_expedite(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        private_state = state.private_by_agent.get(record.agent_id)
        private = private_state.data if private_state is not None else {}
        if "strategy" not in params and "expedite_spend" not in params:
            return {}
        standard_tick = (
            self._first_int(private, ("current_delivery_forecast", "standard_delivery_tick"))
            or 18
        )
        expedited_tick = self._first_int(private, ("expedited_delivery_tick",)) or max(
            14,
            standard_tick - 4,
        )
        expedite_cost = self._first_int(private, ("expedite_cost",)) or 0
        input_cost = (
            self._first_int(private, ("current_input_cost", "current_expected_input_cost")) or 0
        )
        spend = self._first_int(params, ("expedite_spend",)) or 0
        spend = max(0, min(spend, expedite_cost)) if expedite_cost > 0 else max(0, spend)
        if expedite_cost > 0:
            progress = spend / expedite_cost
            delivery_tick = round(standard_tick - ((standard_tick - expedited_tick) * progress))
        else:
            delivery_tick = self._first_int(params, ("forecast_end_tick",)) or standard_tick
        forecast_tick = self._first_int(params, ("forecast_end_tick",)) or delivery_tick
        forecast_tick = max(expedited_tick, min(standard_tick, forecast_tick))
        forecast_cost = self._first_int(params, ("forecast_cost", "expected_cost")) or (
            input_cost + spend
        )
        self._spend_cash(state, record.agent_id, spend)
        record.submission.decision_parameters_used.update(
            {
                "strategy": params.get("strategy", "steel_expedite"),
                "expedite_spend": spend,
            },
        )
        return {"forecast_end_tick": forecast_tick, "forecast_cost": forecast_cost}

    def _resolve_labor_overtime(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        private_state = state.private_by_agent.get(record.agent_id)
        private = private_state.data if private_state is not None else {}
        if (
            "strategy" not in params
            and "overtime_spend" not in params
            and "crew_spend" not in params
        ):
            return {}
        task = state.canonical.tasks["steel_erection"]
        schedule = private.get("current_crew_schedule")
        steel_schedule = schedule.get("steel_erection") if isinstance(schedule, dict) else {}
        constrained_start = (
            self._first_int(steel_schedule, ("start_tick", "planned_start_tick"))
            if isinstance(steel_schedule, dict)
            else None
        ) or task.planned_start_tick
        constrained_end = (
            self._first_int(steel_schedule, ("end_tick", "forecast_end_tick"))
            if isinstance(steel_schedule, dict)
            else None
        ) or task.forecast_end_tick
        spend = self._first_int(params, ("overtime_spend", "crew_spend")) or 0
        cost_per_tick = (
            self._first_int(private, ("overtime_cost_per_tick", "idle_cost_per_tick")) or 85_000
        )
        recovered_ticks = min(2, spend // max(1, cost_per_tick))
        start = self._first_int(params, ("planned_start_tick", "start_tick")) or constrained_start
        end = self._first_int(params, ("forecast_end_tick", "end_tick")) or constrained_end
        start = max(task.planned_start_tick, min(constrained_start, start))
        end = max(start + 1, min(constrained_end, end, constrained_end - recovered_ticks))
        self._spend_cash(state, record.agent_id, spend)
        if spend > 0:
            task.forecast_cost += spend
        record.submission.decision_parameters_used.update(
            {"strategy": params.get("strategy", "labor_schedule"), "overtime_spend": spend},
        )
        return {"start_tick": start, "end_tick": end}

    def _resolve_gc_acceleration(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        private_state = state.private_by_agent.get(record.agent_id)
        private = private_state.data if private_state is not None else {}
        if (
            "strategy" not in params
            and "coordination_spend" not in params
            and "acceleration_spend" not in params
        ):
            return {}
        internal_forecast = (
            self._first_int(private, ("internal_completion_forecast",))
            or state.canonical.forecast_completion_tick
        )
        spend = self._first_int(params, ("coordination_spend", "acceleration_spend")) or 0
        cost_per_tick = self._first_int(private, ("acceleration_cost_per_tick",)) or 250_000
        recovered_ticks = min(2, spend // max(1, cost_per_tick))
        chosen_tick = self._first_int(params, ("forecast_completion_tick", "completion_tick"))
        if chosen_tick is None:
            chosen_tick = max(
                state.canonical.target_completion_tick,
                internal_forecast - recovered_ticks,
            )
        state.canonical.forecast_final_cost += spend
        self._spend_cash(state, record.agent_id, spend)
        record.submission.decision_parameters_used.update(
            {"strategy": params.get("strategy", "gc_completion"), "coordination_spend": spend},
        )
        return {"forecast_completion_tick": chosen_tick}

    def _resolve_owner_contingency(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        private_state = state.private_by_agent.get(record.agent_id)
        private = private_state.data if private_state is not None else {}
        if "strategy" not in params and "contingency_authorized" not in params:
            return {}
        projected_cost = self._first_int(
            private,
            ("projected_final_cost", "forecast_final_cost", "expected_final_cost"),
        ) or state.canonical.forecast_final_cost
        authorized = self._first_int(params, ("contingency_authorized",)) or 0
        forecast_cost = (
            self._first_int(params, ("forecast_final_cost", "final_cost")) or projected_cost
        )
        if authorized > 0:
            self._spend_cash(state, record.agent_id, authorized)
        record.submission.decision_parameters_used.update(
            {
                "strategy": params.get("strategy", "owner_forecast"),
                "contingency_authorized": authorized,
            },
        )
        return {"forecast_final_cost": forecast_cost}

    def _apply_funding_delay(
        self,
        record: AgentRuntimeRecord,
        state: StateStore,
        result: TransitionResult,
    ) -> None:
        funding_delay = self._first_int(
            record.submission.decision.parameters,
            ("funding_delay_ticks", "review_delay"),
        )
        if funding_delay is None or funding_delay <= 0:
            return
        delayed_tick = state.canonical.target_completion_tick + funding_delay
        if state.canonical.forecast_completion_tick < delayed_tick:
            state.canonical.forecast_completion_tick = delayed_tick
            record.submission.decision_parameters_used["funding_delay_ticks"] = funding_delay
            record.submission.decision_parameters_used["forecast_completion_tick"] = delayed_tick
            result.applied.append(
                AppliedTransition(
                    agent_id=record.agent_id,
                    transition_type="funding_delay_applied",
                    target_store="canonical",
                    object_id="project_completion",
                    description="Updated project completion forecast from lender funding delay.",
                ),
            )

    def _spend_cash(self, state: StateStore, agent_id: AgentRole, amount: int) -> None:
        if amount <= 0:
            return
        finance = state.canonical.agent_finances.get(agent_id)
        if finance is not None:
            finance.cash_available -= amount

    def _id(self, prefix: str, tick: int, source: str, index: int) -> str:
        clean_source = source.replace("-", "_")
        return f"{prefix}_{tick}_{clean_source}_{index}"
