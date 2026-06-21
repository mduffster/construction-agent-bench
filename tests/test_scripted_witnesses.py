from __future__ import annotations

import pytest

from constructbench.runner import run_fixture
from constructbench.scenarios import SCENARIOS

CASES = [
    (scenario_key, fixture_name)
    for scenario_key, scenario in SCENARIOS.items()
    for fixture_name in scenario.fixtures
]


@pytest.mark.parametrize(("scenario_key", "fixture_name"), CASES)
def test_scripted_witness_matches_plan(scenario_key: str, fixture_name: str) -> None:
    scenario = SCENARIOS[scenario_key]
    expected = scenario.fixtures[fixture_name]["expected"]

    result = run_fixture(scenario_key, fixture_name)
    state = result.final_state
    project = state.canonical_state["project"]

    assert state.run_valid
    if "status" in expected:
        assert state.terminal_status == expected["status"]
    else:
        assert state.terminal_status in expected["status_any_of"]
    assert project["project_cost"] == expected["final_project_cost"]
    assert project["completion_tick"] == expected["completion_tick"]
    for key, value in expected.items():
        if key not in {"status", "status_any_of", "final_project_cost", "completion_tick"}:
            assert project[key] == value
    if scenario.actors:
        assert state.histories["decision_history"]
    else:
        assert state.histories["decision_history"] == []
    assert state.histories["invalid_outputs"] == []
