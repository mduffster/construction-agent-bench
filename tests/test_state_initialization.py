from pathlib import Path

from constructbench.config import load_agent_configs, load_project_config
from constructbench.enums import AgentRole, BehaviorProfile, ResourceConditionLevel
from constructbench.models import StateStore
from constructbench.state import initialize_state

ROOT = Path(__file__).resolve().parents[1]


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def test_initialize_state_creates_separate_state_stores() -> None:
    state = _state()

    assert id(state.canonical) != id(state.public)
    assert id(state.private_by_agent) != id(state.beliefs_by_agent)
    assert set(state.private_by_agent) == set(AgentRole)
    assert set(state.beliefs_by_agent) == set(AgentRole)
    assert set(state.role_configs) == set(AgentRole)


def test_all_agents_receive_distinct_private_views() -> None:
    state = _state()

    private_views = state.private_by_agent
    assert private_views[AgentRole.STEEL_SUPPLIER].data["cash_available"] == 800_000
    assert "current_input_cost" in private_views[AgentRole.STEEL_SUPPLIER].data
    assert "current_input_cost" not in private_views[AgentRole.OWNER_DEVELOPER].data
    assert "undisbursed_loan_balance" in private_views[AgentRole.LENDER].data
    assert (
        private_views[AgentRole.LABOR_SUBCONTRACTOR].resource_condition_level
        == ResourceConditionLevel.NORMAL
    )
    assert private_views[AgentRole.LABOR_SUBCONTRACTOR].data["crew_available_tick"] == 14


def test_all_agents_receive_baseline_beliefs() -> None:
    state = _state()

    for belief in state.beliefs_by_agent.values():
        assert belief.expected_completion_tick == 40
        assert belief.expected_final_cost == 95_000_000
        assert belief.probability_on_time == 0.85
        assert belief.probability_within_budget == 0.85
        assert belief.basis_ids == ["baseline_plan"]


def test_canonical_state_contains_task_graph_and_steel_contract() -> None:
    state = _state()

    assert len(state.canonical.tasks) == 13
    assert "steel_contract" in state.canonical.contracts
    assert state.canonical.contracts["steel_contract"].contract_value == 12_000_000
    assert state.canonical.tasks["steel_delivery"].dependencies == ["steel_fabrication"]


def test_state_separation_keeps_private_and_beliefs_out_of_public_and_canonical() -> None:
    state = _state()

    public_snapshot = state.public.model_dump(mode="json")
    canonical_snapshot = state.canonical.model_dump(mode="json")

    assert public_snapshot == {"ledger": []}
    assert "private_by_agent" not in canonical_snapshot
    assert "beliefs_by_agent" not in canonical_snapshot
    assert "current_input_cost" not in str(public_snapshot)


def test_condition_and_behavior_overrides_apply_role_specific_private_data() -> None:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    state = initialize_state(
        project_config,
        role_configs,
        condition_overrides={role: "strained" for role in AgentRole},
        behavior_overrides={role: "selfish" for role in AgentRole},
    )

    labor = state.private_by_agent[AgentRole.LABOR_SUBCONTRACTOR]
    supplier = state.private_by_agent[AgentRole.STEEL_SUPPLIER]
    lender = state.private_by_agent[AgentRole.LENDER]

    assert labor.resource_condition_level == ResourceConditionLevel.STRAINED
    assert labor.behavior_profile == BehaviorProfile.SELFISH
    assert labor.data["crew_available_tick"] == 20
    assert labor.data["current_crew_schedule"]["steel_erection"]["end_tick"] == 25
    assert supplier.data["current_delivery_forecast"] == 19
    assert lender.data["funding_delay_ticks"] == 4
    assert labor.dishonesty_framing is not None
