"""Agent runtime orchestration for Phase 3."""

from __future__ import annotations

import re
from typing import Any

from constructbench.agents import AgentPolicy, FallbackPolicy, LLMPolicy
from constructbench.enums import AgentRole
from constructbench.models import (
    AgentBeliefState,
    AgentRuntimeRecord,
    AgentTurnResult,
    DeliveredEvents,
    StateStore,
    TickResult,
)
from constructbench.observations import ObservationBuilder
from constructbench.validation import SubmissionValidator


class BeliefUpdateHandler:
    """Apply validated belief updates to the submitting agent only.

    Structured belief_update fields are authoritative. If a local model leaves
    a belief value unchanged but includes a recognizable numeric update in a
    claim, decision parameter, communication summary, or raw output, this handler
    promotes that number into the belief state.
    """

    FIELD_ALIASES: dict[str, tuple[str, ...]] = {
        "expected_completion_tick": (
            "expected_completion_tick",
            "expected project completion tick",
            "project completion tick",
            "completion tick",
        ),
        "expected_final_cost": (
            "expected_final_cost",
            "expected final cost",
            "final cost",
            "expected cost",
        ),
        "probability_on_time": (
            "probability_on_time",
            "probability on time",
            "on time probability",
            "probability of on-time completion",
        ),
        "probability_within_budget": (
            "probability_within_budget",
            "probability within budget",
            "within budget probability",
            "probability of remaining within budget",
        ),
        "confidence": ("confidence",),
    }

    def apply(self, agent_id: AgentRole, state: StateStore, record: AgentRuntimeRecord) -> None:
        if record.validation.valid:
            current = state.beliefs_by_agent[agent_id]
            belief_update = record.submission.belief_update.model_copy(deep=True)
            extracted_values = self._extract_belief_values(record)
            normalized_belief = self._merge_extracted_values(
                current,
                belief_update,
                extracted_values,
            )
            normalized_belief = self._merge_delivered_basis_ids(record, normalized_belief)
            state.beliefs_by_agent[agent_id] = normalized_belief
            record.submission.belief_update = normalized_belief
            self._merge_observed_new_info(record)

    def _merge_extracted_values(
        self,
        current: AgentBeliefState,
        belief_update: AgentBeliefState,
        extracted_values: dict[str, int | float],
    ) -> AgentBeliefState:
        update_data: dict[str, int | float] = {}
        for field, extracted_value in extracted_values.items():
            if getattr(belief_update, field) == getattr(current, field):
                update_data[field] = extracted_value
        if not update_data:
            return belief_update
        return belief_update.model_copy(update=update_data)

    def _merge_delivered_basis_ids(
        self,
        record: AgentRuntimeRecord,
        belief_update: AgentBeliefState,
    ) -> AgentBeliefState:
        basis_ids = list(belief_update.basis_ids)
        delivered_ids = [
            *(entry.entry_id for entry in record.observation.new_public_entries),
            *(event.event_id for event in record.observation.new_private_events),
        ]
        for basis_id in delivered_ids:
            if basis_id not in basis_ids:
                basis_ids.append(basis_id)
        if basis_ids == belief_update.basis_ids:
            return belief_update
        return belief_update.model_copy(update={"basis_ids": basis_ids})

    def _merge_observed_new_info(self, record: AgentRuntimeRecord) -> None:
        observed_ids = list(record.submission.observed_new_info)
        delivered_ids = [
            *(entry.entry_id for entry in record.observation.new_public_entries),
            *(event.event_id for event in record.observation.new_private_events),
        ]
        for delivered_id in delivered_ids:
            if delivered_id not in observed_ids:
                observed_ids.append(delivered_id)
        record.submission.observed_new_info = observed_ids

    def _extract_belief_values(self, record: AgentRuntimeRecord) -> dict[str, int | float]:
        values: dict[str, int | float] = {}

        values.update(self._extract_from_mapping(record.submission.decision.parameters))

        communication = record.submission.communication
        if communication is not None:
            values.update(self._extract_from_text(communication.summary))
            for claim in communication.claims:
                field = self._canonical_field(claim.field)
                if field is not None:
                    numeric_value = self._coerce_numeric(claim.value, field)
                    if numeric_value is not None:
                        values[field] = numeric_value

        if record.raw_output:
            values.update(self._extract_from_text(record.raw_output))

        return values

    def _extract_from_mapping(self, data: dict[str, Any]) -> dict[str, int | float]:
        values: dict[str, int | float] = {}
        for key, value in data.items():
            field = self._canonical_field(key)
            if field is not None:
                numeric_value = self._coerce_numeric(value, field)
                if numeric_value is not None:
                    values[field] = numeric_value
            if isinstance(value, dict):
                values.update(self._extract_from_mapping(value))
        return values

    def _extract_from_text(self, text: str) -> dict[str, int | float]:
        values: dict[str, int | float] = {}
        for field, aliases in self.FIELD_ALIASES.items():
            for alias in aliases:
                numeric_value = self._extract_number_after_alias(text, alias, field)
                if numeric_value is not None:
                    values[field] = numeric_value
                    break
        return values

    def _canonical_field(self, field_name: str) -> str | None:
        normalized = field_name.strip().lower().replace("-", "_").replace(" ", "_")
        for field, aliases in self.FIELD_ALIASES.items():
            normalized_aliases = {alias.replace(" ", "_") for alias in aliases}
            if normalized == field or normalized in normalized_aliases:
                return field
        return None

    def _extract_number_after_alias(
        self,
        text: str,
        alias: str,
        field: str,
    ) -> int | float | None:
        alias_pattern = re.escape(alias).replace(r"\ ", r"[\s_]+")
        pattern = rf"{alias_pattern}\D{{0,40}}(-?\$?\d[\d,]*(?:\.\d+)?%?)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            return None
        return self._coerce_numeric(match.group(1), field)

    def _coerce_numeric(self, value: Any, field: str) -> int | float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            match = re.search(r"-?\$?\d[\d,]*(?:\.\d+)?%?", value)
            if match is None:
                return None
            token = match.group(0)
            numeric = float(token.replace("$", "").replace(",", "").replace("%", ""))
            if token.endswith("%"):
                numeric = numeric / 100
        else:
            return None

        if field in {"probability_on_time", "probability_within_budget", "confidence"}:
            if numeric > 1:
                numeric = numeric / 100
            return max(0.0, min(1.0, numeric))

        if field in {"expected_completion_tick", "expected_final_cost"}:
            return max(0, round(numeric))

        return numeric


class AgentManager:
    """Build observations, call policies, validate submissions, and update beliefs."""

    def __init__(
        self,
        policies_by_agent: dict[AgentRole, AgentPolicy],
        observation_builder: ObservationBuilder | None = None,
        validator: SubmissionValidator | None = None,
        belief_handler: BeliefUpdateHandler | None = None,
        fallback_policy: FallbackPolicy | None = None,
    ) -> None:
        self.policies_by_agent = policies_by_agent
        self.observation_builder = observation_builder or ObservationBuilder()
        self.validator = validator or SubmissionValidator()
        self.belief_handler = belief_handler or BeliefUpdateHandler()
        self.fallback_policy = fallback_policy or FallbackPolicy()

    def process_tick(self, tick_result: TickResult, state: StateStore) -> AgentTurnResult:
        records: list[AgentRuntimeRecord] = []
        for agent_id in tick_result.active_agents:
            observation = self.observation_builder.build(
                agent_id,
                state,
                tick_result.delivered,
            )
            policy = self.policies_by_agent.get(agent_id, self.fallback_policy)
            submission = policy.decide(observation)
            validation = self.validator.validate(agent_id.value, submission, state, observation)
            used_fallback = policy is self.fallback_policy
            raw_output: str | None = None
            parse_errors: list[str] = []

            if isinstance(policy, LLMPolicy):
                used_fallback = policy.last_used_fallback
                raw_output = policy.last_raw_output
                parse_errors = list(policy.last_parse_errors)

            if not validation.valid:
                submission = self.fallback_policy.decide(observation)
                validation = self.validator.validate(agent_id.value, submission, state, observation)
                used_fallback = True

            record = AgentRuntimeRecord(
                agent_id=agent_id,
                observation=observation,
                submission=submission,
                validation=validation,
                used_fallback=used_fallback,
                raw_output=raw_output,
                parse_errors=parse_errors,
            )
            self.belief_handler.apply(agent_id, state, record)
            records.append(record)

        return AgentTurnResult(tick=tick_result.tick, records=records)


def default_scripted_policies() -> dict[AgentRole, AgentPolicy]:
    """Return no-op scripted policies for all configured roles."""
    from constructbench.agents import ScriptedPolicy

    return {role: ScriptedPolicy() for role in AgentRole}


def delivered_events_for_agent(delivered: DeliveredEvents, agent_id: AgentRole) -> DeliveredEvents:
    """Return delivered information filtered to one agent."""
    return DeliveredEvents(
        public_entries=delivered.public_entries,
        private_events_by_agent={
            agent_id: delivered.private_events_by_agent.get(agent_id, []),
        },
        private_messages_by_agent={
            agent_id: delivered.private_messages_by_agent.get(agent_id, []),
        },
    )
