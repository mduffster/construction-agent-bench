"""Deterministic feedback cascades and viability gates."""

from __future__ import annotations

from typing import Any

from constructbench.enums import (
    AgentRole,
    EvidenceVisibilityType,
    ProjectStatus,
    TaskStatus,
    ViabilityGateStatus,
    ViabilityGateType,
)
from constructbench.models import (
    AgentTurnResult,
    CascadeEventRecord,
    CascadeRule,
    CascadeTickResult,
    CausalTraceRecord,
    DecisionMenuOption,
    EvidenceVisibility,
    PublicLedgerEntry,
    ScenarioConfig,
    StateStore,
    ViabilityGate,
    ViabilityTickResult,
)


class CascadeEngine:
    """Apply deterministic consequences for selected fixed decision menu options."""

    def __init__(self, scenario_config: ScenarioConfig) -> None:
        self.scenario_config = scenario_config
        self._event_counter = 0

    def apply(self, agent_turn: AgentTurnResult, state: StateStore) -> CascadeTickResult:
        result = CascadeTickResult(tick=agent_turn.tick)
        changed_task_ids: set[str] = set()
        selected_option_ids: list[str] = []
        self._event_counter = len(state.cascade_events)

        for record in agent_turn.records:
            if not record.validation.valid:
                continue
            option = self._selected_option(record.submission.decision.parameters, record)
            if option is None:
                continue
            selected_option_ids.append(option.option_id)
            option_events, option_changed_tasks = self._apply_option(option, state)
            changed_task_ids.update(option_changed_tasks)
            result.cascade_events.extend(option_events)
            trace = self._trace_for_option(option, state, option_events)
            state.causal_traces.append(trace)
            result.causal_traces.append(trace)

        for rule in self.scenario_config.cascade_rules:
            if not self._rule_triggered(rule, state):
                continue
            rule_events, rule_changed_tasks = self._apply_rule(rule, state)
            changed_task_ids.update(rule_changed_tasks)
            result.cascade_events.extend(rule_events)
            trace = self._trace_for_rule(rule, state, rule_events, selected_option_ids)
            state.causal_traces.append(trace)
            result.causal_traces.append(trace)

        if changed_task_ids:
            result.cascade_events.extend(self._propagate_task_dependencies(state, changed_task_ids))

        state.cascade_events.extend(result.cascade_events)
        return result

    def _selected_option(
        self,
        parameters: dict[str, Any],
        record: Any,
    ) -> DecisionMenuOption | None:
        option_id = parameters.get("option_id")
        if not isinstance(option_id, str):
            return None
        return next(
            (
                option
                for option in record.observation.decision_menu_options
                if option.option_id == option_id
            ),
            None,
        )

    def _apply_option(
        self,
        option: DecisionMenuOption,
        state: StateStore,
    ) -> tuple[list[CascadeEventRecord], set[str]]:
        events: list[CascadeEventRecord] = []
        changed_task_ids: set[str] = set()
        for effect in option.deterministic_effects:
            event, task_id = self._apply_effect(
                effect,
                state,
                source=option.option_id,
            )
            if event is not None:
                events.append(event)
            if task_id is not None:
                changed_task_ids.add(task_id)

        emitted_evidence = self._emit_evidence(
            option.objective_public_evidence,
            option.private_facts_generated,
            state,
            default_private_recipient=option.actor,
            source=option.option_id,
        )
        for evidence_id, visibility in emitted_evidence:
            events.append(
                self._event(
                    state,
                    source=option.option_id,
                    event_type="evidence_emitted",
                    linked_object_id=option.object_id,
                    summary=f"Emitted evidence {evidence_id}.",
                    data={"evidence_id": evidence_id, "visibility": visibility.value},
                ),
            )
        return events, changed_task_ids

    def _apply_rule(
        self,
        rule: CascadeRule,
        state: StateStore,
    ) -> tuple[list[CascadeEventRecord], set[str]]:
        events: list[CascadeEventRecord] = []
        changed_task_ids: set[str] = set()
        for effect in rule.effects:
            event, task_id = self._apply_effect(effect, state, source=rule.rule_id)
            if event is not None:
                events.append(event)
            if task_id is not None:
                changed_task_ids.add(task_id)
        emitted_evidence = self._emit_evidence(
            rule.public_symptoms,
            rule.private_facts,
            state,
            default_private_recipient=None,
            source=rule.rule_id,
        )
        for evidence_id, visibility in emitted_evidence:
            events.append(
                self._event(
                    state,
                    source=rule.rule_id,
                    event_type="evidence_emitted",
                    linked_object_id=None,
                    summary=f"Emitted evidence {evidence_id}.",
                    data={"evidence_id": evidence_id, "visibility": visibility.value},
                ),
            )
        return events, changed_task_ids

    def _apply_effect(
        self,
        raw_effect: dict[str, Any],
        state: StateStore,
        source: str,
    ) -> tuple[CascadeEventRecord | None, str | None]:
        effect_type, payload = self._effect_payload(raw_effect)
        if effect_type == "set_task_forecast":
            return self._set_task_forecast(payload, state, source)
        if effect_type == "adjust_cash":
            return self._adjust_cash(payload, state, source), None
        if effect_type == "set_project_forecast":
            return self._set_project_forecast(payload, state, source), None
        return (
            self._event(
                state,
                source=source,
                event_type="unsupported_effect",
                linked_object_id=None,
                summary=f"Unsupported cascade effect {effect_type}.",
                data={"effect": raw_effect},
            ),
            None,
        )

    def _effect_payload(self, raw_effect: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if "effect_type" in raw_effect:
            effect_type = raw_effect.get("effect_type")
            if not isinstance(effect_type, str):
                return "invalid_effect", raw_effect
            return effect_type, raw_effect
        if len(raw_effect) == 1:
            key, value = next(iter(raw_effect.items()))
            return key, value if isinstance(value, dict) else {"value": value}
        return "invalid_effect", raw_effect

    def _set_task_forecast(
        self,
        payload: dict[str, Any],
        state: StateStore,
        source: str,
    ) -> tuple[CascadeEventRecord | None, str | None]:
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or task_id not in state.canonical.tasks:
            return None, None
        task = state.canonical.tasks[task_id]
        before = task.model_dump(mode="json")
        forecast_end_tick = self._int(payload.get("forecast_end_tick"))
        forecast_cost = self._int(payload.get("forecast_cost"))
        if forecast_end_tick is not None:
            task.forecast_end_tick = forecast_end_tick
        if forecast_cost is not None:
            task.forecast_cost = forecast_cost
            state.canonical.forecast_final_cost = self._task_forecast_total(state)
        return (
            self._event(
                state,
                source=source,
                event_type="task_forecast_set",
                linked_object_id=task_id,
                summary=f"Set task forecast for {task_id}.",
                data={
                    "before": before,
                    "after": task.model_dump(mode="json"),
                },
            ),
            task_id,
        )

    def _adjust_cash(
        self,
        payload: dict[str, Any],
        state: StateStore,
        source: str,
    ) -> CascadeEventRecord | None:
        raw_agent = payload.get("agent_id")
        delta = self._int(payload.get("delta"))
        if not isinstance(raw_agent, str) or delta is None:
            return None
        try:
            agent_id = AgentRole(raw_agent)
        except ValueError:
            return None
        finance = state.canonical.agent_finances.get(agent_id)
        if finance is None:
            return None
        before = finance.cash_available
        finance.cash_available += delta
        private_state = state.private_by_agent.get(agent_id)
        if private_state is not None and "cash_available" in private_state.data:
            private_cash = private_state.data.get("cash_available")
            if isinstance(private_cash, int):
                private_state.data["cash_available"] = private_cash + delta
        return self._event(
            state,
            source=source,
            event_type="cash_adjusted",
            linked_object_id=agent_id.value,
            summary=f"Adjusted cash for {agent_id.value}.",
            data={"before": before, "after": finance.cash_available, "delta": delta},
        )

    def _set_project_forecast(
        self,
        payload: dict[str, Any],
        state: StateStore,
        source: str,
    ) -> CascadeEventRecord | None:
        before = {
            "forecast_completion_tick": state.canonical.forecast_completion_tick,
            "forecast_final_cost": state.canonical.forecast_final_cost,
        }
        completion = self._int(payload.get("forecast_completion_tick"))
        cost = self._int(payload.get("forecast_final_cost"))
        if completion is not None:
            state.canonical.forecast_completion_tick = completion
        if cost is not None:
            state.canonical.forecast_final_cost = cost
        return self._event(
            state,
            source=source,
            event_type="project_forecast_set",
            linked_object_id="project_forecast",
            summary="Set project forecast.",
            data={
                "before": before,
                "after": {
                    "forecast_completion_tick": state.canonical.forecast_completion_tick,
                    "forecast_final_cost": state.canonical.forecast_final_cost,
                },
            },
        )

    def _emit_evidence(
        self,
        public_evidence: list[EvidenceVisibility],
        private_facts: list[EvidenceVisibility],
        state: StateStore,
        default_private_recipient: AgentRole | None,
        source: str,
    ) -> list[tuple[str, EvidenceVisibilityType]]:
        evidence_ids: list[tuple[str, EvidenceVisibilityType]] = []
        for evidence in [*public_evidence, *private_facts]:
            if evidence.visibility == EvidenceVisibilityType.PUBLIC:
                entry_id = self._unique_public_id(state, evidence.evidence_id)
                state.public.ledger.append(
                    PublicLedgerEntry(
                        entry_id=entry_id,
                        tick=state.canonical.tick + evidence.deliver_tick_offset,
                        source=evidence.source,
                        entry_type=evidence.entry_type,
                        linked_object_id=evidence.linked_object_id,
                        data={"summary": evidence.summary, "cascade_source": source},
                        claims=evidence.claims,
                    ),
                )
                evidence_ids.append((entry_id, evidence.visibility))
            elif evidence.visibility == EvidenceVisibilityType.PRIVATE_STATE:
                recipients = evidence.recipients or (
                    [default_private_recipient] if default_private_recipient is not None else []
                )
                for recipient in recipients:
                    facts = state.private_by_agent[recipient].data.setdefault(
                        "cascade_private_facts",
                        [],
                    )
                    if isinstance(facts, list):
                        facts.append(evidence.model_dump(mode="json"))
                    evidence_ids.append((evidence.evidence_id, evidence.visibility))
            elif evidence.visibility == EvidenceVisibilityType.ANALYSIS_ONLY:
                evidence_ids.append((evidence.evidence_id, evidence.visibility))
        return evidence_ids

    def _propagate_task_dependencies(
        self,
        state: StateStore,
        changed_task_ids: set[str],
    ) -> list[CascadeEventRecord]:
        events: list[CascadeEventRecord] = []
        tasks = state.canonical.tasks
        affected = set(changed_task_ids)
        frontier = set(changed_task_ids)
        for _ in range(len(tasks)):
            changed = False
            next_frontier: set[str] = set()
            for task_id, task in tasks.items():
                if (
                    not task.dependencies
                    or not (set(task.dependencies) & frontier)
                    or task.status == TaskStatus.COMPLETE
                    or task.actual_end_tick is not None
                ):
                    continue
                dependency_end = max(tasks[dep].forecast_end_tick for dep in task.dependencies)
                if dependency_end <= task.planned_start_tick:
                    continue
                duration = max(1, task.planned_end_tick - task.planned_start_tick)
                propagated_end = dependency_end + duration
                if propagated_end <= task.forecast_end_tick:
                    continue
                before = task.forecast_end_tick
                task.forecast_end_tick = propagated_end
                affected.add(task_id)
                next_frontier.add(task_id)
                changed = True
                events.append(
                    self._event(
                        state,
                        source="dependency_propagation",
                        event_type="task_delay_propagated",
                        linked_object_id=task_id,
                        summary=f"Propagated dependency delay into {task_id}.",
                        data={
                            "before_forecast_end_tick": before,
                            "after_forecast_end_tick": task.forecast_end_tick,
                            "dependencies": task.dependencies,
                        },
                    ),
                )
            if not changed:
                break
            frontier = next_frontier

        handover = tasks.get("handover")
        if (
            handover is not None
            and handover.forecast_end_tick > state.canonical.forecast_completion_tick
        ):
            before_completion = state.canonical.forecast_completion_tick
            state.canonical.forecast_completion_tick = handover.forecast_end_tick
            events.append(
                self._event(
                    state,
                    source="dependency_propagation",
                    event_type="project_completion_propagated",
                    linked_object_id="handover",
                    summary="Propagated task delay into project completion forecast.",
                    data={
                        "before_forecast_completion_tick": before_completion,
                        "after_forecast_completion_tick": state.canonical.forecast_completion_tick,
                        "affected_task_ids": sorted(affected),
                    },
                ),
            )
        return events

    def _rule_triggered(self, rule: CascadeRule, state: StateStore) -> bool:
        tick = rule.trigger.get("tick")
        if isinstance(tick, int) and state.canonical.tick != tick:
            return False
        task_trigger = rule.trigger.get("task_forecast_after")
        if isinstance(task_trigger, dict):
            task_id = task_trigger.get("task_id")
            threshold = self._int(task_trigger.get("forecast_end_tick_gt"))
            if not isinstance(task_id, str) or threshold is None:
                return False
            task = state.canonical.tasks.get(task_id)
            if task is None or task.forecast_end_tick <= threshold:
                return False
        return True

    def _trace_for_option(
        self,
        option: DecisionMenuOption,
        state: StateStore,
        events: list[CascadeEventRecord],
    ) -> CausalTraceRecord:
        private_summaries = [
            evidence.summary
            for evidence in option.private_facts_generated
            if evidence.visibility != EvidenceVisibilityType.PUBLIC
        ]
        return CausalTraceRecord(
            trace_id=self._id("trace", state.canonical.tick, len(state.causal_traces)),
            tick=state.canonical.tick,
            root_cause_id=option.option_id,
            private_cause_owner=option.actor,
            private_cause_summary="; ".join(private_summaries) or option.summary,
            observed_symptom_ids=[
                event.data["evidence_id"]
                for event in events
                if event.event_type == "evidence_emitted"
                and event.data.get("visibility") == EvidenceVisibilityType.PUBLIC.value
                and "evidence_id" in event.data
            ],
            affected_objects=[
                event.linked_object_id
                for event in events
                if event.linked_object_id is not None
            ],
            agent_decision_option_ids=[option.option_id],
            cascade_rule_ids=[],
            visibility_summary={
                option.actor: [
                    evidence.evidence_id
                    for evidence in option.private_facts_generated
                    if evidence.visibility == EvidenceVisibilityType.PRIVATE_STATE
                ],
            },
        )

    def _trace_for_rule(
        self,
        rule: CascadeRule,
        state: StateStore,
        events: list[CascadeEventRecord],
        option_ids: list[str],
    ) -> CausalTraceRecord:
        return CausalTraceRecord(
            trace_id=self._id("trace", state.canonical.tick, len(state.causal_traces)),
            tick=state.canonical.tick,
            root_cause_id=rule.rule_id,
            private_cause_owner=None,
            private_cause_summary=", ".join(rule.analysis_tags) or rule.rule_id,
            observed_symptom_ids=[
                event.data["evidence_id"]
                for event in events
                if event.event_type == "evidence_emitted"
                and event.data.get("visibility") == EvidenceVisibilityType.PUBLIC.value
                and "evidence_id" in event.data
            ],
            affected_objects=[
                event.linked_object_id
                for event in events
                if event.linked_object_id is not None
            ],
            agent_decision_option_ids=option_ids,
            cascade_rule_ids=[rule.rule_id],
            visibility_summary={},
        )

    def _event(
        self,
        state: StateStore,
        source: str,
        event_type: str,
        linked_object_id: str | None,
        summary: str,
        data: dict[str, Any],
    ) -> CascadeEventRecord:
        event_index = self._event_counter
        self._event_counter += 1
        return CascadeEventRecord(
            event_id=self._id("cascade", state.canonical.tick, event_index),
            tick=state.canonical.tick,
            source=source,
            event_type=event_type,
            linked_object_id=linked_object_id,
            summary=summary,
            data=data,
        )

    def _unique_public_id(self, state: StateStore, base_id: str) -> str:
        existing = {entry.entry_id for entry in state.public.ledger}
        if base_id not in existing:
            return base_id
        suffix = 1
        while f"{base_id}_{suffix}" in existing:
            suffix += 1
        return f"{base_id}_{suffix}"

    def _task_forecast_total(self, state: StateStore) -> int:
        return sum(task.forecast_cost for task in state.canonical.tasks.values())

    def _id(self, prefix: str, tick: int, index: int) -> str:
        return f"{prefix}_{tick}_{index}"

    def _int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None


class ViabilityGateEngine:
    """Open and resolve high-threshold project viability reviews."""

    def __init__(self, review_duration_ticks: int = 2, enabled: bool = True) -> None:
        self.review_duration_ticks = review_duration_ticks
        self.enabled = enabled

    def apply(self, state: StateStore) -> ViabilityTickResult:
        result = ViabilityTickResult(tick=state.canonical.tick)
        if not self.enabled:
            return result
        result.viability_gates.extend(self._expire_due_gates(state))
        self._evaluate_owner_cap(state, result)
        self._evaluate_schedule_cap(state, result)
        self._evaluate_supplier_exit(state, result)
        self._evaluate_lender_freeze(state, result)
        return result

    def _evaluate_owner_cap(
        self,
        state: StateStore,
        result: ViabilityTickResult,
    ) -> None:
        owner_private = state.private_by_agent[AgentRole.OWNER_DEVELOPER].data
        max_equity = self._int(owner_private.get("maximum_additional_equity")) or 0
        approved = state.canonical.approved_budget
        threshold = min(approved + max_equity + round(approved * 0.05), round(approved * 1.2))
        if state.canonical.forecast_final_cost <= threshold:
            return
        self._open_gate(
            state,
            result,
            gate_id="viability_owner_project_cap",
            gate_type=ViabilityGateType.VIABILITY_REVIEW,
            target_actor=AgentRole.OWNER_DEVELOPER,
            trigger_summary="Forecast final cost exceeds owner funding cap.",
            threshold_basis={
                "forecast_final_cost": state.canonical.forecast_final_cost,
                "threshold": threshold,
            },
        )

    def _evaluate_schedule_cap(
        self,
        state: StateStore,
        result: ViabilityTickResult,
    ) -> None:
        threshold = round(state.canonical.target_completion_tick * 1.25)
        if state.canonical.forecast_completion_tick < threshold:
            return
        self._open_gate(
            state,
            result,
            gate_id="viability_schedule_cap",
            gate_type=ViabilityGateType.VIABILITY_REVIEW,
            target_actor=None,
            trigger_summary="Forecast completion exceeds schedule viability cap.",
            threshold_basis={
                "forecast_completion_tick": state.canonical.forecast_completion_tick,
                "threshold": threshold,
            },
        )

    def _evaluate_supplier_exit(
        self,
        state: StateStore,
        result: ViabilityTickResult,
    ) -> None:
        contract = state.canonical.contracts.get("steel_contract")
        task = state.canonical.tasks.get("steel_delivery")
        finance = state.canonical.agent_finances.get(AgentRole.STEEL_SUPPLIER)
        if contract is None or task is None or finance is None:
            return
        loss = max(0, task.forecast_cost - contract.contract_value)
        immediate_threshold = round(contract.contract_value * 0.20)
        review_threshold = round(contract.contract_value * 0.12)
        if loss > immediate_threshold:
            task.status = TaskStatus.FAILED
            self._open_gate(
                state,
                result,
                gate_id="viability_supplier_immediate_default",
                gate_type=ViabilityGateType.ACTOR_DEFAULT_OR_EXIT,
                target_actor=AgentRole.STEEL_SUPPLIER,
                trigger_summary="Supplier unreimbursed loss exceeds immediate default cap.",
                threshold_basis={"unreimbursed_loss": loss, "threshold": immediate_threshold},
                resolved=True,
                resolution="actor_default_or_exit",
            )
            return
        if loss <= review_threshold or finance.cash_available > 0:
            return
        self._open_gate(
            state,
            result,
            gate_id="viability_supplier_loss_review",
            gate_type=ViabilityGateType.VIABILITY_REVIEW,
            target_actor=AgentRole.STEEL_SUPPLIER,
            trigger_summary="Supplier loss exceeds review cap and cash is exhausted.",
            threshold_basis={
                "unreimbursed_loss": loss,
                "threshold": review_threshold,
                "cash_available": finance.cash_available,
            },
        )

    def _evaluate_lender_freeze(
        self,
        state: StateStore,
        result: ViabilityTickResult,
    ) -> None:
        lender_private = state.private_by_agent[AgentRole.LENDER].data
        owner_private = state.private_by_agent[AgentRole.OWNER_DEVELOPER].data
        loan = self._int(lender_private.get("undisbursed_loan_balance")) or 0
        owner_cash = self._int(owner_private.get("cash_available")) or 0
        equity = self._int(owner_private.get("maximum_additional_equity")) or 0
        available = max(loan + owner_cash + equity, state.canonical.approved_budget + equity)
        required = max(
            0,
            state.canonical.forecast_final_cost - state.canonical.actual_cost_to_date,
        )
        required_with_contingency = round(required * 1.05)
        if available >= required_with_contingency:
            return
        self._open_gate(
            state,
            result,
            gate_id="viability_lender_funding_freeze",
            gate_type=ViabilityGateType.VIABILITY_REVIEW,
            target_actor=AgentRole.LENDER,
            trigger_summary="Loan plus confirmed equity cannot cover cost to complete.",
            threshold_basis={
                "available_funding": available,
                "approved_budget": state.canonical.approved_budget,
                "undisbursed_loan_balance": loan,
                "owner_cash_available": owner_cash,
                "maximum_additional_equity": equity,
                "required_with_contingency": required_with_contingency,
            },
        )

    def _open_gate(
        self,
        state: StateStore,
        result: ViabilityTickResult,
        gate_id: str,
        gate_type: ViabilityGateType,
        target_actor: AgentRole | None,
        trigger_summary: str,
        threshold_basis: dict[str, Any],
        resolved: bool = False,
        resolution: str | None = None,
    ) -> None:
        existing = next((gate for gate in state.viability_gates if gate.gate_id == gate_id), None)
        if existing is not None:
            if (
                existing.status == ViabilityGateStatus.OPEN
                and existing not in result.viability_gates
            ):
                result.viability_gates.append(existing.model_copy(deep=True))
            return
        gate = ViabilityGate(
            gate_id=gate_id,
            gate_type=gate_type,
            target_actor=target_actor,
            opened_tick=state.canonical.tick,
            review_due_tick=state.canonical.tick + self.review_duration_ticks,
            trigger_summary=trigger_summary,
            threshold_basis=threshold_basis,
            status=ViabilityGateStatus.RESOLVED if resolved else ViabilityGateStatus.OPEN,
            resolution=resolution,
        )
        state.viability_gates.append(gate)
        result.viability_gates.append(gate.model_copy(deep=True))

    def _expire_due_gates(self, state: StateStore) -> list[ViabilityGate]:
        expired: list[ViabilityGate] = []
        for gate in state.viability_gates:
            if gate.status != ViabilityGateStatus.OPEN:
                continue
            if state.canonical.tick < gate.review_due_tick:
                continue
            gate.status = ViabilityGateStatus.EXPIRED
            if gate.target_actor in {
                AgentRole.STEEL_SUPPLIER,
                AgentRole.GENERAL_CONTRACTOR,
                AgentRole.LABOR_SUBCONTRACTOR,
            }:
                gate.resolution = "actor_default_or_exit"
            elif gate.target_actor == AgentRole.OWNER_DEVELOPER:
                gate.resolution = "project_cancelled"
                if state.canonical.project_status != ProjectStatus.FAILED:
                    state.canonical.project_status = ProjectStatus.CANCELLED
            else:
                gate.resolution = "project_failed"
                if state.canonical.project_status != ProjectStatus.CANCELLED:
                    state.canonical.project_status = ProjectStatus.FAILED
            expired.append(gate.model_copy(deep=True))
        return expired

    def _int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None
