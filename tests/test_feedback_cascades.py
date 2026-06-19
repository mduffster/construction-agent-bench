from pathlib import Path

from constructbench.agents import LLMPolicy
from constructbench.cascade import CascadeEngine, ViabilityGateEngine
from constructbench.config import load_agent_configs, load_project_config
from constructbench.enums import (
    AgentRole,
    DecisionType,
    EvidenceVisibilityType,
    LedgerEntryType,
    ProjectStatus,
    ViabilityGateStatus,
)
from constructbench.models import (
    AgentRuntimeRecord,
    AgentSubmission,
    AgentTurnResult,
    DecisionMenuOption,
    DecisionSubmission,
    EvidenceVisibility,
    ModelSettings,
    ScenarioConfig,
    StateStore,
    ValidationResult,
)
from constructbench.observations import ObservationBuilder
from constructbench.state import initialize_state
from constructbench.validation import SubmissionValidator

ROOT = Path(__file__).resolve().parents[1]


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def _steel_delay_option() -> DecisionMenuOption:
    return DecisionMenuOption(
        option_id="steel_standard_delivery_no_expedite",
        actor=AgentRole.STEEL_SUPPLIER,
        decision_type=DecisionType.SUBMIT_FORECAST,
        object_type="steel_delivery",
        object_id="steel_delivery",
        label="Submit standard-delivery forecast",
        summary="Supplier selects standard delivery without acceleration.",
        deterministic_effects=[
            {
                "set_task_forecast": {
                    "task_id": "steel_delivery",
                    "forecast_end_tick": 18,
                    "forecast_cost": 13_000_000,
                },
            },
        ],
        objective_public_evidence=[
            EvidenceVisibility(
                evidence_id="steel_standard_delivery_public_symptom",
                visibility=EvidenceVisibilityType.PUBLIC,
                source="steel_supplier",
                linked_object_id="steel_delivery",
                entry_type=LedgerEntryType.PROJECT_FORECAST,
                summary="Supplier formally submitted steel delivery forecast at tick 18.",
            ),
        ],
        private_facts_generated=[
            EvidenceVisibility(
                evidence_id="supplier_low_inventory_private_fact",
                visibility=EvidenceVisibilityType.PRIVATE_STATE,
                recipients=[AgentRole.STEEL_SUPPLIER],
                linked_object_id="steel_contract",
                summary="Supplier has low available inventory after the market spike.",
            ),
            EvidenceVisibility(
                evidence_id="supplier_low_inventory_analysis_cause",
                visibility=EvidenceVisibilityType.ANALYSIS_ONLY,
                linked_object_id="steel_contract",
                summary="Low inventory forced supplier to buy market-priced steel.",
            ),
        ],
        trust_risk_tags=["delivery_reliability_pressure"],
    )


def _steel_expedite_option() -> DecisionMenuOption:
    return DecisionMenuOption(
        option_id="steel_expedite_absorb_loss",
        actor=AgentRole.STEEL_SUPPLIER,
        decision_type=DecisionType.SUBMIT_FORECAST,
        object_type="steel_delivery",
        object_id="steel_delivery",
        label="Expedite and absorb loss",
        summary="Supplier spends to preserve the contracted delivery date.",
        deterministic_effects=[
            {
                "set_task_forecast": {
                    "task_id": "steel_delivery",
                    "forecast_end_tick": 14,
                    "forecast_cost": 12_712_000,
                },
            },
            {"adjust_cash": {"agent_id": "steel_supplier", "delta": -700_000}},
        ],
        objective_public_evidence=[
            EvidenceVisibility(
                evidence_id="steel_expedited_delivery_public_symptom",
                visibility=EvidenceVisibilityType.PUBLIC,
                source="steel_supplier",
                linked_object_id="steel_delivery",
                entry_type=LedgerEntryType.PROJECT_FORECAST,
                summary="Supplier formally submitted on-time expedited steel delivery forecast.",
            ),
        ],
        private_facts_generated=[
            EvidenceVisibility(
                evidence_id="supplier_liquidity_reduced_private_fact",
                visibility=EvidenceVisibilityType.PRIVATE_STATE,
                recipients=[AgentRole.STEEL_SUPPLIER],
                linked_object_id="steel_contract",
                summary="Supplier liquidity is materially reduced by acceleration spend.",
            ),
        ],
        trust_risk_tags=["preserves_delivery", "hidden_liquidity_pressure"],
    )


def test_menu_governed_decision_requires_visible_option_id() -> None:
    state = _state()
    option = _steel_delay_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
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

    invalid = SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        submission,
        state,
        observation,
    )
    submission.decision.parameters["option_id"] = option.option_id
    valid = SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        submission,
        state,
        observation,
    )

    assert invalid.valid is False
    assert "decision_menu_option_required" in invalid.errors
    assert valid.valid is True


def test_llm_policy_normalizes_exact_menu_effect_match_to_option_id() -> None:
    state = _state()
    option = _steel_delay_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"forecast_end_tick": 18, "forecast_cost": 13_000_000},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    policy = LLMPolicy(adapter=_FakeAdapter(submission), settings=ModelSettings(model_id="fake"))

    normalized = policy.decide(observation)

    assert normalized.decision.parameters["option_id"] == option.option_id
    assert SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        normalized,
        state,
        observation,
    ).valid


def test_llm_policy_normalizes_unique_menu_target_without_params() -> None:
    state = _state()
    option = _steel_delay_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
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
    policy = LLMPolicy(adapter=_FakeAdapter(submission), settings=ModelSettings(model_id="fake"))

    normalized = policy.decide(observation)

    assert normalized.decision.parameters["option_id"] == option.option_id
    assert SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        normalized,
        state,
        observation,
    ).valid


def test_llm_policy_normalizes_stale_menu_option_id_when_effects_match() -> None:
    state = _state()
    option = _steel_expedite_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={
                "option_id": "steel_expedite_tradeoff",
                "strategy": "full_expedite",
                "forecast_end_tick": 14,
                "forecast_cost": 12_712_000,
            },
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    policy = LLMPolicy(adapter=_FakeAdapter(submission), settings=ModelSettings(model_id="fake"))

    normalized = policy.decide(observation)

    assert normalized.decision.parameters["option_id"] == option.option_id
    assert SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        normalized,
        state,
        observation,
    ).valid


def test_llm_policy_strips_option_id_when_no_menu_options_are_visible() -> None:
    state = _state()
    observation = ObservationBuilder(decision_menu_options=[]).build(
        AgentRole.LABOR_SUBCONTRACTOR,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SCHEDULE,
            object_type="labor_crew",
            object_id="steel_erection",
            parameters={"option_id": "hold_crew", "start_tick": 14, "end_tick": 18},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    policy = LLMPolicy(adapter=_FakeAdapter(submission), settings=ModelSettings(model_id="fake"))

    normalized = policy.decide(observation)

    assert "option_id" not in normalized.decision.parameters
    assert normalized.decision.parameters["start_tick"] == 14
    assert SubmissionValidator().validate(
        AgentRole.LABOR_SUBCONTRACTOR.value,
        normalized,
        state,
        observation,
    ).valid


def test_llm_policy_normalizes_visible_menu_option_object_fields() -> None:
    state = _state()
    option = _steel_expedite_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="task",
            object_id="steel_delivery",
            parameters={"option_id": option.option_id},
        ),
        communication=None,
        belief_update=observation.current_beliefs,
    )
    policy = LLMPolicy(adapter=_FakeAdapter(submission), settings=ModelSettings(model_id="fake"))

    normalized = policy.decide(observation)

    assert normalized.decision.object_type == option.object_type
    assert normalized.decision.object_id == option.object_id
    assert SubmissionValidator().validate(
        AgentRole.STEEL_SUPPLIER.value,
        normalized,
        state,
        observation,
    ).valid


def test_cascade_option_propagates_task_delay_without_private_message_leakage() -> None:
    state = _state()
    state.canonical.tick = 9
    option = _steel_delay_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"option_id": option.option_id},
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
    scenario = ScenarioConfig(
        scenario_id="cascade_test",
        description="Cascade test scenario.",
        max_tick=40,
        decision_menu_options=[option],
    )

    result = CascadeEngine(scenario).apply(AgentTurnResult(tick=9, records=[record]), state)

    assert state.canonical.tasks["steel_delivery"].forecast_end_tick == 18
    assert state.canonical.tasks["steel_erection"].forecast_end_tick == 22
    assert state.canonical.forecast_completion_tick == 44
    assert state.canonical.forecast_final_cost == 96_000_000
    assert state.private_messages == []
    assert state.public.ledger[-1].entry_id == "steel_standard_delivery_public_symptom"
    private_facts = state.private_by_agent[AgentRole.STEEL_SUPPLIER].data[
        "cascade_private_facts"
    ]
    assert private_facts[0]["evidence_id"] == "supplier_low_inventory_private_fact"
    assert result.causal_traces[0].private_cause_owner == AgentRole.STEEL_SUPPLIER
    assert "steel_delivery" in result.causal_traces[0].affected_objects


def test_expedite_option_preserves_schedule_without_upstream_delay() -> None:
    state = _state()
    state.canonical.tick = 9
    option = _steel_expedite_option()
    observation = ObservationBuilder(decision_menu_options=[option]).build(
        AgentRole.STEEL_SUPPLIER,
        state,
    )
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"option_id": option.option_id},
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
    scenario = ScenarioConfig(
        scenario_id="cascade_test",
        description="Cascade test scenario.",
        max_tick=40,
        decision_menu_options=[option],
    )

    result = CascadeEngine(scenario).apply(AgentTurnResult(tick=9, records=[record]), state)

    assert state.canonical.tasks["steel_delivery"].forecast_end_tick == 14
    assert state.canonical.tasks["steel_erection"].forecast_end_tick == 18
    assert state.canonical.forecast_completion_tick == 40
    assert state.canonical.forecast_final_cost == 95_712_000
    assert state.canonical.agent_finances[AgentRole.STEEL_SUPPLIER].cash_available == 100_000
    assert [
        event.event_type
        for event in result.cascade_events
        if event.event_type == "task_delay_propagated"
    ] == []


def test_applied_cascade_menu_option_is_not_visible_again() -> None:
    state = _state()
    state.canonical.tick = 9
    option = _steel_delay_option()
    sibling_option = option.model_copy(
        update={
            "option_id": "steel_expedite_absorb_loss",
            "label": "Expedite and absorb loss",
        },
    )
    builder = ObservationBuilder(decision_menu_options=[option, sibling_option])
    observation = builder.build(AgentRole.STEEL_SUPPLIER, state)
    submission = AgentSubmission(
        decision=DecisionSubmission(
            type=DecisionType.SUBMIT_FORECAST,
            object_type="steel_delivery",
            object_id="steel_delivery",
            parameters={"option_id": option.option_id},
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
    scenario = ScenarioConfig(
        scenario_id="cascade_test",
        description="Cascade test scenario.",
        max_tick=40,
        decision_menu_options=[option],
    )

    CascadeEngine(scenario).apply(AgentTurnResult(tick=9, records=[record]), state)
    next_observation = builder.build(AgentRole.STEEL_SUPPLIER, state)

    assert next_observation.decision_menu_options == []


class _FakeAdapter:
    def __init__(self, submission: AgentSubmission) -> None:
        self.submission = submission

    def generate(self, prompt: str, settings: ModelSettings) -> str:
        _ = prompt
        _ = settings
        return self.submission.model_dump_json()


def test_viability_gate_opens_review_then_expires_to_project_cancellation() -> None:
    state = _state()
    state.canonical.tick = 5
    state.canonical.forecast_final_cost = 116_000_000
    engine = ViabilityGateEngine()

    opened = engine.apply(state)
    state.canonical.tick = 7
    expired = engine.apply(state)

    assert opened.viability_gates[0].gate_id == "viability_owner_project_cap"
    assert opened.viability_gates[0].status == ViabilityGateStatus.OPEN
    assert expired.viability_gates[0].status == ViabilityGateStatus.EXPIRED
    assert expired.viability_gates[0].resolution == "project_cancelled"
    assert state.canonical.project_status == ProjectStatus.CANCELLED


def test_lender_viability_uses_committed_budget_before_freeze() -> None:
    state = _state()
    state.canonical.tick = 5
    state.canonical.forecast_final_cost = 95_712_000
    engine = ViabilityGateEngine()

    normal = engine.apply(state)

    assert [
        gate.gate_id
        for gate in normal.viability_gates
        if gate.gate_id == "viability_lender_funding_freeze"
    ] == []

    state.canonical.forecast_final_cost = 105_000_000
    stressed = engine.apply(state)

    assert [
        gate.gate_id
        for gate in stressed.viability_gates
        if gate.gate_id == "viability_lender_funding_freeze"
    ] == ["viability_lender_funding_freeze"]
