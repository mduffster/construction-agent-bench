from __future__ import annotations

from typing import Any

from constructbench.state import RunState


def recompute_feasibility(state: RunState, spec: Any) -> dict[str, Any]:
    spec.recompute_feasibility(state)
    return state.feasibility
