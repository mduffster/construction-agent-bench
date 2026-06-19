from pathlib import Path

from constructbench.config import load_agent_configs, load_project_config, load_scenario_config
from constructbench.enums import (
    AgentRole,
    BreachProfile,
    CommunicationVisibility,
    DisclosureAssessmentType,
    ObligationStatus,
    OversightFindingType,
)
from constructbench.models import (
    Claim,
    MaterialFact,
    PrivateMessage,
    PrivateMessageEnvelope,
    PublicLedgerEntry,
    ScenarioConfig,
    StateStore,
)
from constructbench.safety import SafetyEngine
from constructbench.state import initialize_state

ROOT = Path(__file__).resolve().parents[1]


def _state() -> StateStore:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    return initialize_state(project_config, role_configs)


def _scenario() -> ScenarioConfig:
    return load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")


def test_baseline_contains_six_default_contract_obligations() -> None:
    state = _state()

    assert set(state.canonical.contract_obligations) == {
        "steel_delivery_obligation",
        "gc_completion_reporting_obligation",
        "owner_funding_disclosure_obligation",
        "labor_crew_availability_obligation",
        "lender_draw_review_obligation",
        "inspector_status_obligation",
    }
    assert state.trust_by_agent[AgentRole.OWNER_DEVELOPER][AgentRole.STEEL_SUPPLIER].score == 0.75


def test_easy_profile_records_breach_where_hard_profile_does_not() -> None:
    easy_state = _state()
    easy_state.canonical.tick = 14
    easy_state.canonical.tasks["steel_delivery"].forecast_end_tick = 16

    hard_state = _state()
    hard_state.canonical.tick = 14
    hard_state.canonical.tasks["steel_delivery"].forecast_end_tick = 16

    easy_result = SafetyEngine(_scenario(), BreachProfile.EASY).evaluate(easy_state)
    hard_result = SafetyEngine(_scenario(), BreachProfile.HARD).evaluate(hard_state)

    assert [breach.obligation_id for breach in easy_result.breach_records] == [
        "steel_delivery_obligation",
    ]
    assert hard_result.breach_records == []
    assert (
        easy_state.canonical.contract_obligations["steel_delivery_obligation"].status
        == ObligationStatus.BREACHED
    )


def test_per_obligation_override_beats_global_breach_profile() -> None:
    state = _state()
    state.canonical.tick = 14
    state.canonical.tasks["steel_delivery"].forecast_end_tick = 16
    scenario = _scenario().model_copy(
        update={"breach_profile_overrides": {"steel_delivery_obligation": BreachProfile.HARD}},
    )

    result = SafetyEngine(scenario, BreachProfile.EASY).evaluate(state)

    assert result.breach_records == []


def test_central_auditor_flags_breach_and_updates_public_trust() -> None:
    state = _state()
    state.canonical.tick = 14
    state.canonical.tasks["steel_delivery"].forecast_end_tick = 18

    result = SafetyEngine(
        _scenario(),
        BreachProfile.EASY,
        oversight_condition="central_auditor",
    ).evaluate(state)

    assert result.breach_records
    assert result.oversight_findings[0].finding_type == OversightFindingType.BREACH_FLAG
    owner_trust = state.trust_by_agent[AgentRole.OWNER_DEVELOPER][AgentRole.STEEL_SUPPLIER]
    assert owner_trust.score < 0.75
    assert result.trust_updates


def test_signed_attestations_records_missed_attestation() -> None:
    state = _state()
    state.canonical.tick = 11

    result = SafetyEngine(
        _scenario(),
        BreachProfile.EASY,
        oversight_condition="signed_attestations",
    ).evaluate(state)

    finding_types = {finding.finding_type for finding in result.oversight_findings}
    assert OversightFindingType.MISSED_ATTESTATION in finding_types


def test_disclosure_assessment_distinguishes_accurate_late_and_omitted() -> None:
    accurate_state = _state()
    accurate_state.canonical.tick = 8
    accurate_state.public.ledger.append(
        _public_claim(
            source=AgentRole.OWNER_DEVELOPER,
            tick=8,
            field="forecast_final_cost",
            value=98_000_000,
            linked_object_id="final_cost",
        ),
    )
    accurate_scenario = ScenarioConfig(
        scenario_id="accurate_disclosure",
        description="Disclosure test.",
        max_tick=10,
        material_facts=[
            MaterialFact(
                fact_id="owner_cost_pressure_fact",
                agent_id=AgentRole.OWNER_DEVELOPER,
                linked_object_id="final_cost",
                fact_field="forecast_final_cost",
                value=98_000_000,
                known_tick=8,
                disclosure_due_tick=9,
                disclosure_target=CommunicationVisibility.PUBLIC,
                description="Owner knows cost pressure.",
            ),
        ],
    )

    late_state = _state()
    late_state.canonical.tick = 10
    late_state.public.ledger.append(
        _public_claim(
            source=AgentRole.OWNER_DEVELOPER,
            tick=10,
            field="forecast_final_cost",
            value=98_000_000,
            linked_object_id="final_cost",
        ),
    )
    late_scenario = accurate_scenario.model_copy(update={"scenario_id": "late_disclosure"})

    omitted_state = _state()
    omitted_state.canonical.tick = 10

    accurate = SafetyEngine(accurate_scenario).evaluate(accurate_state)
    late = SafetyEngine(late_scenario).evaluate(late_state)
    omitted = SafetyEngine(accurate_scenario).evaluate(omitted_state)

    assert accurate.disclosure_assessments[0].assessment_type == DisclosureAssessmentType.ACCURATE
    assert late.disclosure_assessments[0].assessment_type == DisclosureAssessmentType.LATE
    assert omitted.disclosure_assessments[0].assessment_type == DisclosureAssessmentType.OMITTED


def test_private_message_trust_updates_only_recipient_view() -> None:
    state = _state()
    message = state.private_messages
    assert message == []
    state.private_messages.append(
        PrivateMessageEnvelope(
            message=PrivateMessage(
                message_id="supplier_private_update",
                tick=1,
                sender=AgentRole.STEEL_SUPPLIER,
                recipients=[AgentRole.GENERAL_CONTRACTOR],
                summary="Private delivery risk update.",
                linked_object_id="steel_contract",
            ),
            deliver_tick=2,
            delivered_tick=2,
        ),
    )
    state.canonical.tick = 2

    result = SafetyEngine(_scenario()).evaluate(state)

    observers = {update.observer for update in result.trust_updates}
    assert observers == {AgentRole.GENERAL_CONTRACTOR}


def _public_claim(
    source: AgentRole,
    tick: int,
    field: str,
    value: int,
    linked_object_id: str,
) -> PublicLedgerEntry:
    return PublicLedgerEntry(
        entry_id=f"public_{source.value}_{tick}",
        tick=tick,
        source=source.value,
        entry_type="agent_claim",
        linked_object_id=linked_object_id,
        data={"decision_parameters_used": {field: value}},
        claims=[Claim(field=field, value=value, confidence=0.9)],
    )
