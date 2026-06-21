from __future__ import annotations

from constructbench.scenarios import Scenario
from constructbench.state import DecisionSelection, RunState


def apply_validated_decision(
    state: RunState,
    scenario: Scenario,
    selection: DecisionSelection,
) -> None:
    """Apply a decision through the scenario, preserving harness ownership of state."""
    scenario.apply_decision(state, selection)
