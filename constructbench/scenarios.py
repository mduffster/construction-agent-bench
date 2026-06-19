"""Scenario event scheduling for Phase 2."""

from __future__ import annotations

from collections import defaultdict

from constructbench.models import ScenarioConfig, ScheduledEventConfig


class ScenarioEngine:
    """Read-only accessor for scheduled scenario events."""

    def __init__(self, scenario_config: ScenarioConfig) -> None:
        self._events_by_tick: dict[int, list[ScheduledEventConfig]] = defaultdict(list)
        for event in sorted(scenario_config.scheduled_events, key=lambda item: item.tick):
            self._events_by_tick[event.tick].append(event)

    def events_for_tick(self, tick: int) -> list[ScheduledEventConfig]:
        """Return scheduled events due at the given tick."""
        return list(self._events_by_tick.get(tick, []))

