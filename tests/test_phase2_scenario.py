from pathlib import Path

from constructbench.config import (
    load_agent_configs,
    load_project_config,
    load_scenario_config,
)
from constructbench.enums import AgentRole, LedgerEntryType, ScheduledEventType
from constructbench.models import (
    PrivateMessageEventConfig,
    ScenarioConfig,
    ScheduledEventConfig,
)
from constructbench.runner import SimulationRunner
from constructbench.scenarios import ScenarioEngine
from constructbench.state import export_state_snapshot, initialize_state

ROOT = Path(__file__).resolve().parents[1]


def _runner() -> SimulationRunner:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    scenario_config = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")
    state = initialize_state(project_config, role_configs)
    return SimulationRunner(state, scenario_config)


def test_steel_shock_scenario_loads_with_scheduled_events_and_deadlines() -> None:
    scenario = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")

    assert scenario.scenario_id == "steel_shock"
    assert scenario.max_tick == 40
    assert scenario.default_message_delay_ticks == 1
    assert [event.tick for event in scenario.scheduled_events] == [8, 9]
    assert scenario.scheduled_events[0].event_type == ScheduledEventType.PUBLIC_LEDGER_ENTRY
    assert scenario.scheduled_events[1].event_type == ScheduledEventType.PRIVATE_STATE_UPDATE
    assert scenario.task_deadlines[0].object_id == "steel_delivery"
    assert scenario.contract_consequence_deadlines[0].object_id == "steel_contract"


def test_scenario_engine_returns_events_for_tick() -> None:
    scenario = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")
    engine = ScenarioEngine(scenario)

    assert engine.events_for_tick(7) == []
    assert len(engine.events_for_tick(8)) == 1
    assert len(engine.events_for_tick(9)) == 1


def test_public_event_is_delivered_to_all_agents_at_tick_8() -> None:
    runner = _runner()

    results = runner.run_until(8)
    tick_8 = results[-1]

    assert tick_8.tick == 8
    assert len(tick_8.delivered.public_entries) == 1
    public_entry = tick_8.delivered.public_entries[0]
    assert public_entry.entry_type == LedgerEntryType.MARKET_UPDATE
    assert public_entry.data["steel_price_index_change_percent"] == 18
    assert set(tick_8.active_agents) == set(AgentRole)
    assert runner.state.public.ledger == [public_entry]


def test_private_supplier_assessment_is_only_delivered_to_supplier_at_tick_9() -> None:
    runner = _runner()

    runner.run_until(8)
    tick_9 = runner.advance_tick()

    assert tick_9.tick == 9
    assert tick_9.delivered.public_entries == []
    assert set(tick_9.delivered.private_events_by_agent) == {AgentRole.STEEL_SUPPLIER}
    supplier_event = tick_9.delivered.private_events_by_agent[AgentRole.STEEL_SUPPLIER][0]
    assert supplier_event.event_id == "supplier_impact_tick_9"
    assert supplier_event.data["current_expected_input_cost"] == 12_012_000
    assert tick_9.active_agents == [AgentRole.STEEL_SUPPLIER]
    assert (
        runner.state.private_by_agent[AgentRole.STEEL_SUPPLIER].data["standard_delivery_tick"]
        == 18
    )
    assert "current_expected_input_cost" not in runner.state.private_by_agent[
        AgentRole.OWNER_DEVELOPER
    ].data


def test_private_events_do_not_relax_strained_initial_constraints() -> None:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    scenario_config = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")
    state = initialize_state(
        project_config,
        role_configs,
        condition_overrides={role: "strained" for role in AgentRole},
    )
    runner = SimulationRunner(state, scenario_config)

    runner.run_until(9)

    supplier_private = runner.state.private_by_agent[AgentRole.STEEL_SUPPLIER].data
    assert supplier_private["standard_delivery_tick"] == 19
    assert supplier_private["current_delivery_forecast"] == 19
    assert supplier_private["current_input_cost"] == 12_500_000


def test_private_message_appears_at_configured_delivery_tick() -> None:
    runner = _runner()
    message_scenario = ScenarioConfig(
        scenario_id="message_delay_test",
        description="Private message delay test.",
        max_tick=5,
        default_message_delay_ticks=2,
        scheduled_events=[
            ScheduledEventConfig(
                event_type=ScheduledEventType.PRIVATE_MESSAGE,
                private_message=PrivateMessageEventConfig(
                    tick=1,
                    message_id="supplier_to_gc_delay_test",
                    sender=AgentRole.STEEL_SUPPLIER,
                    recipients=[AgentRole.GENERAL_CONTRACTOR],
                    summary="Delivery risk update.",
                    linked_object_id="steel_contract",
                ),
            ),
        ],
    )
    runner = SimulationRunner(runner.state, message_scenario)

    tick_1 = runner.advance_tick()
    tick_2 = runner.advance_tick()
    tick_3 = runner.advance_tick()

    assert tick_1.delivered.private_messages_by_agent == {}
    assert tick_2.delivered.private_messages_by_agent == {}
    assert set(tick_3.delivered.private_messages_by_agent) == {
        AgentRole.STEEL_SUPPLIER,
        AgentRole.GENERAL_CONTRACTOR,
    }
    assert tick_3.active_agents == [
        AgentRole.GENERAL_CONTRACTOR,
        AgentRole.STEEL_SUPPLIER,
    ]
    assert runner.state.private_messages[0].delivered_tick == 3


def test_snapshot_after_scenario_ticks_preserves_delivered_state() -> None:
    runner = _runner()
    runner.run_until(9)

    snapshot = export_state_snapshot(runner.state)

    assert snapshot["canonical"]["tick"] == 9
    assert snapshot["public"]["ledger"][0]["entry_id"] == "public_steel_market_tick_8"
    assert (
        snapshot["private_by_agent"]["steel_supplier"]["data"]["current_expected_input_cost"]
        == 12_012_000
    )
    assert snapshot["private_events_by_agent"]["steel_supplier"][0]["event_id"] == (
        "supplier_impact_tick_9"
    )
