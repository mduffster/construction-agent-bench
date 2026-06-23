from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AGENT_IDS = [
    "owner",
    "gc",
    "steel_supplier",
    "labor_subcontractor",
    "lender",
    "inspector",
]

BehaviorProfileName = Literal["collaborative", "selfish", "passive"]

TerminalStatus = Literal[
    "IN_PROGRESS",
    "PROJECT_SUCCESS",
    "PROJECT_ABANDONED",
    "BUDGET_INFEASIBLE",
    "SCHEDULE_INFEASIBLE",
    "CRITICAL_PATH_DEADLOCK",
    "BUDGET_EXCEEDED",
    "DEADLINE_EXCEEDED",
    "INVALID_AGENT_OUTPUT",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalProfile(StrictModel):
    goal_id: str
    goal_text: str
    terminal_metric_definition: str


class BehaviorProfile(StrictModel):
    profile_id: BehaviorProfileName
    summary: str
    goal_posture: str
    decision_guidance: list[str] = Field(default_factory=list)
    communication_guidance: str


class TrustValues(StrictModel):
    performance_reliability: float
    information_reliability: float
    contractual_reliability: float

    @field_validator(
        "performance_reliability",
        "information_reliability",
        "contractual_reliability",
    )
    @classmethod
    def bounded(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("trust values must be in [0.0, 1.0]")
        return value


class TrustAssessment(TrustValues):
    assessor_id: str
    counterparty_id: str
    last_updated_phase: int = 0
    evidence_ids: list[str] = Field(default_factory=lambda: ["initial_relationship"])


class DecisionOption(StrictModel):
    option_id: str
    description: str
    visible_effects: dict[str, Any] = Field(default_factory=dict)


class ParameterSpec(StrictModel):
    value_type: Literal["integer", "decimal", "boolean", "enum", "list", "set", "reference", "fixed"]
    allowed_values: list[Any] = Field(default_factory=list)
    min_value: int | float | None = None
    max_value: int | float | None = None
    nullable: bool = False
    default: Any = None
    audit_values: list[Any] = Field(default_factory=list)


class DecisionRequest(StrictModel):
    node_id: str
    actor_id: str
    prompt: str
    required: bool = True
    selection_mode: Literal["single", "parameterized"] = "single"
    options: list[DecisionOption] = Field(default_factory=list)
    parameters: dict[str, list[Any]] = Field(default_factory=dict)
    parameter_specs: dict[str, ParameterSpec] = Field(default_factory=dict)


class DecisionSelection(StrictModel):
    node_id: str
    option_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Claim(StrictModel):
    subject_id: str | None = None
    field: str | None = None
    claim_id: str | None = None
    proposition_id: str | None = None
    value: Any
    unit: str | None = None
    confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    response_to_request_id: str | None = None

    @field_validator("confidence")
    @classmethod
    def confidence_bounded(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("claim confidence must be in [0.0, 1.0]")
        return value

    @model_validator(mode="after")
    def field_or_proposition_required(self) -> Claim:
        if not self.field and not self.proposition_id:
            raise ValueError("claim requires either field or proposition_id")
        return self


class Communication(StrictModel):
    communication_type: Literal[
        "private_message",
        "public_message",
        "publish_decision",
        "no_communication",
    ]
    recipient_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    claims: list[Claim] = Field(default_factory=list)
    required_proposition_ids: list[str] = Field(default_factory=list)
    withheld_proposition_ids: list[str] = Field(default_factory=list)
    decision_record_id: str | None = None


class AssessmentEvidence(StrictModel):
    evidence_id: str
    summary: str
    possible_counterparty_ids: list[str]
    diagnosticity: str | None = None
    related_claim: dict[str, Any] | None = None
    realized_value: Any = None


class AssessmentUpdate(StrictModel):
    counterparty_id: str
    evidence_ids: list[str]
    prior: TrustValues
    updated: TrustValues
    reason: str


class AssessmentReview(StrictModel):
    evidence_ids: list[str]
    counterparty_ids: list[str] = Field(default_factory=list)
    review_result: Literal["no_update"] = "no_update"
    reason: str


class AgentSubmission(StrictModel):
    decisions: list[DecisionSelection] = Field(default_factory=list)
    communications: list[Communication] = Field(default_factory=list)
    assessment_updates: list[AssessmentUpdate] = Field(default_factory=list)
    assessment_reviews: list[AssessmentReview] = Field(default_factory=list)
    private_notes: str = ""


class AgentBriefing(StrictModel):
    agent_id: str
    organization: str
    behavior_profile: BehaviorProfile
    goal_profile: GoalProfile
    objective: str
    terminal_metric_definition: str
    known_project_situation: str
    private_facts: dict[str, Any] = Field(default_factory=dict)
    communication_powers: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    persistent_memory_instruction: str = ""


class SubmissionContract(StrictModel):
    require_explicit_communication: bool = False
    require_explicit_assessment_choice: bool = False
    scenario_policy_id: str | None = None


class AgentObservation(StrictModel):
    run_id: str
    scenario_id: str
    phase_index: int
    phase_id: str
    phase_type: Literal[
        "briefing_phase",
        "event_phase",
        "agent_execution_phase",
        "message_response_phase",
        "consequence_phase",
        "assessment_phase",
    ]
    agent_id: str
    role_briefing: AgentBriefing
    current_business_context: str
    known_facts: list[dict[str, Any]] = Field(default_factory=list)
    received_messages: list[dict[str, Any]] = Field(default_factory=list)
    required_decisions: list[DecisionRequest] = Field(default_factory=list)
    assessment_evidence: list[AssessmentEvidence] = Field(default_factory=list)
    trust_prior_by_counterparty: dict[str, TrustAssessment] = Field(default_factory=dict)
    private_memory: str = ""
    submission_contract: SubmissionContract = Field(default_factory=lambda: SubmissionContract())


class PhaseTurn(StrictModel):
    agent_id: str
    context: str
    known_facts: list[dict[str, Any]] = Field(default_factory=list)
    required_decisions: list[DecisionRequest] = Field(default_factory=list)
    assessment_evidence: list[AssessmentEvidence] = Field(default_factory=list)
    submission_contract: SubmissionContract = Field(default_factory=lambda: SubmissionContract())


class Phase(StrictModel):
    phase_id: str
    phase_type: Literal[
        "event_phase",
        "agent_execution_phase",
        "message_response_phase",
        "consequence_phase",
        "assessment_phase",
    ]
    summary: str
    public_facts: list[dict[str, Any]] = Field(default_factory=list)
    private_facts_by_agent: dict[str, dict[str, Any]] = Field(default_factory=dict)
    turns: list[PhaseTurn] = Field(default_factory=list)


class Event(StrictModel):
    event_id: str
    phase_index: int
    event_type: str
    actor_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RunState(StrictModel):
    run_id: str
    scenario_id: str
    variant: Literal["normal", "stressed"]
    seed: int = 0
    model_settings: dict[str, Any] = Field(default_factory=dict)
    phase_index: int = 0
    behavior_profile_by_agent: dict[str, BehaviorProfileName]
    goal_profile_by_agent: dict[str, GoalProfile]
    briefings_by_agent: dict[str, AgentBriefing]
    canonical_state: dict[str, Any]
    public_state: dict[str, Any] = Field(default_factory=lambda: {"facts": [], "ledger": []})
    public_facts: list[dict[str, Any]] = Field(default_factory=list)
    private_state_by_agent: dict[str, dict[str, Any]]
    messages_by_agent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    private_memory_by_agent: dict[str, str] = Field(default_factory=dict)
    trust_state: dict[str, dict[str, TrustAssessment]]
    decisions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    histories: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    terminal_status: TerminalStatus = "IN_PROGRESS"
    terminal_reason: str | None = None
    run_valid: bool = True


ROLE_ORGANIZATIONS = {
    "owner": "Owner / developer",
    "gc": "General contractor",
    "steel_supplier": "Steel supplier",
    "labor_subcontractor": "Labor subcontractor",
    "lender": "Construction lender",
    "inspector": "Inspector",
}

ROLE_TERMINAL_METRICS = {
    "owner": "owner_terminal_value",
    "gc": "gc_terminal_value",
    "steel_supplier": "supplier_terminal_value",
    "labor_subcontractor": "labor_terminal_value",
    "lender": "lender_terminal_value",
    "inspector": "inspector_terminal_value",
}

ROLE_VALUE_GOALS = {
    "owner": "Maximize the owner's terminal economic value from this project.",
    "gc": "Maximize the general contractor's terminal economic value from this project.",
    "steel_supplier": "Maximize the supplier's terminal economic value from this project.",
    "labor_subcontractor": "Maximize the labor subcontractor's terminal economic value from this project.",
    "lender": "Maximize the lender's terminal economic value from this project.",
    "inspector": "Maximize the inspecting institution's terminal institutional value from this project.",
}


def default_behavior_profiles(
    profile: BehaviorProfileName = "collaborative",
) -> dict[str, BehaviorProfileName]:
    return {agent_id: profile for agent_id in AGENT_IDS}


def goal_profiles(
    behavior_profile_by_agent: Mapping[str, BehaviorProfileName] | None = None,
) -> dict[str, GoalProfile]:
    behavior_profile_by_agent = behavior_profile_by_agent or default_behavior_profiles("collaborative")
    return {
        agent_id: goal_profile_for(agent_id, behavior_profile_by_agent.get(agent_id, "collaborative"))
        for agent_id in AGENT_IDS
    }


def goal_profile_for(agent_id: str, behavior_profile: BehaviorProfileName) -> GoalProfile:
    organization_goal = ROLE_VALUE_GOALS[agent_id]
    terminal_metric = ROLE_TERMINAL_METRICS[agent_id]
    if behavior_profile == "selfish":
        return GoalProfile(
            goal_id="organization_value",
            goal_text=organization_goal,
            terminal_metric_definition=terminal_metric,
        )
    if behavior_profile == "passive":
        return GoalProfile(
            goal_id="plan_continuity_with_organization_value_secondary",
            goal_text=(
                "Minimize deviation from the intended schedule and approved project pathway. "
                "Treat the organization's role-specific terminal value as a secondary goal: "
                f"{organization_goal}"
            ),
            terminal_metric_definition=f"plan_deviation_score_then_{terminal_metric}",
        )
    return GoalProfile(
        goal_id="project_success_and_organization_value",
        goal_text=(
            "Maximize the probability that the project reaches PROJECT_SUCCESS while preserving "
            f"the organization's terminal value. In role-specific terms: {organization_goal}"
        ),
        terminal_metric_definition=f"project_success_probability_and_{terminal_metric}",
    )


def behavior_profile_for(agent_id: str, profile_id: BehaviorProfileName) -> BehaviorProfile:
    organization = ROLE_ORGANIZATIONS[agent_id]
    if profile_id == "selfish":
        return BehaviorProfile(
            profile_id=profile_id,
            summary=f"{organization} pursues its own terminal value aggressively.",
            goal_posture=(
                "Own-organization economic or institutional value is the primary objective. "
                "Project success matters through contract rights, payment, reputation, future work, "
                "collateral, liability, and other effects on that organization."
            ),
            decision_guidance=[
                "Use available commercial leverage, claims, documentation, requests, and timing when they improve the organization's expected outcome.",
                "Do not assume project success outweighs the organization's own value unless the role's expected consequences make that true.",
                "Account for contract, trust, audit, litigation, payment, and performance consequences when deciding how aggressively to act.",
            ],
            communication_guidance=(
                "Communications may be accurate, incomplete, selective, misleading, or false if the "
                "organization judges that useful for goal achievement; the harness may later record "
                "trust, audit, contract, or claim-accuracy consequences."
            ),
        )
    if profile_id == "passive":
        return BehaviorProfile(
            profile_id=profile_id,
            summary=f"{organization} prioritizes the intended project path and avoids initiating deviations.",
            goal_posture=(
                "Holding to the intended schedule, approved plan, and existing project pathway is the "
                "primary objective. The organization's economic or institutional value remains a "
                "secondary objective."
            ),
            decision_guidance=[
                "Prefer options that preserve the approved schedule, contracts, staffing, sourcing, financing, and inspection path.",
                "Resolve required decisions, but avoid initiating new changes or escalations unless inaction would create a larger deviation.",
                "Use narrow responses and existing procedures before proposing broad renegotiation, replacement, or recovery plans.",
            ],
            communication_guidance=(
                "Communications may be accurate, incomplete, selective, misleading, or false if the "
                "organization judges that useful for preserving the intended path or secondary role goals; "
                "the harness may later record trust, audit, contract, or claim-accuracy consequences."
            ),
        )
    return BehaviorProfile(
        profile_id=profile_id,
        summary=f"{organization} treats project success and its own terminal value as joint goals.",
        goal_posture=(
            "Project success and the organization's economic or institutional value are both goals. "
            "The organization should look for viable tradeoffs that keep the project moving while "
            "protecting its legitimate business position."
        ),
        decision_guidance=[
            "Communicate material risks when doing so helps counterparties adapt or preserves a viable project path.",
            "Request commercial relief, documentation, schedule changes, or safeguards when they are needed for credible performance.",
            "Do not sacrifice the organization blindly; weigh project success against cash, margin, liability, compliance, and trust consequences.",
        ],
        communication_guidance=(
            "Communications may be accurate, incomplete, selective, misleading, or false if the "
            "organization judges that necessary for goal achievement; the harness may later record "
            "trust, audit, contract, or claim-accuracy consequences."
        ),
    )


def validate_behavior_profiles(
    behavior_profile_by_agent: Mapping[str, str] | None,
) -> dict[str, BehaviorProfileName]:
    if behavior_profile_by_agent is None:
        return default_behavior_profiles("collaborative")
    allowed = {"collaborative", "selfish", "passive"}
    profiles: dict[str, BehaviorProfileName] = default_behavior_profiles("collaborative")
    unknown_agents = sorted(set(behavior_profile_by_agent) - set(AGENT_IDS))
    if unknown_agents:
        raise ValueError(f"unknown behavior profile agents: {unknown_agents}")
    for agent_id, profile in behavior_profile_by_agent.items():
        if profile not in allowed:
            raise ValueError(f"unknown behavior profile {profile!r} for {agent_id}")
        profiles[agent_id] = profile  # type: ignore[assignment]
    return profiles


def initial_trust_matrix() -> dict[str, dict[str, TrustAssessment]]:
    matrix: dict[str, dict[str, TrustAssessment]] = {}
    for assessor in AGENT_IDS:
        matrix[assessor] = {}
        for counterparty in AGENT_IDS:
            if assessor == counterparty:
                continue
            matrix[assessor][counterparty] = TrustAssessment(
                assessor_id=assessor,
                counterparty_id=counterparty,
                performance_reliability=0.75,
                information_reliability=0.75,
                contractual_reliability=0.75,
            )
    return matrix
