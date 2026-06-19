from pathlib import Path

from constructbench.agents import LLMPolicy, ScriptedPolicy
from constructbench.config import (
    load_agent_configs,
    load_project_config,
    load_scenario_config,
)
from constructbench.enums import AgentRole, CommunicationVisibility, DecisionType
from constructbench.models import (
    AgentRuntimeRecord,
    AgentSubmission,
    Claim,
    Communication,
    DecisionSubmission,
    ModelSettings,
    StateStore,
    ValidationResult,
)
from constructbench.observations import ObservationBuilder
from constructbench.runner import SimulationRunner
from constructbench.runtime import AgentManager, BeliefUpdateHandler, default_scripted_policies
from constructbench.state import initialize_state
from constructbench.validation import SubmissionValidator

ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []

    def generate(self, prompt: str, settings: ModelSettings) -> str:
        self.prompts.append(prompt)
        return self.outputs.pop(0)


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def _runner() -> SimulationRunner:
    scenario_config = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")
    return SimulationRunner(_state(), scenario_config)


def _none_submission_json() -> str:
    return """
    {
      "decision": {"type": "none", "object_type": null, "object_id": null, "parameters": {}},
      "communication": null,
      "belief_update": {
        "expected_completion_tick": 40,
        "expected_final_cost": 95000000,
        "probability_on_time": 0.85,
        "probability_within_budget": 0.85,
        "confidence": 0.8,
        "basis_ids": ["baseline_plan"]
      }
    }
    """


def test_observation_builder_filters_public_private_and_role_objects() -> None:
    runner = _runner()
    runner.run_until(8)
    tick_9 = runner.advance_tick()

    observation = ObservationBuilder().build(
        AgentRole.STEEL_SUPPLIER,
        runner.state,
        tick_9.delivered,
    )

    assert observation.tick == 9
    assert observation.private_state["current_expected_input_cost"] == 12_012_000
    assert "undisbursed_loan_balance" not in observation.private_state
    assert {task.task_id for task in observation.relevant_tasks} >= {
        "steel_procurement",
        "steel_fabrication",
        "steel_delivery",
    }
    assert [contract.contract_id for contract in observation.relevant_contracts] == [
        "steel_contract",
    ]
    assert observation.available_decisions == runner.state.role_configs[
        AgentRole.STEEL_SUPPLIER
    ].permitted_decisions
    assert AgentRole.GENERAL_CONTRACTOR in observation.trust_in_counterparties


def test_scripted_agents_can_process_deterministic_active_ticks() -> None:
    runner = _runner()
    manager = AgentManager(default_scripted_policies())

    tick_results = runner.run_until(9)
    turn_results = [manager.process_tick(result, runner.state) for result in tick_results]
    active_turns = [turn for turn in turn_results if turn.records]

    assert [turn.tick for turn in active_turns] == [8, 9]
    assert len(active_turns[0].records) == 6
    assert len(active_turns[1].records) == 1
    assert all(record.validation.valid for turn in active_turns for record in turn.records)
    assert {
        record.submission.decision.type for record in active_turns[0].records
    } == {
        DecisionType.INSPECT,
        DecisionType.REQUEST_INFORMATION,
        DecisionType.SCHEDULE,
        DecisionType.SUBMIT_FORECAST,
    }
    supplier_record = active_turns[1].records[0]
    assert supplier_record.agent_id == AgentRole.STEEL_SUPPLIER
    assert supplier_record.submission.decision.type == DecisionType.SUBMIT_FORECAST


def test_llm_policy_returns_valid_structured_submission() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    adapter = FakeAdapter([_none_submission_json()])
    policy = LLMPolicy(
        adapter=adapter,
        settings=ModelSettings(model_id="fake_local_model"),
    )
    manager = AgentManager({AgentRole.OWNER_DEVELOPER: policy})

    result = manager.process_tick(tick_result, runner.state)
    owner_record = next(
        record for record in result.records if record.agent_id == AgentRole.OWNER_DEVELOPER
    )

    assert owner_record.validation.valid
    assert owner_record.submission.decision.type == DecisionType.NONE
    assert owner_record.used_fallback is False
    assert len(adapter.prompts) == 1
    assert "primary actor for the organization" in adapter.prompts[0]
    assert "advance the role_goals" in adapter.prompts[0]
    assert "current constraints and information" in adapter.prompts[0]
    assert "0.75 means established working trust" in adapter.prompts[0]


def test_llm_policy_repairs_malformed_output_once() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    adapter = FakeAdapter(["not json", _none_submission_json()])
    policy = LLMPolicy(
        adapter=adapter,
        settings=ModelSettings(model_id="fake_local_model"),
    )
    manager = AgentManager({AgentRole.OWNER_DEVELOPER: policy})

    result = manager.process_tick(tick_result, runner.state)
    owner_record = next(
        record for record in result.records if record.agent_id == AgentRole.OWNER_DEVELOPER
    )

    assert owner_record.validation.valid
    assert owner_record.used_fallback is False
    assert owner_record.parse_errors[0].startswith("invalid_json")
    assert len(adapter.prompts) == 2


def test_invalid_llm_output_uses_fallback_submission() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    adapter = FakeAdapter(["not json", "still not json"])
    policy = LLMPolicy(
        adapter=adapter,
        settings=ModelSettings(model_id="fake_local_model"),
    )
    manager = AgentManager({AgentRole.OWNER_DEVELOPER: policy})

    result = manager.process_tick(tick_result, runner.state)
    owner_record = next(
        record for record in result.records if record.agent_id == AgentRole.OWNER_DEVELOPER
    )

    assert owner_record.validation.valid
    assert owner_record.used_fallback
    assert owner_record.submission.decision.type == DecisionType.NONE
    assert len(owner_record.parse_errors) == 2


def test_submission_validator_enforces_role_permissions_and_manager_falls_back() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    invalid_supplier_submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.PAY, object_type="invoice"),
        communication=None,
        belief_update=runner.state.beliefs_by_agent[AgentRole.STEEL_SUPPLIER],
    )
    validation = SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        invalid_supplier_submission,
        runner.state,
    )
    assert not validation.valid
    assert "decision_type_not_permitted:pay" in validation.errors

    manager = AgentManager(
        {AgentRole.STEEL_SUPPLIER: ScriptedPolicy(invalid_supplier_submission)},
    )
    result = manager.process_tick(tick_result, runner.state)
    supplier_record = next(
        record for record in result.records if record.agent_id == AgentRole.STEEL_SUPPLIER
    )
    assert supplier_record.used_fallback
    assert supplier_record.validation.valid
    assert supplier_record.submission.decision.type == DecisionType.NONE


def test_valid_belief_update_changes_only_submitting_agent_belief() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    updated_belief = runner.state.beliefs_by_agent[AgentRole.OWNER_DEVELOPER].model_copy(
        update={
            "expected_completion_tick": 42,
            "basis_ids": ["baseline_plan", "public_steel_shock"],
        },
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=None,
        belief_update=updated_belief,
    )
    manager = AgentManager({AgentRole.OWNER_DEVELOPER: ScriptedPolicy(submission)})

    manager.process_tick(tick_result, runner.state)

    assert runner.state.beliefs_by_agent[AgentRole.OWNER_DEVELOPER].expected_completion_tick == 42
    assert runner.state.beliefs_by_agent[AgentRole.STEEL_SUPPLIER].expected_completion_tick == 40
    assert runner.state.canonical.forecast_completion_tick == 40


def test_belief_handler_promotes_numbers_from_communication_summary() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    observation = ObservationBuilder().build(
        AgentRole.OWNER_DEVELOPER,
        runner.state,
        tick_result.delivered,
    )
    unchanged_belief = observation.current_beliefs.model_copy(deep=True)
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=Communication(
            visibility=CommunicationVisibility.PUBLIC,
            summary=(
                "After the steel shock, expected_completion_tick is 42, "
                "expected final cost is $97,000,000, and probability_on_time is 55%."
            ),
        ),
        belief_update=unchanged_belief,
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.OWNER_DEVELOPER,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    BeliefUpdateHandler().apply(AgentRole.OWNER_DEVELOPER, runner.state, record)

    belief = runner.state.beliefs_by_agent[AgentRole.OWNER_DEVELOPER]
    assert belief.expected_completion_tick == 42
    assert belief.expected_final_cost == 97_000_000
    assert belief.probability_on_time == 0.55
    assert runner.state.beliefs_by_agent[AgentRole.STEEL_SUPPLIER].expected_completion_tick == 40
    assert runner.state.canonical.forecast_completion_tick == 40


def test_belief_handler_promotes_numbers_from_claims_and_raw_output() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    observation = ObservationBuilder().build(
        AgentRole.GENERAL_CONTRACTOR,
        runner.state,
        tick_result.delivered,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=Communication(
            visibility=CommunicationVisibility.PUBLIC,
            summary="The GC is revising the forecast.",
            claims=[
                Claim(field="expected_completion_tick", value=43, unit="tick", confidence=0.7),
            ],
        ),
        belief_update=observation.current_beliefs.model_copy(deep=True),
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.GENERAL_CONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
        raw_output="probability_within_budget: 62%",
    )

    BeliefUpdateHandler().apply(AgentRole.GENERAL_CONTRACTOR, runner.state, record)

    belief = runner.state.beliefs_by_agent[AgentRole.GENERAL_CONTRACTOR]
    assert belief.expected_completion_tick == 43
    assert belief.probability_within_budget == 0.62
    assert runner.state.canonical.forecast_completion_tick == 40


def test_belief_handler_adds_delivered_event_ids_to_basis() -> None:
    runner = _runner()
    tick_result = runner.run_until(8)[-1]
    observation = ObservationBuilder().build(
        AgentRole.LABOR_SUBCONTRACTOR,
        runner.state,
        tick_result.delivered,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(type=DecisionType.NONE),
        communication=None,
        belief_update=observation.current_beliefs.model_copy(deep=True),
    )
    record = AgentRuntimeRecord(
        agent_id=AgentRole.LABOR_SUBCONTRACTOR,
        observation=observation,
        submission=submission,
        validation=ValidationResult(valid=True),
    )

    BeliefUpdateHandler().apply(AgentRole.LABOR_SUBCONTRACTOR, runner.state, record)

    belief = runner.state.beliefs_by_agent[AgentRole.LABOR_SUBCONTRACTOR]
    assert belief.basis_ids == ["baseline_plan", "public_steel_market_tick_8"]
