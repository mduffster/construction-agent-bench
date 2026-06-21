from __future__ import annotations

from typing import Any

from constructbench.state import Event, RunState


def record_event(
    state: RunState,
    events: list[Event],
    event_type: str,
    *,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        event_id=f"evt_{len(events) + 1:06d}",
        phase_index=state.phase_index,
        event_type=event_type,
        actor_id=actor_id,
        details=details or {},
    )
    events.append(event)
    return event


def replay_events(initial_state: RunState, events: list[Event]) -> RunState:
    state = initial_state.model_copy(deep=True)
    for event in events:
        state_after = event.details.get("state_after")
        if state_after is not None:
            state = RunState.model_validate(state_after)
    return state
