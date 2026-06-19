"""Strict Pydantic schemas for Phase 1 ConstructBench state."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from constructbench.enums import (
    AgentRole,
    AssessmentUpdateMode,
    BehaviorProfile,
    BreachProfile,
    BreachSeverity,
    CommunicationVisibility,
    ContractStatus,
    DecisionType,
    DisclosureAssessmentType,
    InspectionStatus,
    LedgerEntryType,
    ObligationStatus,
    ObligationType,
    OversightFindingType,
    PaymentStatus,
    PolicyProfile,
    PrivateEventType,
    ProjectStatus,
    ResourceConditionLevel,
    ScheduledEventType,
    TaskStatus,
    UnchangedReason,
)

SnakeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Money = Annotated[int, Field(ge=0)]
Tick = Annotated[int, Field(ge=0)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Claim(StrictModel):
    field: SnakeId
    value: int | float | str | bool | None
    unit: str | None = None
    confidence: Probability


class AvailableDecision(StrictModel):
    decision_type: DecisionType
    object_types: list[SnakeId] = Field(default_factory=list)


class AgentBeliefState(StrictModel):
    expected_completion_tick: Tick
    expected_final_cost: Money
    probability_on_time: Probability
    probability_within_budget: Probability
    confidence: Probability
    basis_ids: list[SnakeId]


class Task(StrictModel):
    task_id: SnakeId
    responsible_agent: AgentRole
    status: TaskStatus
    planned_start_tick: Tick
    planned_end_tick: Tick
    forecast_end_tick: Tick
    actual_end_tick: Tick | None = None
    dependencies: list[SnakeId] = Field(default_factory=list)
    baseline_cost: Money
    forecast_cost: Money
    actual_cost: Money = 0
    inspection_required: bool = False

    @model_validator(mode="after")
    def validate_tick_order(self) -> Task:
        if self.planned_end_tick < self.planned_start_tick:
            raise ValueError("planned_end_tick must be >= planned_start_tick")
        return self


class Contract(StrictModel):
    contract_id: SnakeId
    parties: list[AgentRole]
    status: ContractStatus
    contract_value: Money
    start_tick: Tick
    end_tick: Tick | None = None
    linked_task_ids: list[SnakeId] = Field(default_factory=list)
    terms: dict[str, Any] = Field(default_factory=dict)


class ContractObligation(StrictModel):
    obligation_id: SnakeId
    responsible_agent: AgentRole
    obligation_type: ObligationType
    linked_object_id: SnakeId
    due_tick: Tick
    description: str
    expected_field: SnakeId
    expected_value: int | float | str | bool
    easy_threshold: int | float = 0
    hard_threshold: int | float = 0
    breach_profile_override: BreachProfile | None = None
    status: ObligationStatus = ObligationStatus.PENDING
    data: dict[str, Any] = Field(default_factory=dict)


class BreachRecord(StrictModel):
    breach_id: SnakeId
    obligation_id: SnakeId
    responsible_agent: AgentRole
    linked_object_id: SnakeId
    tick: Tick
    severity: BreachSeverity
    breach_profile: BreachProfile
    threshold: int | float
    observed_value: int | float | str | bool | None
    expected_value: int | float | str | bool
    description: str


class Payment(StrictModel):
    payment_id: SnakeId
    payer: AgentRole
    recipient: AgentRole
    amount: Money
    due_tick: Tick
    status: PaymentStatus
    paid_tick: Tick | None = None
    linked_contract_id: SnakeId | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Inspection(StrictModel):
    inspection_id: SnakeId
    task_id: SnakeId
    requested_by: AgentRole
    inspector_agent: AgentRole = AgentRole.INSPECTOR
    status: InspectionStatus
    scheduled_tick: Tick | None = None
    completed_tick: Tick | None = None
    outcome: str | None = None
    evidence_ids: list[SnakeId] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class AgentFinance(StrictModel):
    agent_id: AgentRole
    cash_available: Money
    data: dict[str, Any] = Field(default_factory=dict)


class PublicLedgerEntry(StrictModel):
    entry_id: SnakeId
    tick: Tick
    source: SnakeId
    entry_type: LedgerEntryType
    linked_object_id: SnakeId | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)


class PrivateEvent(StrictModel):
    event_id: SnakeId
    tick: Tick
    event_type: PrivateEventType
    source: SnakeId = "system"
    recipient: AgentRole
    linked_object_id: SnakeId | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class PublicState(StrictModel):
    ledger: list[PublicLedgerEntry] = Field(default_factory=list)


class AttestationRequirement(StrictModel):
    requirement_id: SnakeId
    agent_id: AgentRole
    due_tick: Tick
    linked_object_id: SnakeId
    required_field: SnakeId
    expected_value: int | float | str | bool | None = None
    tolerance: int | float = 0
    description: str


class MaterialFact(StrictModel):
    fact_id: SnakeId
    agent_id: AgentRole
    linked_object_id: SnakeId
    fact_field: SnakeId
    value: int | float | str | bool
    known_tick: Tick
    disclosure_due_tick: Tick
    disclosure_target: CommunicationVisibility = CommunicationVisibility.PUBLIC
    description: str


class OversightFinding(StrictModel):
    finding_id: SnakeId
    tick: Tick
    finding_type: OversightFindingType
    source: SnakeId = "oversight"
    target_agent: AgentRole
    linked_object_id: SnakeId | None = None
    severity: BreachSeverity = BreachSeverity.MINOR
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class DisclosureAssessment(StrictModel):
    assessment_id: SnakeId
    tick: Tick
    fact_id: SnakeId
    agent_id: AgentRole
    linked_object_id: SnakeId
    assessment_type: DisclosureAssessmentType
    expected_field: SnakeId
    expected_value: int | float | str | bool
    observed_value: int | float | str | bool | None = None
    public_entry_id: SnakeId | None = None
    summary: str


class PairwiseTrustState(StrictModel):
    observer: AgentRole
    target: AgentRole
    score: Probability = 0.75
    basis_ids: list[SnakeId] = Field(default_factory=list)


class CounterpartyAssessment(StrictModel):
    target: AgentRole
    trust_score: Probability
    confidence: Probability
    basis_ids: list[SnakeId] = Field(default_factory=list)
    reason: str


class AgentTrustAssessmentRecord(StrictModel):
    assessment_id: SnakeId
    tick: Tick
    observer: AgentRole
    target: AgentRole
    trust_score: Probability
    confidence: Probability
    basis_ids: list[SnakeId] = Field(default_factory=list)
    reason: str


class ExpectationDimensions(StrictModel):
    delivery_reliability: Probability = 0.75
    reporting_integrity: Probability = 0.75


class EvidenceSummary(StrictModel):
    evidence_id: SnakeId
    evidence_type: SnakeId
    source: str
    linked_object_id: SnakeId | None = None
    summary: str


class EvidenceAssessment(StrictModel):
    evidence_id: SnakeId
    relevant_dimensions: list[SnakeId] = Field(default_factory=list)
    causal_attribution: str
    diagnosticity: str
    summary: str | None = None


class CommercialResponse(StrictModel):
    require_performance_bond: bool = False
    seek_alternate_supplier: bool = False
    required_reporting_interval_ticks: Tick | None = None
    allow_advance_payment: bool = True
    require_independent_verification: bool = False


class CounterpartyExpectationState(StrictModel):
    observer: AgentRole
    target: AgentRole
    assessment: ExpectationDimensions = Field(default_factory=ExpectationDimensions)
    basis_ids: list[SnakeId] = Field(default_factory=list)


class CounterpartyExpectationAssessment(StrictModel):
    target: AgentRole
    mode: AssessmentUpdateMode = AssessmentUpdateMode.STRUCTURED_DIMENSIONAL
    previous_assessment: ExpectationDimensions | None = None
    updated_assessment: ExpectationDimensions
    evidence_assessment: list[EvidenceAssessment] = Field(default_factory=list)
    basis_ids: list[SnakeId] = Field(default_factory=list)
    changed_from_prior: bool
    unchanged_reason: UnchangedReason | None = None
    commercial_response: CommercialResponse = Field(default_factory=CommercialResponse)
    rationale: str

    @model_validator(mode="after")
    def validate_unchanged_reason(self) -> CounterpartyExpectationAssessment:
        if not self.changed_from_prior and self.unchanged_reason is None:
            raise ValueError("unchanged counterparty expectation update requires unchanged_reason")
        return self


class CounterpartyExpectationUpdateRecord(StrictModel):
    update_id: SnakeId
    tick: Tick
    observer: AgentRole
    target: AgentRole
    mode: AssessmentUpdateMode
    previous_assessment: ExpectationDimensions
    updated_assessment: ExpectationDimensions
    delivery_reliability_delta: float
    reporting_integrity_delta: float
    evidence_assessment: list[EvidenceAssessment] = Field(default_factory=list)
    basis_ids: list[SnakeId] = Field(default_factory=list)
    changed_from_prior: bool
    unchanged_reason: UnchangedReason | None = None
    commercial_response: CommercialResponse = Field(default_factory=CommercialResponse)
    rationale: str


class TrustUpdate(StrictModel):
    update_id: SnakeId
    tick: Tick
    observer: AgentRole
    target: AgentRole
    delta: float
    score_after: Probability
    reason: str
    basis_id: SnakeId


class AgentPrivateState(StrictModel):
    agent_id: AgentRole
    role: AgentRole
    resource_condition_level: ResourceConditionLevel = ResourceConditionLevel.NORMAL
    resource_summary: str | None = None
    behavior_profile: BehaviorProfile = BehaviorProfile.COLLABORATIVE
    behavior_summary: str | None = None
    behavior_guidance: list[str] = Field(default_factory=list)
    dishonesty_framing: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_agent_matches_role(self) -> AgentPrivateState:
        if self.agent_id != self.role:
            raise ValueError("agent_id and role must match in Phase 1 private state")
        return self


class CanonicalProjectState(StrictModel):
    tick: Tick = 0
    project_status: ProjectStatus
    baseline_cost: Money
    approved_budget: Money
    forecast_final_cost: Money
    actual_cost_to_date: Money
    target_completion_tick: Tick
    forecast_completion_tick: Tick
    actual_completion_tick: Tick | None = None
    tasks: dict[SnakeId, Task]
    contracts: dict[SnakeId, Contract]
    contract_obligations: dict[SnakeId, ContractObligation] = Field(default_factory=dict)
    breach_records: list[BreachRecord] = Field(default_factory=list)
    payments: dict[SnakeId, Payment] = Field(default_factory=dict)
    inspections: dict[SnakeId, Inspection] = Field(default_factory=dict)
    agent_finances: dict[AgentRole, AgentFinance] = Field(default_factory=dict)
    scheduled_events: list[dict[str, Any]] = Field(default_factory=list)


class ProjectConfig(StrictModel):
    project_id: SnakeId
    canonical: CanonicalProjectState
    initial_belief: AgentBeliefState
    private_states: dict[AgentRole, AgentPrivateState]
    public_state: PublicState = Field(default_factory=PublicState)

    @model_validator(mode="after")
    def validate_config_consistency(self) -> ProjectConfig:
        missing_finances = set(self.private_states) - set(self.canonical.agent_finances)
        if missing_finances:
            missing = ", ".join(sorted(role.value for role in missing_finances))
            raise ValueError(f"agent finances missing for: {missing}")

        task_ids = set(self.canonical.tasks)
        for task in self.canonical.tasks.values():
            missing_dependencies = set(task.dependencies) - task_ids
            if missing_dependencies:
                missing = ", ".join(sorted(missing_dependencies))
                raise ValueError(f"task {task.task_id} has unknown dependencies: {missing}")
        return self


class ResourceConditionPreset(StrictModel):
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class BehaviorProfilePreset(StrictModel):
    summary: str
    decision_guidance: list[str] = Field(default_factory=list)
    dishonesty_framing: str | None = None


class RoleConfig(StrictModel):
    role_id: AgentRole
    display_name: str
    policy_profile: PolicyProfile
    default_condition_level: ResourceConditionLevel = ResourceConditionLevel.NORMAL
    default_behavior_profile: BehaviorProfile = BehaviorProfile.COLLABORATIVE
    ordered_goals: list[str]
    visible_project_objects: list[SnakeId]
    private_state_fields: list[SnakeId]
    resource_condition_presets: dict[ResourceConditionLevel, ResourceConditionPreset] = Field(
        default_factory=dict,
    )
    behavior_profile_presets: dict[BehaviorProfile, BehaviorProfilePreset] = Field(
        default_factory=dict,
    )
    contractual_authority: list[str]
    permitted_decisions: list[AvailableDecision]
    permitted_request_types: list[SnakeId] = Field(default_factory=list)
    required_reporting_obligations: list[str] = Field(default_factory=list)
    activation_conditions: list[str] = Field(default_factory=list)


class DecisionSubmission(StrictModel):
    type: DecisionType
    object_type: SnakeId | None = None
    object_id: SnakeId | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Communication(StrictModel):
    visibility: CommunicationVisibility
    recipients: list[AgentRole] = Field(default_factory=list)
    summary: str
    linked_object_id: SnakeId | None = None
    claims: list[Claim] = Field(default_factory=list)


class AgentSubmission(StrictModel):
    decision: DecisionSubmission
    communication: Communication | None = None
    belief_update: AgentBeliefState
    counterparty_assessments: list[CounterpartyAssessment] = Field(default_factory=list)
    counterparty_expectation_updates: list[CounterpartyExpectationAssessment] = Field(
        default_factory=list,
    )
    rationale: str | None = None
    observed_new_info: list[SnakeId] = Field(default_factory=list)
    decision_parameters_used: dict[str, Any] = Field(default_factory=dict)


class PrivateMessage(StrictModel):
    message_id: SnakeId
    tick: Tick
    sender: AgentRole
    recipients: list[AgentRole]
    summary: str
    linked_object_id: SnakeId | None = None
    claims: list[Claim] = Field(default_factory=list)


class PrivateMessageEnvelope(StrictModel):
    message: PrivateMessage
    deliver_tick: Tick
    delivered_tick: Tick | None = None


class EconomicDecisionOption(StrictModel):
    option_id: SnakeId
    decision_type: DecisionType
    object_type: SnakeId
    object_id: SnakeId | None = None
    description: str
    parameter_guidance: dict[str, Any] = Field(default_factory=dict)
    known_effects: dict[str, Any] = Field(default_factory=dict)
    costs: dict[str, Any] = Field(default_factory=dict)
    risks: dict[str, Any] = Field(default_factory=dict)
    strategy_notes: list[str] = Field(default_factory=list)


class AgentObservation(StrictModel):
    tick: Tick
    agent_id: AgentRole
    role: AgentRole
    policy_profile: PolicyProfile
    resource_condition_level: ResourceConditionLevel
    resource_summary: str | None = None
    behavior_profile: BehaviorProfile
    behavior_summary: str | None = None
    behavior_guidance: list[str] = Field(default_factory=list)
    dishonesty_framing: str | None = None
    role_goals: list[str] = Field(default_factory=list)
    contractual_authority: list[str] = Field(default_factory=list)
    public_project_state: dict[str, Any]
    private_state: dict[str, Any]
    relevant_tasks: list[Task]
    relevant_contracts: list[Contract]
    new_public_entries: list[PublicLedgerEntry]
    new_private_events: list[PrivateEvent] = Field(default_factory=list)
    new_private_messages: list[PrivateMessage]
    pending_requests: list[dict[str, Any]]
    current_beliefs: AgentBeliefState
    trust_in_counterparties: dict[AgentRole, PairwiseTrustState] = Field(default_factory=dict)
    mechanical_reputation_in_counterparties: dict[AgentRole, PairwiseTrustState] = Field(
        default_factory=dict,
    )
    assessment_update_mode: AssessmentUpdateMode = AssessmentUpdateMode.SCALAR_BASELINE
    counterparty_expectations: dict[AgentRole, CounterpartyExpectationState] = Field(
        default_factory=dict,
    )
    received_evidence: list[EvidenceSummary] = Field(default_factory=list)
    commercial_response_options: dict[AgentRole, CommercialResponse] = Field(
        default_factory=dict,
    )
    available_decisions: list[AvailableDecision]
    economic_decision_options: list[EconomicDecisionOption] = Field(default_factory=list)


class StateStore(StrictModel):
    canonical: CanonicalProjectState
    public: PublicState
    private_by_agent: dict[AgentRole, AgentPrivateState]
    beliefs_by_agent: dict[AgentRole, AgentBeliefState]
    role_configs: dict[AgentRole, RoleConfig]
    trust_by_agent: dict[AgentRole, dict[AgentRole, PairwiseTrustState]] = Field(
        default_factory=dict,
    )
    agent_trust_by_agent: dict[AgentRole, dict[AgentRole, PairwiseTrustState]] = Field(
        default_factory=dict,
    )
    agent_trust_assessments: list[AgentTrustAssessmentRecord] = Field(default_factory=list)
    expectations_by_agent: dict[AgentRole, dict[AgentRole, CounterpartyExpectationState]] = Field(
        default_factory=dict,
    )
    expectation_update_records: list[CounterpartyExpectationUpdateRecord] = Field(
        default_factory=list,
    )
    oversight_findings: list[OversightFinding] = Field(default_factory=list)
    disclosure_assessments: list[DisclosureAssessment] = Field(default_factory=list)
    trust_updates: list[TrustUpdate] = Field(default_factory=list)
    private_events_by_agent: dict[AgentRole, list[PrivateEvent]] = Field(default_factory=dict)
    private_messages: list[PrivateMessageEnvelope] = Field(default_factory=list)

    def to_snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PublicLedgerEventConfig(StrictModel):
    tick: Tick
    entry_id: SnakeId
    source: SnakeId = "system"
    entry_type: LedgerEntryType
    linked_object_id: SnakeId | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)


class PrivateStateEventConfig(StrictModel):
    tick: Tick
    event_id: SnakeId
    recipient: AgentRole
    event_type: PrivateEventType
    linked_object_id: SnakeId | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class PrivateMessageEventConfig(StrictModel):
    tick: Tick
    message_id: SnakeId
    sender: AgentRole
    recipients: list[AgentRole]
    summary: str
    linked_object_id: SnakeId | None = None
    claims: list[Claim] = Field(default_factory=list)
    delay_ticks: Tick | None = None


class ScheduledEventConfig(StrictModel):
    event_type: ScheduledEventType
    public_ledger_entry: PublicLedgerEventConfig | None = None
    private_state_update: PrivateStateEventConfig | None = None
    private_message: PrivateMessageEventConfig | None = None

    @model_validator(mode="after")
    def validate_payload_matches_event_type(self) -> ScheduledEventConfig:
        payloads = {
            ScheduledEventType.PUBLIC_LEDGER_ENTRY: self.public_ledger_entry,
            ScheduledEventType.PRIVATE_STATE_UPDATE: self.private_state_update,
            ScheduledEventType.PRIVATE_MESSAGE: self.private_message,
        }
        if payloads[self.event_type] is None:
            raise ValueError(f"Missing payload for scheduled event type: {self.event_type}")
        extra_payloads = [
            event_type.value
            for event_type, payload in payloads.items()
            if event_type != self.event_type and payload is not None
        ]
        if extra_payloads:
            extra = ", ".join(extra_payloads)
            raise ValueError(f"Unexpected payloads for scheduled event: {extra}")
        return self

    @property
    def tick(self) -> Tick:
        if self.public_ledger_entry is not None:
            return self.public_ledger_entry.tick
        if self.private_state_update is not None:
            return self.private_state_update.tick
        if self.private_message is not None:
            return self.private_message.tick
        raise ValueError("Scheduled event has no payload")


class DeadlineConfig(StrictModel):
    object_id: SnakeId
    due_tick: Tick
    description: str


class ScenarioConfig(StrictModel):
    scenario_id: SnakeId
    description: str
    max_tick: Tick
    default_message_delay_ticks: Tick = 1
    scheduled_events: list[ScheduledEventConfig] = Field(default_factory=list)
    task_deadlines: list[DeadlineConfig] = Field(default_factory=list)
    payment_deadlines: list[DeadlineConfig] = Field(default_factory=list)
    contract_consequence_deadlines: list[DeadlineConfig] = Field(default_factory=list)
    contract_obligations: list[ContractObligation] = Field(default_factory=list)
    attestation_requirements: list[AttestationRequirement] = Field(default_factory=list)
    material_facts: list[MaterialFact] = Field(default_factory=list)
    breach_profile_overrides: dict[SnakeId, BreachProfile] = Field(default_factory=dict)


class DeliveredEvents(StrictModel):
    public_entries: list[PublicLedgerEntry] = Field(default_factory=list)
    private_events_by_agent: dict[AgentRole, list[PrivateEvent]] = Field(default_factory=dict)
    private_messages_by_agent: dict[AgentRole, list[PrivateMessage]] = Field(default_factory=dict)


class TickResult(StrictModel):
    tick: Tick
    delivered: DeliveredEvents
    active_agents: list[AgentRole] = Field(default_factory=list)


class ValidationResult(StrictModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class AgentRuntimeRecord(StrictModel):
    agent_id: AgentRole
    observation: AgentObservation
    submission: AgentSubmission
    validation: ValidationResult
    used_fallback: bool = False
    raw_output: str | None = None
    parse_errors: list[str] = Field(default_factory=list)


class AgentTurnResult(StrictModel):
    tick: Tick
    records: list[AgentRuntimeRecord] = Field(default_factory=list)


class AppliedTransition(StrictModel):
    agent_id: AgentRole
    transition_type: SnakeId
    target_store: SnakeId
    object_id: SnakeId | None = None
    description: str


class TransitionResult(StrictModel):
    tick: Tick
    applied: list[AppliedTransition] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)


class SafetyTickResult(StrictModel):
    tick: Tick
    breach_records: list[BreachRecord] = Field(default_factory=list)
    oversight_findings: list[OversightFinding] = Field(default_factory=list)
    disclosure_assessments: list[DisclosureAssessment] = Field(default_factory=list)
    trust_updates: list[TrustUpdate] = Field(default_factory=list)


class ModelSettings(StrictModel):
    model_id: str
    runtime: str = "local"
    temperature: float = 0.0
    sampling_seed: int | None = None
    max_input_tokens: int = Field(default=4096, ge=1)
    max_output_tokens: int = Field(default=1024, ge=1)
    retry_count: int = Field(default=1, ge=0)
