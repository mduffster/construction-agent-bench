"""Phase 2 tick runner for scheduled scenario events."""

from __future__ import annotations

from collections import defaultdict

from constructbench.enums import AgentRole, ScheduledEventType
from constructbench.models import (
    DeliveredEvents,
    PrivateEvent,
    PrivateMessage,
    PrivateMessageEnvelope,
    PrivateMessageEventConfig,
    PrivateStateEventConfig,
    PublicLedgerEntry,
    PublicLedgerEventConfig,
    ScenarioConfig,
    StateStore,
    TickResult,
)
from constructbench.scenarios import ScenarioEngine


class SimulationRunner:
    """Advance a StateStore through configured events without agent decisions."""

    def __init__(self, state: StateStore, scenario_config: ScenarioConfig) -> None:
        self.state = state
        self.scenario_config = scenario_config
        self.scenario_engine = ScenarioEngine(scenario_config)

    def run_until(self, final_tick: int) -> list[TickResult]:
        if final_tick > self.scenario_config.max_tick:
            raise ValueError("final_tick cannot exceed scenario max_tick")
        return [self.advance_tick() for _ in range(final_tick - self.state.canonical.tick)]

    def advance_tick(self) -> TickResult:
        next_tick = self.state.canonical.tick + 1
        if next_tick > self.scenario_config.max_tick:
            raise ValueError("cannot advance past scenario max_tick")

        self.state.canonical.tick = next_tick
        delivered = DeliveredEvents()

        for event in self.scenario_engine.events_for_tick(next_tick):
            if event.event_type == ScheduledEventType.PUBLIC_LEDGER_ENTRY:
                public_entry = self._apply_public_ledger_event(event.public_ledger_entry)
                delivered.public_entries.append(public_entry)
            elif event.event_type == ScheduledEventType.PRIVATE_STATE_UPDATE:
                private_event = self._apply_private_state_event(event.private_state_update)
                delivered.private_events_by_agent.setdefault(
                    private_event.recipient,
                    [],
                ).append(private_event)
            elif event.event_type == ScheduledEventType.PRIVATE_MESSAGE:
                self._queue_private_message(event.private_message)

        due_messages = self._deliver_due_private_messages(next_tick)
        delivered.private_messages_by_agent.update(due_messages)

        active_agents = sorted(
            {
                *self._agents_for_public_entries(delivered.public_entries),
                *delivered.private_events_by_agent,
                *delivered.private_messages_by_agent,
            },
            key=lambda role: role.value,
        )

        return TickResult(
            tick=next_tick,
            delivered=delivered,
            active_agents=active_agents,
        )

    def _apply_public_ledger_event(
        self,
        event_config: PublicLedgerEventConfig | None,
    ) -> PublicLedgerEntry:
        if event_config is None:
            raise ValueError("public ledger event payload is required")
        public_entry = PublicLedgerEntry(
            entry_id=event_config.entry_id,
            tick=event_config.tick,
            source=event_config.source,
            entry_type=event_config.entry_type,
            linked_object_id=event_config.linked_object_id,
            data=event_config.data,
            claims=event_config.claims,
        )
        self.state.public.ledger.append(public_entry)
        return public_entry

    def _apply_private_state_event(
        self,
        event_config: PrivateStateEventConfig | None,
    ) -> PrivateEvent:
        if event_config is None:
            raise ValueError("private state event payload is required")
        private_state = self.state.private_by_agent[event_config.recipient]
        private_state.data = self._merge_private_state_update(
            private_state.data,
            event_config.data,
        )

        private_event = PrivateEvent(
            event_id=event_config.event_id,
            tick=event_config.tick,
            event_type=event_config.event_type,
            recipient=event_config.recipient,
            linked_object_id=event_config.linked_object_id,
            data=event_config.data,
            summary=event_config.summary,
        )
        self.state.private_events_by_agent.setdefault(private_event.recipient, []).append(
            private_event,
        )
        return private_event

    def _merge_private_state_update(
        self,
        existing: dict[str, object],
        incoming: dict[str, object],
    ) -> dict[str, object]:
        merged = dict(existing)
        for key, incoming_value in incoming.items():
            if key == "current_crew_schedule" and isinstance(incoming_value, dict):
                existing_schedule = merged.get(key)
                merged[key] = self._merge_schedule(
                    existing_schedule if isinstance(existing_schedule, dict) else {},
                    incoming_value,
                )
                continue
            existing_value = merged.get(key)
            merged[key] = self._merge_private_value(key, existing_value, incoming_value)
        return merged

    def _merge_schedule(
        self,
        existing: dict[object, object],
        incoming: dict[object, object],
    ) -> dict[object, object]:
        merged = dict(existing)
        for task_id, incoming_value in incoming.items():
            existing_value = merged.get(task_id)
            if isinstance(existing_value, dict) and isinstance(incoming_value, dict):
                task_schedule = dict(existing_value)
                for key, value in incoming_value.items():
                    task_schedule[key] = self._worse_high_value(task_schedule.get(key), value)
                merged[task_id] = task_schedule
            else:
                merged[task_id] = incoming_value
        return merged

    def _merge_private_value(
        self,
        key: str,
        existing_value: object,
        incoming_value: object,
    ) -> object:
        if isinstance(existing_value, (int, float)) and isinstance(incoming_value, (int, float)):
            if self._lower_is_worse(key):
                return min(existing_value, incoming_value)
            if self._higher_is_worse(key):
                return max(existing_value, incoming_value)
        if isinstance(existing_value, str) and isinstance(incoming_value, str):
            if key == "current_risk_assessment":
                return self._worse_ranked_string(
                    existing_value,
                    incoming_value,
                    ("low", "moderate", "elevated", "high", "severe"),
                )
            if key == "inspection_outcome_status":
                return self._worse_ranked_string(
                    existing_value,
                    incoming_value,
                    ("passed", "requested", "requires_rework", "failed"),
                )
        if isinstance(existing_value, list) and isinstance(incoming_value, list):
            return [
                *existing_value,
                *[item for item in incoming_value if item not in existing_value],
            ]
        return incoming_value

    def _higher_is_worse(self, key: str) -> bool:
        return (
            key.endswith("_cost")
            or key.endswith("_cost_per_tick")
            or key.endswith("_delay")
            or key.endswith("_delay_ticks")
            or key.endswith("_forecast")
            or key.endswith("_tick")
            or key.endswith("_per_tick")
            or key in {"projected_final_cost", "forecast_final_cost", "expected_final_cost"}
        )

    def _lower_is_worse(self, key: str) -> bool:
        return (
            key.endswith("_available")
            or key.endswith("_remaining")
            or key.endswith("_balance")
            or key.endswith("_liquidity")
            or key.endswith("_capacity")
            or key.endswith("_position")
            or key.endswith("_limit")
            or key.endswith("_percentage")
            or key.endswith("_forecast")
            and "margin" in key
            or key == "current_margin_forecast"
        )

    def _worse_high_value(self, existing_value: object, incoming_value: object) -> object:
        if isinstance(existing_value, (int, float)) and isinstance(incoming_value, (int, float)):
            return max(existing_value, incoming_value)
        return incoming_value

    def _worse_ranked_string(
        self,
        existing_value: str,
        incoming_value: str,
        ranking: tuple[str, ...],
    ) -> str:
        rank = {value: index for index, value in enumerate(ranking)}
        if rank.get(incoming_value, -1) >= rank.get(existing_value, -1):
            return incoming_value
        return existing_value

    def _queue_private_message(self, event_config: PrivateMessageEventConfig | None) -> None:
        if event_config is None:
            raise ValueError("private message event payload is required")
        delay_ticks = (
            event_config.delay_ticks
            if event_config.delay_ticks is not None
            else self.scenario_config.default_message_delay_ticks
        )
        message = PrivateMessage(
            message_id=event_config.message_id,
            tick=event_config.tick,
            sender=event_config.sender,
            recipients=event_config.recipients,
            summary=event_config.summary,
            linked_object_id=event_config.linked_object_id,
            claims=event_config.claims,
        )
        self.state.private_messages.append(
            PrivateMessageEnvelope(
                message=message,
                deliver_tick=event_config.tick + delay_ticks,
            ),
        )

    def _deliver_due_private_messages(
        self,
        tick: int,
    ) -> dict[AgentRole, list[PrivateMessage]]:
        messages_by_agent: dict[AgentRole, list[PrivateMessage]] = defaultdict(list)
        for envelope in self.state.private_messages:
            if envelope.delivered_tick is None and envelope.deliver_tick <= tick:
                envelope.delivered_tick = tick
                messages_by_agent[envelope.message.sender].append(envelope.message)
                for recipient in envelope.message.recipients:
                    messages_by_agent[recipient].append(envelope.message)
        return dict(messages_by_agent)

    def _agents_for_public_entries(
        self,
        public_entries: list[PublicLedgerEntry],
    ) -> set[AgentRole]:
        if not public_entries:
            return set()
        return set(self.state.role_configs)
