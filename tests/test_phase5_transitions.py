from pathlib import Path

from constructbench.config import load_agent_configs, load_project_config
from constructbench.enums import AgentRole, CommunicationVisibility, DecisionType
from constructbench.models import (
    AgentRuntimeRecord,
    AgentSubmission,
    AgentTurnResult,
    Communication,
    CounterpartyAssessment,
    DecisionSubmission,
    StateStore,
    ValidationResult,
)
from constructbench.observations import ObservationBuilder
from constructbench.state import initialize_state
from constructbench.transitions import TransitionResolver

ROOT = Path(__file__).resolve().parents[1]


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def test_forecast_submission_updates_task_and_public_ledger() -> None:
    state = _state()
    observation = ObservationBuilder().build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"expected_steel_delivery_tick": 18, "forecast_cost": 12_012_000},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.STEEL_SUPPLIER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    result = TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    assert state.canonical.tasks["steel_delivery"].forecast_end_tick == 18
    assert state.canonical.tasks["steel_delivery"].forecast_cost == 12_012_000
    assert state.public.ledger[-1].entry_type.value == "project_forecast"
    assert [transition.transition_type for transition in result.applied] == [
        "task_forecast_updated",
        "forecast_published",
    ]


def test_private_communication_queues_private_message() -> None:
    state = _state()
    observation = ObservationBuilder().build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=Communication(
            visibility=CommunicationVisibility.PRIVATE,
            recipients=[AgentRole.GENERAL_CONTRACTOR],
            summary="Steel delivery forecast is at risk.",
            linked_object_id="steel_contract",
        ),
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.STEEL_SUPPLIER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    result = TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
        message_delay_ticks=1,
    )

    assert len(state.private_messages) == 1
    assert state.private_messages[0].deliver_tick == 10
    assert state.private_messages[0].message.recipients == [AgentRole.GENERAL_CONTRACTOR]
    assert result.applied[0].transition_type == "private_message_queued"


def test_forecast_submission_without_parameters_does_not_use_private_delivery_forecast() -> None:
    state = _state()
    state.private_by_agent[AgentRole.STEEL_SUPPLIER].data["current_delivery_forecast"] = 18
    observation = ObservationBuilder().build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.STEEL_SUPPLIER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    assert state.canonical.tasks["steel_delivery"].forecast_end_tick == 14


def test_forecast_submission_uses_agent_selected_delivery_forecast() -> None:
    state = _state()
    state.private_by_agent[AgentRole.STEEL_SUPPLIER].data["current_delivery_forecast"] = 19
    state.private_by_agent[AgentRole.STEEL_SUPPLIER].data["current_input_cost"] = 12_500_000
    observation = ObservationBuilder().build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"forecast_end_tick": 18, "forecast_cost": 12_012_000},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.STEEL_SUPPLIER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    task = state.canonical.tasks["steel_delivery"]
    assert task.forecast_end_tick == 18
    assert task.forecast_cost == 12_012_000


def test_explicit_expedite_strategy_maps_spend_to_delivery_and_cash() -> None:
    state = _state()
    state.private_by_agent[AgentRole.STEEL_SUPPLIER].data.update(
        {
            "current_delivery_forecast": 20,
            "current_input_cost": 12_500_000,
            "expedite_cost": 1_000_000,
            "expedited_delivery_tick": 16,
        },
    )
    starting_cash = state.canonical.agent_finances[AgentRole.STEEL_SUPPLIER].cash_available
    observation = ObservationBuilder().build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"strategy": "partial_expedite", "expedite_spend": 500_000},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.STEEL_SUPPLIER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    task = state.canonical.tasks["steel_delivery"]
    assert task.forecast_end_tick == 18
    assert task.forecast_cost == 13_000_000
    assert (
        state.canonical.agent_finances[AgentRole.STEEL_SUPPLIER].cash_available
        == starting_cash - 500_000
    )


def test_labor_schedule_updates_planned_end_with_delayed_start() -> None:
    state = _state()
    state.private_by_agent[AgentRole.LABOR_SUBCONTRACTOR].data["current_crew_schedule"] = {
        "steel_erection": {"start_tick": 24, "end_tick": 29},
    }
    observation = ObservationBuilder().build(AgentRole.LABOR_SUBCONTRACTOR, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SCHEDULE,
            object_type="labor_crew",
            parameters={"strategy": "hold_crew"},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.LABOR_SUBCONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    task = state.canonical.tasks["steel_erection"]
    assert task.planned_start_tick == 24
    assert task.planned_end_tick == 29
    assert task.forecast_end_tick == 29


def test_labor_schedule_uses_agent_selected_schedule() -> None:
    state = _state()
    state.private_by_agent[AgentRole.LABOR_SUBCONTRACTOR].data["current_crew_schedule"] = {
        "steel_erection": {"start_tick": 20, "end_tick": 25},
    }
    observation = ObservationBuilder().build(AgentRole.LABOR_SUBCONTRACTOR, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SCHEDULE,
            object_type="labor_crew",
            parameters={"start_tick": 17, "end_tick": 21},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.LABOR_SUBCONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    task = state.canonical.tasks["steel_erection"]
    assert task.planned_start_tick == 17
    assert task.planned_end_tick == 21
    assert task.forecast_end_tick == 21


def test_counterparty_assessment_updates_agent_owned_private_trust() -> None:
    state = _state()
    observation = ObservationBuilder().build(AgentRole.GENERAL_CONTRACTOR, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=None,
        belief_update=observation.current_beliefs,
        counterparty_assessments=[
            CounterpartyAssessment(
                target=AgentRole.STEEL_SUPPLIER,
                trust_score=0.61,
                confidence=0.7,
                basis_ids=["baseline_plan"],
                reason="Supplier reliability is uncertain after schedule risk.",
            ),
        ],
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.GENERAL_CONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    result = TransitionResolver().apply(
        agent_turn=AgentTurnResult(tick=9, records=[record]),
        state=state,
    )

    assert (
        state.agent_trust_by_agent[AgentRole.GENERAL_CONTRACTOR][
            AgentRole.STEEL_SUPPLIER
        ].score
        == 0.61
    )
    assert (
        state.trust_by_agent[AgentRole.GENERAL_CONTRACTOR][
            AgentRole.STEEL_SUPPLIER
        ].score
        == 0.75
    )
    assert result.applied[0].transition_type == "agent_trust_assessed"
