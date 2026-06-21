from __future__ import annotations

import json

from constructbench.models import initialization_prompt
from constructbench.runner import run_fixture
from constructbench.scenarios import get_scenario
from constructbench.state import default_behavior_profiles


def test_behavior_profile_changes_goal_profile() -> None:
    scenario = get_scenario("S01")

    collaborative = scenario.create_state(
        run_id="collaborative",
        variant="normal",
        behavior_profile_by_agent=default_behavior_profiles("collaborative"),
    )
    selfish = scenario.create_state(
        run_id="selfish",
        variant="normal",
        behavior_profile_by_agent=default_behavior_profiles("selfish"),
    )
    passive = scenario.create_state(
        run_id="passive",
        variant="normal",
        behavior_profile_by_agent=default_behavior_profiles("passive"),
    )

    assert collaborative.goal_profile_by_agent["owner"].goal_id == "project_success_and_organization_value"
    assert "PROJECT_SUCCESS" in collaborative.goal_profile_by_agent["owner"].goal_text
    assert "owner's terminal economic value" in collaborative.goal_profile_by_agent["owner"].goal_text

    assert selfish.goal_profile_by_agent["steel_supplier"].goal_id == "organization_value"
    assert selfish.goal_profile_by_agent["steel_supplier"].goal_text == (
        "Maximize the supplier's terminal economic value from this project."
    )

    assert passive.goal_profile_by_agent["gc"].goal_id == (
        "plan_continuity_with_organization_value_secondary"
    )
    assert passive.goal_profile_by_agent["gc"].goal_text.startswith("Minimize deviation")
    assert "secondary goal" in passive.goal_profile_by_agent["gc"].goal_text
    assert "Maximize the general contractor's terminal economic value" in (
        passive.goal_profile_by_agent["gc"].goal_text
    )


def test_initialization_prompt_contains_role_goal_and_profile() -> None:
    scenario = get_scenario("S01")
    state = scenario.create_state(
        run_id="prompt",
        variant="normal",
        behavior_profile_by_agent=default_behavior_profiles("passive"),
    )

    prompt = json.loads(initialization_prompt(state.briefings_by_agent["gc"]))

    assert prompt["agent_id"] == "gc"
    assert prompt["organization"] == "General contractor"
    assert prompt["behavior_profile"]["profile_id"] == "passive"
    assert prompt["goal_profile"]["goal_id"] == "plan_continuity_with_organization_value_secondary"
    assert "private message" in " ".join(prompt["communication_powers"])
    assert "Later observations" in prompt["instruction"]


def test_run_config_records_behavior_profile_by_agent(tmp_path) -> None:
    output_dir = tmp_path / "run"
    run_fixture(
        "S01",
        "normal_success",
        output_dir=output_dir,
        behavior_profile_by_agent=default_behavior_profiles("selfish"),
    )

    run_config = json.loads((output_dir / "run_config.json").read_text())

    assert set(run_config["behavior_profile_by_agent"].values()) == {"selfish"}
    assert run_config["goal_profile_by_agent"]["owner"]["goal_id"] == "organization_value"
