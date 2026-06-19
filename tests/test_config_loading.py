from pathlib import Path

from constructbench.config import load_agent_configs, load_project_config
from constructbench.enums import AgentRole, BehaviorProfile, DecisionType, ResourceConditionLevel

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_project_config_loads() -> None:
    config = load_project_config(ROOT / "configs" / "project_baseline.yaml")

    assert config.project_id == "baseline_steel_shock"
    assert config.canonical.baseline_cost == 95_000_000
    assert config.canonical.approved_budget == 100_000_000
    assert config.canonical.target_completion_tick == 40
    assert config.initial_belief.expected_completion_tick == 40
    assert config.initial_belief.expected_final_cost == 95_000_000


def test_agent_configs_load_all_six_roles() -> None:
    configs = load_agent_configs(ROOT / "configs" / "agents")

    assert set(configs) == {role.value for role in AgentRole}
    steel_supplier = configs["steel_supplier"]
    assert steel_supplier.role_id == AgentRole.STEEL_SUPPLIER
    assert "cash_available" in steel_supplier.private_state_fields
    assert any(
        decision.decision_type == DecisionType.SUBMIT_REQUEST
        for decision in steel_supplier.permitted_decisions
    )
    assert set(steel_supplier.resource_condition_presets) == set(ResourceConditionLevel)
    assert set(steel_supplier.behavior_profile_presets) == set(BehaviorProfile)
    assert (
        steel_supplier.resource_condition_presets[ResourceConditionLevel.STRAINED]
        .data["current_delivery_forecast"]
        == 19
    )
