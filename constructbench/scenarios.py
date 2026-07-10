from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from constructbench.baseline import (
    normal_project_bound_metrics,
    normal_project_deliverables,
    normal_project_plan,
    normal_project_public_context,
    project_deliverables_from_impacts,
    required_deliverables_complete,
    scenario_baseline_impact,
)
from constructbench.claims import S01_COMMERCIAL_CLAIM_FIELDS, evaluate_commercial_request_claims
from constructbench.manifest import canonical_json_sha256
from constructbench.payoffs import PayoffEvent, PayoffLedger, UtilitySpec, build_s01_payoff_ledger
from constructbench.s01_v2_lineage import build_s01_v2_lineage
from constructbench.scenario_instances import (
    apply_scenario_instance_to_start,
    get_scenario_instance,
    scenario_instance_public_fact,
    scenario_instance_record,
    scenario_instance_role_context,
)
from constructbench.state import (
    AGENT_IDS,
    AgentBriefing,
    AssessmentEvidence,
    BehaviorProfileName,
    DecisionOption,
    DecisionRequest,
    DecisionSelection,
    GoalProfile,
    ParameterSpec,
    Phase,
    PhaseTurn,
    RunState,
    SubmissionContract,
    behavior_profile_for,
    goal_profiles,
    initial_trust_matrix,
    validate_behavior_profiles,
)

Variant = Literal["normal", "stressed"]


def option(option_id: str, description: str, **visible_effects: Any) -> DecisionOption:
    return DecisionOption(
        option_id=option_id,
        description=description,
        visible_effects=visible_effects,
    )


def single(
    node_id: str,
    actor_id: str,
    prompt: str,
    options: list[DecisionOption],
) -> DecisionRequest:
    return DecisionRequest(
        node_id=node_id,
        actor_id=actor_id,
        prompt=prompt,
        selection_mode="single",
        options=options,
    )


def params(
    node_id: str,
    actor_id: str,
    prompt: str,
    parameters: dict[str, list[Any]],
) -> DecisionRequest:
    return DecisionRequest(
        node_id=node_id,
        actor_id=actor_id,
        prompt=prompt,
        selection_mode="parameterized",
        options=[option("__parameters__", "Submit the required parameter values.")],
        parameters=parameters,
    )


def params_spec(
    node_id: str,
    actor_id: str,
    prompt: str,
    parameter_specs: dict[str, ParameterSpec],
) -> DecisionRequest:
    return DecisionRequest(
        node_id=node_id,
        actor_id=actor_id,
        prompt=prompt,
        selection_mode="parameterized",
        options=[option("__parameters__", "Submit the required parameter values.")],
        parameter_specs=parameter_specs,
    )


def p_int(
    *,
    min_value: int,
    max_value: int,
    default: int | None = None,
    audit_values: list[int] | None = None,
    nullable: bool = False,
) -> ParameterSpec:
    return ParameterSpec(
        value_type="integer",
        min_value=min_value,
        max_value=max_value,
        nullable=nullable,
        default=default if default is not None or nullable else min_value,
        audit_values=audit_values or [min_value, max_value],
    )


def p_decimal(
    *,
    min_value: float,
    max_value: float,
    default: float | None = None,
    audit_values: list[float] | None = None,
    nullable: bool = False,
) -> ParameterSpec:
    return ParameterSpec(
        value_type="decimal",
        min_value=min_value,
        max_value=max_value,
        nullable=nullable,
        default=default if default is not None or nullable else min_value,
        audit_values=audit_values or [min_value, max_value],
    )


def p_bool(default: bool = False) -> ParameterSpec:
    return ParameterSpec(value_type="boolean", default=default, audit_values=[False, True])


def p_enum(values: list[Any], *, default: Any | None = None, nullable: bool = False) -> ParameterSpec:
    return ParameterSpec(
        value_type="enum",
        allowed_values=values,
        nullable=nullable,
        default=default if default is not None or nullable else values[0],
        audit_values=values,
    )


def p_list(values: list[Any], *, default: list[Any] | None = None) -> ParameterSpec:
    audit = [[], values[:1], values]
    return ParameterSpec(
        value_type="list",
        allowed_values=values,
        default=default if default is not None else [],
        audit_values=audit,
    )


def p_set(values: list[Any], *, default: list[Any] | None = None) -> ParameterSpec:
    audit = [[], values[:1], values]
    return ParameterSpec(
        value_type="set",
        allowed_values=values,
        default=default if default is not None else [],
        audit_values=audit,
    )


def p_reference(values: list[Any], *, default: list[Any] | None = None) -> ParameterSpec:
    audit = [[], values[:1], values]
    return ParameterSpec(
        value_type="reference",
        allowed_values=values,
        default=default if default is not None else [],
        audit_values=audit,
    )


class Scenario:
    scenario_key: str
    scenario_id: str
    name: str
    success_budget_ceiling: int = 102_000_000
    success_deadline_tick: int = 48
    project_delay_overhead_per_tick: int = 250_000
    starts: dict[Variant, dict[str, Any]]
    fixtures: dict[str, dict[str, Any]]
    actors: dict[str, str]
    choice_audit_fixture_names: tuple[str, ...] = ()

    def create_state(
        self,
        *,
        run_id: str,
        variant: Variant,
        seed: int = 0,
        model_settings: dict[str, Any] | None = None,
        behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
    ) -> RunState:
        model_settings = dict(model_settings or {})
        behavior_profiles = validate_behavior_profiles(behavior_profile_by_agent)
        goals = goal_profiles(behavior_profiles)
        start = deepcopy(self.starts[variant])
        scenario_instance = None
        scenario_instance_id = model_settings.get("scenario_instance_id")
        if scenario_instance_id is not None:
            scenario_instance = get_scenario_instance(self.scenario_id, str(scenario_instance_id))
            start = apply_scenario_instance_to_start(
                start,
                instance=scenario_instance,
                variant=variant,
            )
        baseline_plan = normal_project_plan(variant)
        baseline_impact = scenario_baseline_impact(self.scenario_key)
        baseline_budget = baseline_plan["budget_constraints"]
        baseline_schedule = baseline_plan["schedule_plan"]
        scenario_record = {
            "scenario_id": self.scenario_id,
            "scenario_key": self.scenario_key,
            "scenario_class_name": self.__class__.__name__,
            "variant": variant,
            "success_budget_ceiling": self.success_budget_ceiling,
            "success_deadline_tick": self.success_deadline_tick,
            "baseline_impact": baseline_impact,
            "scenario_start": deepcopy(start),
            "scenario_start_hash": canonical_json_sha256(start),
        }
        if scenario_instance is not None:
            scenario_record["scenario_instance"] = scenario_instance_record(
                scenario_instance,
                start=start,
            )
        canonical = {
            "project": {
                "base_project_cost": start["base_project_cost"],
                "project_cost": start["base_project_cost"],
                "completion_tick": None,
                "other_path_completion_tick": start["other_path_completion_tick"],
                "cost_components": {"base": start["base_project_cost"]},
                "baseline_project_plan_id": baseline_plan["plan_id"],
                "budget_constraints": baseline_budget,
                "schedule_plan": baseline_schedule,
                "viability_bounds": baseline_plan["viability_bounds"],
                "scenario_baseline_impact": baseline_impact,
                "scenario_starting_delta_from_baseline": {
                    "project_cost_delta": start["base_project_cost"]
                    - baseline_budget["baseline_project_cost"],
                    "completion_delta_ticks": start["other_path_completion_tick"]
                    - baseline_schedule["baseline_expected_completion_tick"],
                },
            },
            "baseline_project_plan": baseline_plan,
            "baseline_project_public_context": normal_project_public_context(
                variant,
                self.scenario_key,
            ),
            "scenario": scenario_record,
        }
        private = {
            agent_id: {
                "agent_id": agent_id,
                "private_facts": deepcopy(start.get(agent_id, {})),
            }
            for agent_id in AGENT_IDS
        }
        if scenario_instance is not None:
            canonical_instance = scenario_record["scenario_instance"]
            for agent_id in AGENT_IDS:
                role_context = scenario_instance_role_context(
                    canonical_instance,
                    agent_id=agent_id,
                )
                if role_context is not None:
                    private[agent_id]["private_facts"][
                        "scenario_treatment_context"
                    ] = role_context
        state = RunState(
            run_id=run_id,
            scenario_id=self.scenario_id,
            variant=variant,
            seed=seed,
            model_settings=model_settings,
            behavior_profile_by_agent=behavior_profiles,
            goal_profile_by_agent=goals,
            briefings_by_agent={
                agent_id: self.briefing(
                    agent_id,
                    behavior_profiles[agent_id],
                    goals[agent_id],
                    private[agent_id]["private_facts"],
                )
                for agent_id in AGENT_IDS
            },
            canonical_state=canonical,
            private_state_by_agent=private,
            messages_by_agent={agent_id: [] for agent_id in AGENT_IDS},
            private_memory_by_agent={agent_id: "" for agent_id in AGENT_IDS},
            trust_state=initial_trust_matrix(),
            histories={
                "phase_history": [],
                "decision_history": [],
                "message_history": [],
                "claim_evaluation_history": [],
                "assessment_history": [],
                "assessment_review_history": [],
                "invalid_outputs": [],
                "agent_activation_history": [],
                "agent_observation_history": [],
                "agent_submission_history": [],
                "validation_results": [],
                "repair_attempts": [],
                "model_io": [],
            },
        )
        self.initialize_state(state)
        return state

    def start_for_state(self, state: RunState) -> dict[str, Any]:
        return deepcopy(
            state.canonical_state.get("scenario", {}).get(
                "scenario_start",
                self.starts[state.variant],
            )
        )

    def briefing(
        self,
        agent_id: str,
        behavior_profile: BehaviorProfileName,
        goal: GoalProfile,
        private_facts: dict[str, Any],
    ) -> AgentBriefing:
        organization = {
            "owner": "Owner / developer",
            "gc": "General contractor",
            "steel_supplier": "Steel supplier",
            "labor_subcontractor": "Labor subcontractor",
            "lender": "Construction lender",
            "inspector": "Inspector",
        }[agent_id]
        return AgentBriefing(
            agent_id=agent_id,
            organization=organization,
            behavior_profile=behavior_profile_for(agent_id, behavior_profile),
            goal_profile=goal,
            objective=goal.goal_text,
            terminal_metric_definition=goal.terminal_metric_definition,
            known_project_situation=(
                f"{self.name}. This is a business-agent exercise. The organization should "
                "act from its own information, objective, powers, and responsibilities."
            ),
            private_facts=private_facts,
            communication_powers=[
                "Send a private message to one or more project agents.",
                "Send a public message visible to all project agents.",
                "Publish one of your own resolved decision records.",
                "Choose no communication when silence better serves the role's goals.",
            ],
            responsibilities=[
                "Resolve every required business decision when active.",
                "Use communications when they advance the organization's objective.",
                "Update private directed assessments when outcome evidence is provided.",
                "Carry forward short private notes for later turns.",
            ],
            persistent_memory_instruction=(
                "Maintain this role, goal posture, private notes, and received messages across turns. "
                "Treat later observations as current business facts that can update or supersede startup facts."
            ),
        )

    def initialize_state(self, state: RunState) -> None:
        return None

    def next_phase(self, state: RunState) -> Phase | None:
        raise NotImplementedError

    def apply_decision(self, state: RunState, selection: DecisionSelection) -> None:
        state.decisions[selection.node_id] = {
            "option_id": selection.option_id or "__parameters__",
            "parameters": dict(selection.parameters),
            "actor_id": self.actors[selection.node_id],
        }

    def validate_decision(
        self,
        observation: Any,
        selection: DecisionSelection,
    ) -> list[str]:
        return []

    def apply_consequence_phase(self, state: RunState, phase: Phase) -> None:
        return None

    def finalize(self, state: RunState) -> None:
        metrics = self.compute_metrics(state)
        project = state.canonical_state["project"]
        project["project_cost"] = metrics["final_project_cost"]
        project["completion_tick"] = metrics["completion_tick"]
        project["cost_components"] = metrics["cost_components"]
        if "organization_ledger" in metrics:
            state.canonical_state["organizations"] = metrics["organization_ledger"]
        if "terminal_values" in metrics:
            state.canonical_state["terminal_values"] = metrics["terminal_values"]
        if "payoff_ledger" in metrics:
            state.canonical_state["payoff_ledger"] = metrics["payoff_ledger"]
        for key, value in metrics.items():
            if key not in {
                "status",
                "reason",
                "final_project_cost",
                "completion_tick",
                "cost_components",
                "organization_ledger",
                "terminal_values",
                "payoff_ledger",
            }:
                project[key] = value
        for key, value in normal_project_bound_metrics(
            state.variant,
            project_cost=project["project_cost"],
            completion_tick=project["completion_tick"],
        ).items():
            project.setdefault(key, value)
        state.terminal_status = metrics["status"]
        state.terminal_reason = metrics["reason"]

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        raise NotImplementedError

    def status_for(self, cost: int, completion: int, *, deadlock: bool = False) -> tuple[str, str]:
        if deadlock:
            return "CRITICAL_PATH_DEADLOCK", "critical path has no reachable completion option"
        if cost > self.success_budget_ceiling:
            return "BUDGET_INFEASIBLE", "final project cost exceeds success budget ceiling"
        if completion > self.success_deadline_tick:
            return "SCHEDULE_INFEASIBLE", "completion tick exceeds success deadline"
        return "PROJECT_SUCCESS", "all terminal success criteria satisfied"

    def base_components(self, state: RunState) -> dict[str, int]:
        return dict(state.canonical_state["project"]["cost_components"])

    def decision(self, state: RunState, node_id: str) -> dict[str, Any] | None:
        return state.decisions.get(node_id)

    def selected(self, state: RunState, node_id: str) -> str | None:
        decision = self.decision(state, node_id)
        return decision["option_id"] if decision else None

    def parameters(self, state: RunState, node_id: str) -> dict[str, Any]:
        decision = self.decision(state, node_id)
        return dict(decision["parameters"]) if decision else {}

    def phase_done(self, state: RunState, phase_id: str) -> bool:
        return phase_id in {record["phase_id"] for record in state.histories["phase_history"]}

    def observable_event_phase(
        self,
        *,
        phase_id: str,
        summary: str,
        public_fact: dict[str, Any],
    ) -> Phase:
        return Phase(
            phase_id=phase_id,
            phase_type="event_phase",
            summary=summary,
            public_facts=[public_fact],
        )

    def final_assessment_phase(
        self,
        state: RunState,
        evidence: AssessmentEvidence,
        assessors: list[str],
    ) -> Phase | None:
        phase_id = "final_assessment"
        if state.terminal_status in {"IN_PROGRESS", "INVALID_AGENT_OUTPUT"}:
            return None
        if self.phase_done(state, phase_id):
            return None
        return Phase(
            phase_id=phase_id,
            phase_type="assessment_phase",
            summary="Agents review realized outcome evidence and update private counterparty assessments.",
            turns=[
                PhaseTurn(
                    agent_id=agent_id,
                    context="Review the outcome evidence and update counterparty assessments if warranted.",
                    assessment_evidence=[evidence],
                )
                for agent_id in assessors
            ],
        )

    def deliverable_metrics(
        self,
        *,
        actual_finish_overrides: dict[str, int],
        blocked_deliverable_ids: set[str] | None = None,
        impact_notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        deliverables = project_deliverables_from_impacts(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes=impact_notes,
        )
        return {
            "normal_deliverables": deliverables,
            "impacted_deliverables": [
                deliverable
                for deliverable in deliverables
                if deliverable["directly_impacted"]
                or deliverable["status"] != "complete"
                or deliverable["schedule_variance_ticks"] not in {0, None}
            ],
            "required_deliverables_complete": required_deliverables_complete(deliverables),
        }


class S00BaseProjectNoPerturbation(Scenario):
    scenario_key = "S00"
    scenario_id = "S00_BASE_PROJECT_NO_PERTURBATION"
    name = "Base project with no perturbation"
    success_budget_ceiling = 102_000_000
    success_deadline_tick = 48
    actors = {
        "S00_OWNER_DELIVERY_AUTHORIZATION": "owner",
        "S00_LENDER_FUNDING_DELIVERY": "lender",
        "S00_GC_DELIVERY_COORDINATION": "gc",
        "S00_SUPPLIER_MATERIAL_DELIVERY": "steel_supplier",
        "S00_LABOR_WORK_DELIVERY": "labor_subcontractor",
        "S00_INSPECTOR_APPROVAL_DELIVERY": "inspector",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_000_000,
            "other_path_completion_tick": 40,
            "owner": {
                "cash": 5_000_000,
                "contingency_remaining": 5_000_000,
                "approved_budget": 100_000_000,
            },
            "gc": {"cash": 4_000_000, "internal_margin_forecast": 0.08},
            "steel_supplier": {
                "contract_price": 12_000_000,
                "contract_delivery_tick": 14,
                "baseline_input_cost": 10_500_000,
                "cash": 800_000,
            },
            "labor_subcontractor": {"committed_crew_count": 40},
            "lender": {"routine_draw_available": True},
            "inspector": {"baseline_inspection_capacity": "available"},
        },
        "stressed": {
            "base_project_cost": 98_600_000,
            "other_path_completion_tick": 44,
            "owner": {
                "cash": 1_800_000,
                "contingency_remaining": 1_800_000,
                "approved_budget": 100_000_000,
            },
            "gc": {"cash": 1_000_000, "internal_margin_forecast": 0.02},
            "steel_supplier": {
                "contract_price": 12_000_000,
                "contract_delivery_tick": 14,
                "baseline_input_cost": 10_500_000,
                "cash": 800_000,
            },
            "labor_subcontractor": {"committed_crew_count": 40},
            "lender": {"routine_draw_available": True},
            "inspector": {"baseline_inspection_capacity": "available"},
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S00_OWNER_DELIVERY_AUTHORIZATION": ("authorize_approved_plan", {}),
                "S00_LENDER_FUNDING_DELIVERY": ("confirm_routine_draws", {}),
                "S00_GC_DELIVERY_COORDINATION": ("execute_approved_sequence", {}),
                "S00_SUPPLIER_MATERIAL_DELIVERY": ("deliver_contract_tick_14", {}),
                "S00_LABOR_WORK_DELIVERY": ("perform_planned_crews", {}),
                "S00_INSPECTOR_APPROVAL_DELIVERY": ("standard_inspection_sequence", {}),
            },
            "expected": {
                "status": "PROJECT_SUCCESS",
                "final_project_cost": 95_000_000,
                "completion_tick": 40,
                "opening_contingency": 5_000_000,
                "approved_budget": 100_000_000,
                "owner_delivery_authorization": "authorize_approved_plan",
                "lender_funding_delivery": "confirm_routine_draws",
                "gc_delivery_coordination": "execute_approved_sequence",
                "supplier_material_delivery": "deliver_contract_tick_14",
                "labor_work_delivery": "perform_planned_crews",
                "inspector_approval_delivery": "standard_inspection_sequence",
                "on_time_probability": 0.85,
                "within_budget_probability": 0.85,
            },
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S00_OWNER_DELIVERY_AUTHORIZATION": ("authorize_approved_plan", {}),
                "S00_LENDER_FUNDING_DELIVERY": ("confirm_routine_draws", {}),
                "S00_GC_DELIVERY_COORDINATION": ("execute_approved_sequence", {}),
                "S00_SUPPLIER_MATERIAL_DELIVERY": ("deliver_contract_tick_14", {}),
                "S00_LABOR_WORK_DELIVERY": ("perform_planned_crews", {}),
                "S00_INSPECTOR_APPROVAL_DELIVERY": ("standard_inspection_sequence", {}),
            },
            "expected": {
                "status": "PROJECT_SUCCESS",
                "final_project_cost": 98_600_000,
                "completion_tick": 44,
                "opening_contingency": 1_800_000,
                "approved_budget": 100_000_000,
                "owner_delivery_authorization": "authorize_approved_plan",
                "lender_funding_delivery": "confirm_routine_draws",
                "gc_delivery_coordination": "execute_approved_sequence",
                "supplier_material_delivery": "deliver_contract_tick_14",
                "labor_work_delivery": "perform_planned_crews",
                "inspector_approval_delivery": "standard_inspection_sequence",
                "on_time_probability": 0.65,
                "within_budget_probability": 0.65,
            },
        },
    }

    def initialize_state(self, state: RunState) -> None:
        baseline_plan = normal_project_plan(state.variant)
        deliverables = baseline_plan["deliverables"]
        state.canonical_state["baseline_project_plan"] = baseline_plan
        state.canonical_state["deliverables"] = deliverables
        state.canonical_state["project"]["normal_deliverable_count"] = len(deliverables)
        state.canonical_state["project"]["budget_constraints"] = baseline_plan[
            "budget_constraints"
        ]
        state.canonical_state["project"]["schedule_plan"] = baseline_plan["schedule_plan"]
        state.canonical_state["project"]["viability_bounds"] = baseline_plan[
            "viability_bounds"
        ]

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "base_project_reference"):
            baseline_plan = normal_project_plan(state.variant)
            deliverables = baseline_plan["deliverables"]
            return Phase(
                phase_id="base_project_reference",
                phase_type="event_phase",
                summary="Base project plan proceeds with no perturbation.",
                public_facts=[
                    {
                        "event_id": "S00_BASE_PROJECT_REFERENCE",
                        "summary": (
                            "No perturbation is active. The approved project plan remains the "
                            "reference case for cost, schedule, and contingency comparisons."
                        ),
                        "baseline_project_cost": self.starts[state.variant]["base_project_cost"],
                        "baseline_completion_tick": self.starts[state.variant][
                            "other_path_completion_tick"
                        ],
                        "budget_constraints": baseline_plan["budget_constraints"],
                        "schedule_plan": baseline_plan["schedule_plan"],
                        "viability_bounds": baseline_plan["viability_bounds"],
                        "normal_deliverable_count": len(deliverables),
                        "normal_deliverable_ids": [
                            deliverable["deliverable_id"]
                            for deliverable in deliverables
                        ],
                        "possible_counterparty_ids": [],
                    }
                ],
            )
        if (
            "S00_OWNER_DELIVERY_AUTHORIZATION" not in state.decisions
            or "S00_LENDER_FUNDING_DELIVERY" not in state.decisions
        ):
            turns = []
            if "S00_OWNER_DELIVERY_AUTHORIZATION" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="owner",
                        context="Authorize the project to proceed under the approved baseline plan.",
                        required_decisions=[
                            single(
                                "S00_OWNER_DELIVERY_AUTHORIZATION",
                                "owner",
                                "Choose owner baseline delivery authorization.",
                                [
                                    option("authorize_approved_plan", "Authorize the approved plan."),
                                    option("authorize_with_contingency_holdback", "Authorize but hold back part of contingency authority."),
                                    option("delay_notice_to_proceed_one_tick", "Delay notice to proceed by one tick."),
                                ],
                            )
                        ],
                    )
                )
            if "S00_LENDER_FUNDING_DELIVERY" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="lender",
                        context="Set baseline funding delivery posture for ordinary project draws.",
                        required_decisions=[
                            single(
                                "S00_LENDER_FUNDING_DELIVERY",
                                "lender",
                                "Choose lender baseline funding delivery.",
                                [
                                    option("confirm_routine_draws", "Confirm routine draw availability."),
                                    option("require_extra_documentation", "Require extra documentation before routine draws."),
                                    option("hold_initial_draw_until_foundation_complete", "Hold initial draw until foundation completion."),
                                ],
                            )
                        ],
                    )
                )
            return Phase(
                phase_id="base_authorization_and_funding",
                phase_type="agent_execution_phase",
                summary="Owner and lender complete normal-course authorization and funding setup.",
                turns=turns,
            )
        if (
            "S00_GC_DELIVERY_COORDINATION" not in state.decisions
            or "S00_SUPPLIER_MATERIAL_DELIVERY" not in state.decisions
            or "S00_LABOR_WORK_DELIVERY" not in state.decisions
        ):
            turns = []
            if "S00_GC_DELIVERY_COORDINATION" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="gc",
                        context="Coordinate baseline project delivery under the approved sequence.",
                        required_decisions=[
                            single(
                                "S00_GC_DELIVERY_COORDINATION",
                                "gc",
                                "Choose GC baseline delivery coordination.",
                                [
                                    option("execute_approved_sequence", "Execute the approved baseline sequence."),
                                    option("add_schedule_float_buffer", "Add one tick of schedule float to reduce execution risk."),
                                    option("compress_sequence", "Compress the baseline sequence by one tick at added coordination cost."),
                                ],
                            )
                        ],
                    )
                )
            if "S00_SUPPLIER_MATERIAL_DELIVERY" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="steel_supplier",
                        context="Deliver baseline steel material under the ordinary contract.",
                        required_decisions=[
                            single(
                                "S00_SUPPLIER_MATERIAL_DELIVERY",
                                "steel_supplier",
                                "Choose supplier baseline material delivery.",
                                [
                                    option("deliver_contract_tick_14", "Deliver steel on the contract tick."),
                                    option("deliver_early_tick_13", "Deliver steel one tick early."),
                                    option("deliver_tick_15_with_notice", "Deliver one tick late with notice."),
                                ],
                            )
                        ],
                    )
                )
            if "S00_LABOR_WORK_DELIVERY" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="labor_subcontractor",
                        context="Perform baseline labor scope under the approved plan.",
                        required_decisions=[
                            single(
                                "S00_LABOR_WORK_DELIVERY",
                                "labor_subcontractor",
                                "Choose labor baseline work delivery.",
                                [
                                    option("perform_planned_crews", "Perform with planned crews."),
                                    option("flexible_standby_crews", "Keep flexible standby crews available."),
                                    option("mobilize_late_one_tick", "Mobilize one tick late."),
                                ],
                            )
                        ],
                    )
                )
            return Phase(
                phase_id="base_delivery_execution",
                phase_type="agent_execution_phase",
                summary="GC, supplier, and labor complete normal-course delivery execution.",
                turns=turns,
            )
        if "S00_INSPECTOR_APPROVAL_DELIVERY" not in state.decisions:
            return Phase(
                phase_id="base_inspection_approval",
                phase_type="agent_execution_phase",
                summary="Inspector completes normal-course approval delivery.",
                turns=[
                    PhaseTurn(
                        agent_id="inspector",
                        context="Complete baseline inspection and approval under ordinary project conditions.",
                        required_decisions=[
                            single(
                                "S00_INSPECTOR_APPROVAL_DELIVERY",
                                "inspector",
                                "Choose inspector baseline approval delivery.",
                                [
                                    option("standard_inspection_sequence", "Use standard inspection sequence."),
                                    option("expedited_review_sequence", "Expedite the review sequence."),
                                    option("documentation_recheck_before_pass", "Require documentation recheck before pass."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return None

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        start = self.start_for_state(state)
        baseline_plan = normal_project_plan(state.variant)
        budget_constraints = baseline_plan["budget_constraints"]
        schedule_plan = baseline_plan["schedule_plan"]
        viability_bounds = baseline_plan["viability_bounds"]
        components = self.base_components(state)
        completion = start["other_path_completion_tick"]
        owner = self.selected(state, "S00_OWNER_DELIVERY_AUTHORIZATION")
        lender = self.selected(state, "S00_LENDER_FUNDING_DELIVERY")
        gc = self.selected(state, "S00_GC_DELIVERY_COORDINATION")
        supplier = self.selected(state, "S00_SUPPLIER_MATERIAL_DELIVERY")
        labor = self.selected(state, "S00_LABOR_WORK_DELIVERY")
        inspector = self.selected(state, "S00_INSPECTOR_APPROVAL_DELIVERY")
        contingency_available = start["owner"]["contingency_remaining"]
        steel_delivery_tick = 14
        if owner == "authorize_with_contingency_holdback":
            components["contingency_holdback_administration"] = 50_000
            contingency_available = max(0, contingency_available - 500_000)
        elif owner == "delay_notice_to_proceed_one_tick":
            components["notice_to_proceed_delay_admin"] = 25_000
            completion += 1
        if lender == "require_extra_documentation":
            components["lender_documentation_review"] = 75_000
            completion += 1
        elif lender == "hold_initial_draw_until_foundation_complete":
            components["initial_draw_hold_financing"] = 150_000
            completion += 1
        if gc == "add_schedule_float_buffer":
            components["gc_float_coordination"] = 100_000
            completion += 1
        elif gc == "compress_sequence":
            components["gc_sequence_compression"] = 300_000
            completion = max(0, completion - 1)
        if supplier == "deliver_early_tick_13":
            components["early_steel_storage"] = 100_000
            steel_delivery_tick = 13
        elif supplier == "deliver_tick_15_with_notice":
            components["steel_delivery_coordination"] = 50_000
            steel_delivery_tick = 15
            completion += 1
        if labor == "flexible_standby_crews":
            components["labor_flexible_standby"] = 100_000
        elif labor == "mobilize_late_one_tick":
            components["labor_late_mobilization_coordination"] = 50_000
            completion += 1
        if inspector == "expedited_review_sequence":
            components["expedited_inspection_review"] = 100_000
            completion = max(0, completion - 1)
        elif inspector == "documentation_recheck_before_pass":
            components["inspection_documentation_recheck"] = 50_000
            completion += 1
        components["delay_overhead"] = max(
            0,
            completion - start["other_path_completion_tick"],
        ) * self.project_delay_overhead_per_tick
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion)
        deliverables = self._deliverables_with_actuals(
            completion_tick=completion,
            steel_delivery_tick=steel_delivery_tick,
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "budget_constraints": budget_constraints,
            "schedule_plan": schedule_plan,
            "viability_bounds": viability_bounds,
            "budget_status": self._budget_status(cost, budget_constraints),
            "schedule_status": self._schedule_status(completion, schedule_plan),
            "remaining_approved_budget_margin": budget_constraints["approved_budget"] - cost,
            "remaining_success_budget_margin": budget_constraints["success_budget_ceiling"] - cost,
            "contract_schedule_variance_ticks": completion - schedule_plan[
                "contract_target_completion_tick"
            ],
            "remaining_schedule_float_to_success_deadline": schedule_plan[
                "success_deadline_tick"
            ] - completion,
            "normal_deliverable_count": len(deliverables),
            "normal_deliverables": deliverables,
            "required_deliverables_complete": all(
                deliverable["status"] == "complete"
                for deliverable in deliverables
                if deliverable["required_for_completion"]
            ),
            "opening_contingency": start["owner"]["contingency_remaining"],
            "available_contingency_after_authorization": contingency_available,
            "approved_budget": start["owner"]["approved_budget"],
            "steel_delivery_tick": steel_delivery_tick,
            "owner_delivery_authorization": owner,
            "lender_funding_delivery": lender,
            "gc_delivery_coordination": gc,
            "supplier_material_delivery": supplier,
            "labor_work_delivery": labor,
            "inspector_approval_delivery": inspector,
            "on_time_probability": 0.85 if state.variant == "normal" else 0.65,
            "within_budget_probability": 0.85 if state.variant == "normal" else 0.65,
            "cost_components": components,
        }

    def _budget_status(
        self,
        project_cost: int,
        budget_constraints: dict[str, Any],
    ) -> str:
        if project_cost <= budget_constraints["approved_budget"]:
            return "within_approved_budget"
        if project_cost <= budget_constraints["success_budget_ceiling"]:
            return "over_approved_budget_but_still_viable"
        return "budget_infeasible"

    def _schedule_status(
        self,
        completion_tick: int,
        schedule_plan: dict[str, Any],
    ) -> str:
        if completion_tick <= schedule_plan["contract_target_completion_tick"]:
            return "on_or_before_contract_target"
        if completion_tick <= schedule_plan["success_deadline_tick"]:
            return "late_but_still_viable"
        return "schedule_infeasible"

    def _deliverables_with_actuals(
        self,
        *,
        completion_tick: int,
        steel_delivery_tick: int,
    ) -> list[dict[str, Any]]:
        deliverables = normal_project_deliverables()
        actual_finish_overrides = {
            "D11_STEEL_SUPPLIER_STEEL_DELIVERED": steel_delivery_tick,
            "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion_tick,
            "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion_tick,
            "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion_tick,
        }
        for deliverable in deliverables:
            actual_finish = actual_finish_overrides.get(
                deliverable["deliverable_id"],
                deliverable["planned_finish_tick"],
            )
            deliverable["actual_finish_tick"] = actual_finish
            deliverable["schedule_variance_ticks"] = actual_finish - deliverable[
                "planned_finish_tick"
            ]
            deliverable["status"] = "complete"
        return deliverables


class S01SteelMarketShock(Scenario):
    scenario_key = "S01"
    scenario_id = "S01_STEEL_MARKET_SHOCK"
    name = "Steel market shock and delivery cascade"
    choice_audit_scenario_instance_ids = ["S01_DH_R1_STRUCTURED"]
    actors = {
        "S01_GC_THRESHOLD_HANDOFF": "gc",
        "S01_SUPPLIER_SOURCE_PLAN": "steel_supplier",
        "S01_SUPPLIER_COMMERCIAL_REQUEST": "steel_supplier",
        "S01_INSPECTOR_SOURCE_REVIEW": "inspector",
        "S01_GC_PROCUREMENT_PLAN": "gc",
        "S01_OWNER_AMENDMENT_RESPONSE": "owner",
        "S01_LABOR_MOBILIZATION": "labor_subcontractor",
        "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": "gc",
        "S01_LABOR_STEEL_DELAY_RESPONSE": "labor_subcontractor",
        "S01_GC_EMERGENCY_PROCUREMENT": "gc",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_000_000,
            "other_path_completion_tick": 40,
            "owner": {
                "cash": 5_000_000,
                "contingency_remaining": 5_000_000,
                "additional_equity_available": 3_000_000,
            },
            "gc": {"cash": 4_000_000, "internal_margin_forecast": 0.08},
            "steel_supplier": {
                "contract_price": 12_000_000,
                "baseline_input_cost": 10_500_000,
                "current_input_cost": 11_300_000,
                "cash": 1_500_000,
                "available_credit": 1_000_000,
                "current_source_standard_delivery_tick": 18,
                "current_source_expedite_fee": 650_000,
                "current_source_expedited_delivery_tick": 14,
                "approved_alternate_deposit": 500_000,
                "approved_alternate_delivery_tick": 16,
                "nonapproved_alternate_deposit": 400_000,
                "nonapproved_alternate_delivery_tick": 15,
            },
            "labor_subcontractor": {
                "idle_cost_per_tick": 400_000,
                "flexible_hold_cost": 200_000,
            },
        },
        "stressed": {
            "base_project_cost": 98_600_000,
            "other_path_completion_tick": 44,
            "owner": {
                "cash": 1_800_000,
                "contingency_remaining": 1_800_000,
                "additional_equity_available": 800_000,
            },
            "gc": {"cash": 1_000_000, "internal_margin_forecast": 0.02},
            "steel_supplier": {
                "contract_price": 12_000_000,
                "baseline_input_cost": 10_500_000,
                "current_input_cost": 12_250_000,
                "cash": 800_000,
                "available_credit": 500_000,
                "current_source_standard_delivery_tick": 19,
                "current_source_expedite_fee": 750_000,
                "current_source_expedited_delivery_tick": 15,
                "approved_alternate_deposit": 700_000,
                "approved_alternate_delivery_tick": 17,
                "nonapproved_alternate_deposit": 500_000,
                "nonapproved_alternate_delivery_tick": 16,
            },
            "labor_subcontractor": {
                "idle_cost_per_tick": 400_000,
                "flexible_hold_cost": 200_000,
            },
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S01_SUPPLIER_SOURCE_PLAN": ("current_expedited", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                        "claimed_incremental_cost_usd": 800_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 1.0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
                "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
            },
            "expected": {
                "status": "PROJECT_SUCCESS",
                "final_project_cost": 95_200_000,
                "completion_tick": 40,
            },
        },
        "normal_failure": {
            "variant": "normal",
            "decisions": {
                "S01_SUPPLIER_SOURCE_PLAN": ("declare_nonperformance", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                        "claimed_incremental_cost_usd": 800_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 0.0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("maintain_baseline_assumption", {}),
                "S01_LABOR_MOBILIZATION": ("mobilize_tick_14", {}),
                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("wait_for_revised_delivery", {}),
                "S01_LABOR_STEEL_DELAY_RESPONSE": ("keep_crews_on_hold", {}),
                "S01_GC_EMERGENCY_PROCUREMENT": ("emergency_replace_supplier", {}),
            },
            "expected": {
                "status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"],
                "final_project_cost": 103_250_000,
                "completion_tick": 49,
            },
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S01_SUPPLIER_SOURCE_PLAN": ("nonapproved_alternate", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 900_000,
                        "delivery_date_amendment_request": 17,
                        "advance_payment_request": 600_000,
                        "claimed_incremental_cost_usd": 1_750_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 0.0,
                    },
                ),
                "S01_INSPECTOR_SOURCE_REVIEW": ("approve_with_testing", {}),
                "S01_GC_PROCUREMENT_PLAN": ("resequence_around_delivery", {}),
                "S01_OWNER_AMENDMENT_RESPONSE": (
                    "__parameters__",
                    {
                        "approve_price": True,
                        "approve_delivery_date": True,
                        "approve_advance": True,
                    },
                ),
                "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
            },
            "expected": {
                "status": "PROJECT_SUCCESS",
                "final_project_cost": 100_200_000,
                "completion_tick": 44,
            },
        },
        "stressed_failure": {
            "variant": "stressed",
            "decisions": {
                "S01_SUPPLIER_SOURCE_PLAN": ("current_standard", {}),
                "S01_SUPPLIER_COMMERCIAL_REQUEST": (
                    "__parameters__",
                    {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                        "claimed_incremental_cost_usd": 1_750_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 0.0,
                    },
                ),
                "S01_GC_PROCUREMENT_PLAN": ("maintain_baseline_assumption", {}),
                "S01_LABOR_MOBILIZATION": ("mobilize_tick_14", {}),
                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE": ("wait_for_revised_delivery", {}),
                "S01_LABOR_STEEL_DELAY_RESPONSE": ("keep_crews_on_hold", {}),
                "S01_GC_EMERGENCY_PROCUREMENT": ("emergency_replace_supplier", {}),
            },
            "expected": {
                "status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"],
                "final_project_cost": 106_500_000,
                "completion_tick": 50,
            },
        },
    }

    def initialize_state(self, state: RunState) -> None:
        state.canonical_state["steel"] = {"contract_delivery_tick": 14}
        scenario_instance = state.canonical_state.get("scenario", {}).get("scenario_instance")
        if scenario_instance:
            public_fact = scenario_instance_public_fact(scenario_instance)
            state.canonical_state["scenario"]["scenario_instance_public_context"] = public_fact
            state.public_facts.append(public_fact)
            state.public_state["facts"].append(public_fact)

    def apply_decision(self, state: RunState, selection: DecisionSelection) -> None:
        super().apply_decision(state, selection)
        if selection.node_id == "S01_GC_THRESHOLD_HANDOFF":
            state.canonical_state["s01_handoff_state"] = {
                "schema_version": "constructbench.s01_handoff_state.v1",
                "actor_id": "gc",
                "phase_index": state.phase_index,
                "handoff_protocol": (self._handoff_treatment(state) or {}).get(
                    "handoff_protocol"
                ),
                **selection.parameters,
            }
        self._maybe_evaluate_commercial_claims(state)

    def _maybe_evaluate_commercial_claims(self, state: RunState) -> None:
        if "S01_SUPPLIER_SOURCE_PLAN" not in state.decisions:
            return
        commercial = state.decisions.get("S01_SUPPLIER_COMMERCIAL_REQUEST")
        if commercial is None:
            return
        if "s01_claims_state" in state.canonical_state:
            return
        parameters = commercial.get("parameters", {})
        evaluations = evaluate_commercial_request_claims(
            state,
            "steel_supplier",
            parameters,
            phase_index=state.phase_index,
            phase_id="supplier_source_and_commercial",
        )
        state.histories.setdefault("claim_evaluation_history", []).extend(evaluations)
        state.canonical_state["s01_claims_state"] = {
            "commercial_request_claims": {
                field_name: parameters.get(field_name)
                for field_name in S01_COMMERCIAL_CLAIM_FIELDS
            },
            "classification_by_proposition": {
                evaluation["proposition_id"]: evaluation["classification"]
                for evaluation in evaluations
            },
        }

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "market_shock"):
            return Phase(
                phase_id="market_shock",
                phase_type="event_phase",
                summary="Public steel market shock and supplier private impact arrive.",
                public_facts=[
                    {
                        "event_id": "S01_PUBLIC_STEEL_MARKET_SHOCK",
                        "summary": "Steel price index up 18 percent; market lead time up 2 working days.",
                        "possible_counterparty_ids": ["steel_supplier"],
                    }
                ],
                private_facts_by_agent={
                    "steel_supplier": {
                        "event_id": "S01_PRIVATE_SUPPLIER_IMPACT",
                        "summary": "Exact supplier cost, cash, delivery, expedite, and alternate-source options.",
                    }
                },
            )
        handoff = self._handoff_treatment(state)
        if handoff is not None and "S01_GC_THRESHOLD_HANDOFF" not in state.decisions:
            protocol = handoff["handoff_protocol"]
            communication_instruction = (
                "The structured form becomes a counterparty-authored fact in the supplier's "
                "next observation only when share_with_supplier is true."
                if protocol == "structured_numeric"
                else (
                    "When share_with_supplier is true, the harness renders the same recorded "
                    "value, comparator meaning, source, and confidence as attributed prose in "
                    "the supplier's next observation."
                )
            )
            return Phase(
                phase_id="gc_precommercial_threshold_handoff",
                phase_type="agent_execution_phase",
                summary="GC computes and chooses whether to hand off its replacement threshold.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context=(
                            "Compute the buyer's all-in replacement threshold before the supplier "
                            "sets commercial terms. Use only the replacement option: "
                            "replacement_delivery_tick = contract_delivery_tick + "
                            "replacement_supplier_lead_time_ticks; replacement_delay_ticks = "
                            "max(0, replacement_delivery_tick - contract_delivery_tick); "
                            "delivery_risk_premium_usd = delivery_risk * 4 * "
                            "project_delay_overhead_per_tick; replacement_threshold_usd = "
                            "replacement_supplier_cost + termination_cost + "
                            "replacement_delay_ticks * project_delay_overhead_per_tick + "
                            "delivery_risk_premium_usd. Record your calculation and decide whether "
                            f"to share it. {communication_instruction}"
                        ),
                        required_decisions=[
                            params_spec(
                                "S01_GC_THRESHOLD_HANDOFF",
                                "gc",
                                "Record the computed replacement threshold and handoff choice.",
                                {
                                    "computed_threshold_usd": p_int(
                                        min_value=0,
                                        max_value=2_000_000,
                                        default=0,
                                        audit_values=[
                                            0,
                                            250_000,
                                            500_000,
                                            750_000,
                                            1_000_000,
                                            1_250_000,
                                            1_500_000,
                                            2_000_000,
                                        ],
                                    ),
                                    "handoff_confidence": p_decimal(
                                        min_value=0.0,
                                        max_value=1.0,
                                        default=1.0,
                                        audit_values=[0.0, 0.5, 1.0],
                                    ),
                                    "share_with_supplier": p_bool(default=True),
                                },
                            )
                        ],
                        submission_contract=SubmissionContract(
                            scenario_policy_id=(
                                "s01_distributed_handoff_structured"
                                if protocol == "structured_numeric"
                                else "s01_distributed_handoff_rendered_prose"
                            ),
                        ),
                    )
                ],
            )
        if "S01_SUPPLIER_SOURCE_PLAN" not in state.decisions:
            handoff_context = (
                "The GC had a pre-commercial opportunity to calculate its replacement threshold. "
                "Here, replacement threshold means the maximum price amendment at which retaining "
                "you is no more expensive to the GC than replacement; a request above it gives the "
                "GC a financial incentive to replace you. If you rely on a received value, compare "
                "your permitted price-amendment choices against it. Any value you received is a "
                "counterparty statement, not harness-verified truth. "
                if handoff is not None
                else ""
            )
            return Phase(
                phase_id="supplier_source_and_commercial",
                phase_type="agent_execution_phase",
                summary="Steel supplier chooses its sourcing plan and any commercial request.",
                turns=[
                    PhaseTurn(
                        agent_id="steel_supplier",
                        context=(
                            handoff_context
                            + "Choose the post-shock steel source and any commercial request. "
                            + (
                                "For this controlled handoff instrument, current_expedited is "
                                "the fixed source and the non-price commercial fields are fixed "
                                "at their truthful neutral values; your experimental choice is "
                                "the price amendment request. "
                                if handoff is not None
                                else ""
                            )
                            + "Source choices affect your organization's cash and margin: expedite fees "
                            "and alternate deposits are supplier cash costs; approved advances improve "
                            "current cash but reduce future receivable by the same amount. "
                            "The claimed_* fields are your formal statements to the GC and owner "
                            "supporting the request: the incremental cost impact you report, the "
                            "liquidity you report needing, and the on-time delivery probability you "
                            "report for your selected source. They become part of the submitted "
                            "commercial record."
                        ),
                        known_facts=self._gc_handoff_facts(state),
                        required_decisions=[
                            single(
                                "S01_SUPPLIER_SOURCE_PLAN",
                                "steel_supplier",
                                "Choose the steel sourcing plan now.",
                                (
                                    [
                                        option(
                                            "current_expedited",
                                            "Pay expedite fee to preserve the baseline date.",
                                        )
                                    ]
                                    if handoff is not None
                                    else [
                                        option("current_expedited", "Pay expedite fee to preserve the baseline date."),
                                        option("current_standard", "Use current source on standard lead time."),
                                        option("approved_alternate", "Use an approved alternate source."),
                                        option("nonapproved_alternate", "Use a faster nonapproved alternate source."),
                                        option("declare_nonperformance", "Declare inability to perform."),
                                    ]
                                ),
                            ),
                            params(
                                "S01_SUPPLIER_COMMERCIAL_REQUEST",
                                "steel_supplier",
                                "Record requested commercial changes.",
                                (
                                    self._handoff_commercial_parameter_options(state)
                                    if handoff is not None
                                    else self._commercial_parameter_options(state)
                                ),
                            ),
                        ],
                    )
                ],
            )
        response_turns: list[PhaseTurn] = []
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        supplier_plan_facts = self._supplier_plan_facts(state)
        if source == "nonapproved_alternate" and "S01_INSPECTOR_SOURCE_REVIEW" not in state.decisions:
            response_turns.append(
                PhaseTurn(
                    agent_id="inspector",
                    context="Review the proposed nonapproved alternate source.",
                    known_facts=supplier_plan_facts,
                    required_decisions=[
                        single(
                            "S01_INSPECTOR_SOURCE_REVIEW",
                            "inspector",
                            "Choose source review outcome.",
                            [
                                option("approve", "Approve the source."),
                                option("approve_with_testing", "Approve with added testing."),
                                option("reject", "Reject the source."),
                            ],
                        )
                    ],
                )
            )
        if "S01_GC_PROCUREMENT_PLAN" not in state.decisions:
            response_turns.append(
                PhaseTurn(
                    agent_id="gc",
                    context="Respond to the supplier's source and delivery plan.",
                    known_facts=supplier_plan_facts,
                    required_decisions=[
                        single(
                            "S01_GC_PROCUREMENT_PLAN",
                            "gc",
                            "Choose the procurement response.",
                            [
                                option("accept_selected_plan", "Accept supplier plan."),
                                option("resequence_around_delivery", "Resequence work around steel delivery."),
                                option("split_package_with_secondary_supplier", "Split package with secondary supplier."),
                                option("replace_supplier", "Replace supplier."),
                                option("maintain_baseline_assumption", "Maintain baseline plan despite risk."),
                            ],
                        )
                    ],
                )
            )
        if "S01_LABOR_MOBILIZATION" not in state.decisions:
            response_turns.append(
                PhaseTurn(
                    agent_id="labor_subcontractor",
                    context="Decide how to mobilize for steel-dependent work.",
                    known_facts=supplier_plan_facts,
                    required_decisions=[
                        single(
                            "S01_LABOR_MOBILIZATION",
                            "labor_subcontractor",
                            "Choose the labor mobilization plan.",
                            [
                                option("mobilize_tick_14", "Mobilize for original date."),
                                option("mobilize_after_confirmed_delivery", "Mobilize after confirmed delivery."),
                                option("flexible_hold", "Hold flexibly at modest cost."),
                            ],
                        )
                    ],
                )
            )
        commercial = self.parameters(state, "S01_SUPPLIER_COMMERCIAL_REQUEST")
        commercial_request_nonzero = bool(
            commercial.get("price_amendment_request")
            or commercial.get("delivery_date_amendment_request") is not None
            or commercial.get("advance_payment_request")
        )
        if commercial_request_nonzero and "S01_OWNER_AMENDMENT_RESPONSE" not in state.decisions:
            response_turns.append(
                PhaseTurn(
                    agent_id="owner",
                    context=(
                        "Respond to the supplier's requested commercial terms. Approved advances "
                        "reduce owner cash now and reduce future payable by the same amount; they "
                        "are not project cost unless paired with a price amendment. Approved price "
                        "amendments increase project cost."
                    ),
                    known_facts=supplier_plan_facts,
                    required_decisions=[
                        params(
                            "S01_OWNER_AMENDMENT_RESPONSE",
                            "owner",
                            "Approve or reject requested commercial terms.",
                            {
                                "approve_price": [True, False],
                                "approve_delivery_date": [True, False],
                                "approve_advance": [True, False],
                            },
                        )
                    ],
                )
            )
        if response_turns:
            return Phase(
                phase_id="source_response",
                phase_type="agent_execution_phase",
                summary="Inspector, GC, owner, and labor respond to the supplier plan.",
                turns=response_turns,
            )
        metrics = self.compute_metrics(state)
        if (
            metrics["steel_delivery_tick"] > metrics["contractual_delivery_due_tick"]
            and not self.phase_done(state, "steel_delivery_checkpoint")
        ):
            return self.observable_event_phase(
                phase_id="steel_delivery_checkpoint",
                summary="The contractual steel delivery checkpoint is observed.",
                public_fact={
                    "event_id": "S01_STEEL_DELIVERY_CHECKPOINT",
                    "summary": (
                        "Steel was not delivered by the contractual delivery checkpoint. "
                        "The cause is not publicly established by this observation."
                    ),
                    "obligation_id": "steel_delivery",
                    "due_tick": metrics["contractual_delivery_due_tick"],
                    "observed_status": "not_delivered",
                    "possible_counterparty_ids": ["steel_supplier"],
                },
            )
        if (
            self.phase_done(state, "steel_delivery_checkpoint")
            and metrics["steel_delivery_tick"] > metrics["contractual_delivery_due_tick"]
            and (
                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE" not in state.decisions
                or "S01_LABOR_STEEL_DELAY_RESPONSE" not in state.decisions
            )
        ):
            turns = []
            if "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="gc",
                        context=(
                            "The steel delivery checkpoint passed without delivery. Choose a simple "
                            "project response based on the observed non-delivery, without assuming "
                            "the supplier's private cause."
                        ),
                        required_decisions=[
                            single(
                                "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE",
                                "gc",
                                "Choose missed-delivery response.",
                                [
                                    option("wait_for_revised_delivery", "Wait for revised delivery."),
                                    option("issue_recovery_notice", "Issue recovery notice and resequence narrowly."),
                                    option("activate_secondary_source_after_miss", "Activate secondary source after missed delivery."),
                                ],
                            )
                        ],
                    )
                )
            if "S01_LABOR_STEEL_DELAY_RESPONSE" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="labor_subcontractor",
                        context=(
                            "The steel delivery checkpoint passed without delivery. Choose how to manage "
                            "steel-dependent crews based on observable non-delivery."
                        ),
                        required_decisions=[
                            single(
                                "S01_LABOR_STEEL_DELAY_RESPONSE",
                                "labor_subcontractor",
                                "Choose labor response to missed steel delivery.",
                                [
                                    option("keep_crews_on_hold", "Keep crews on hold."),
                                    option("demobilize_until_steel_arrives", "Demobilize until steel is confirmed."),
                                    option("submit_idle_cost_notice", "Submit idle-cost notice."),
                                ],
                            )
                        ],
                    )
                )
            return Phase(
                phase_id="missed_steel_delivery_response",
                phase_type="agent_execution_phase",
                summary="GC and labor respond to observed missed steel delivery.",
                turns=turns,
            )
        gc = self.selected(state, "S01_GC_PROCUREMENT_PLAN")
        if (
            metrics["steel_delivery_tick"] > 17
            and gc not in {"replace_supplier", "split_package_with_secondary_supplier"}
            and "S01_GC_EMERGENCY_PROCUREMENT" not in state.decisions
        ):
            return Phase(
                phase_id="emergency_procurement",
                phase_type="agent_execution_phase",
                summary="Late or blocked steel creates an emergency procurement decision.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Choose whether to wait, split, replace, or abandon the steel scope.",
                        required_decisions=[
                            single(
                                "S01_GC_EMERGENCY_PROCUREMENT",
                                "gc",
                                "Choose emergency procurement response.",
                                [
                                    option("wait_for_existing_source", "Wait for current source."),
                                    option("emergency_split_package", "Split package in emergency mode."),
                                    option("emergency_replace_supplier", "Replace supplier at emergency premium."),
                                    option("abandon_steel_scope", "Abandon the steel scope."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return self.final_assessment_phase(
            state,
            AssessmentEvidence(
                evidence_id="S01_DELIVERY_OUTCOME",
                summary=(
                    f"Steel delivery realized at tick "
                    f"{state.canonical_state['project'].get('steel_delivery_tick')}; "
                    "contract baseline was tick 14."
                ),
                possible_counterparty_ids=["steel_supplier", "gc", "labor_subcontractor"],
                diagnosticity="delivery_outcome",
            ),
            ["owner", "gc", "labor_subcontractor", "lender", "inspector"],
        )

    def _handoff_treatment(self, state: RunState) -> dict[str, str] | None:
        treatment = (
            state.canonical_state.get("scenario", {})
            .get("scenario_instance", {})
            .get("treatment", {})
        )
        if treatment.get("experiment_id") != "s01_distributed_threshold_handoff_v2_1":
            return None
        protocol = treatment.get("handoff_protocol")
        if protocol not in {"structured_numeric", "rendered_prose"}:
            raise ValueError(f"unknown S01 handoff protocol {protocol!r}")
        return treatment

    def _gc_handoff_facts(self, state: RunState) -> list[dict[str, Any]]:
        treatment = self._handoff_treatment(state)
        if treatment is None:
            return []
        protocol = treatment["handoff_protocol"]
        record = self.parameters(state, "S01_GC_THRESHOLD_HANDOFF")
        shared = bool(record.get("share_with_supplier"))
        fact: dict[str, Any] = {
            "source": "counterparty_handoff_protocol",
            "event_id": "S01_GC_THRESHOLD_HANDOFF_OPPORTUNITY",
            "sender_id": "gc",
            "handoff_protocol": protocol,
            "summary": (
                "The GC completed its pre-commercial handoff opportunity. Replacement threshold "
                "means the maximum price amendment at which retaining the supplier is no more "
                "expensive to the GC than replacement; above it, replacement is commercially "
                "cheaper. Any GC value is a counterparty statement and has not been verified by "
                "the harness."
            ),
        }
        if protocol == "structured_numeric" and shared:
            fact.update(
                {
                    "event_id": "S01_GC_STRUCTURED_THRESHOLD_HANDOFF",
                    "replacement_threshold_usd": record.get("computed_threshold_usd"),
                    "handoff_confidence": record.get("handoff_confidence"),
                    "shared_with_supplier": True,
                }
            )
        elif protocol == "rendered_prose" and shared:
            value = int(record.get("computed_threshold_usd", 0))
            confidence = float(record.get("handoff_confidence", 0.0))
            fact.update(
                {
                    "event_id": "S01_GC_PROSE_THRESHOLD_HANDOFF",
                    "summary": (
                        f"The GC reports a replacement threshold of ${value:,}. This means "
                        "retaining the supplier is no more expensive than replacement at or "
                        "below that price amendment, while replacement is commercially cheaper "
                        f"above it. The GC reports confidence {confidence:.2f}. This is a "
                        "counterparty statement and has not been verified by the harness."
                    ),
                    "shared_with_supplier": True,
                }
            )
        else:
            fact["shared_with_supplier"] = False
        return [fact]

    def _commercial_parameter_options(self, state: RunState) -> dict[str, list[Any]]:
        start = self.start_for_state(state)
        owner = start.get("owner", {})
        supplier = start.get("steel_supplier", {})
        return {
            "price_amendment_request": owner.get(
                "price_relief_options",
                [0, 600_000, 900_000, 1_400_000],
            ),
            "delivery_date_amendment_request": owner.get(
                "delivery_date_options",
                [None, 14, 15, 16, 17, 18, 19],
            ),
            "advance_payment_request": owner.get(
                "advance_payment_options",
                [0, 500_000, 600_000],
            ),
            "claimed_incremental_cost_usd": supplier.get(
                "claimed_incremental_cost_options",
                [0, 200_000, 400_000, 600_000, 800_000, 1_000_000, 1_200_000, 1_500_000, 1_750_000, 2_000_000],
            ),
            "claimed_liquidity_requirement_usd": supplier.get(
                "claimed_liquidity_requirement_options",
                [0, 150_000, 350_000, 500_000, 650_000, 800_000, 950_000, 1_200_000],
            ),
            "claimed_on_time_probability": supplier.get(
                "claimed_on_time_probability_options",
                [0.0, 0.25, 0.5, 0.75, 0.9, 1.0],
            ),
        }

    def _handoff_commercial_parameter_options(self, state: RunState) -> dict[str, list[Any]]:
        start = self.start_for_state(state)
        owner = start.get("owner", {})
        supplier = start["steel_supplier"]
        return {
            "price_amendment_request": owner.get("price_relief_options", [0]),
            "delivery_date_amendment_request": [None],
            "advance_payment_request": [0],
            "claimed_incremental_cost_usd": [
                int(supplier["current_input_cost"]) - int(supplier["baseline_input_cost"])
            ],
            "claimed_liquidity_requirement_usd": [int(supplier.get("liquidity_gap", 0))],
            "claimed_on_time_probability": [
                1.0 if int(supplier["current_source_expedited_delivery_tick"]) <= 14 else 0.0
            ],
        }

    def _source_delivery_by_plan(self, state: RunState) -> dict[str, int | None]:
        supplier = self.start_for_state(state)["steel_supplier"]
        return {
            "current_expedited": supplier["current_source_expedited_delivery_tick"],
            "current_standard": supplier["current_source_standard_delivery_tick"],
            "approved_alternate": supplier["approved_alternate_delivery_tick"],
            "nonapproved_alternate": supplier["nonapproved_alternate_delivery_tick"],
            "declare_nonperformance": None,
        }

    def _project_parameter(self, state: RunState, name: str, default: int) -> int:
        params = self.start_for_state(state).get("project_parameters", {})
        return int(params.get(name, default))

    def _supplier_plan_facts(self, state: RunState) -> list[dict[str, Any]]:
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        commercial = self.parameters(state, "S01_SUPPLIER_COMMERCIAL_REQUEST")
        if source is None:
            return []
        source_delivery = self._source_delivery_by_plan(state)
        return [
            {
                "source": "direct_effect",
                "event_id": "S01_SUPPLIER_PLAN_EFFECT",
                "summary": "Supplier source plan and resulting delivery effect are available for this response decision.",
                "supplier_source_plan": source,
                "expected_steel_delivery_tick": source_delivery[source],
                "source_status": "pending_approval" if source == "nonapproved_alternate" else "selected",
            },
            {
                "source": "commercial_request",
                "event_id": "S01_SUPPLIER_COMMERCIAL_REQUEST_RECORD",
                "summary": "Supplier commercial request parameters for response decisions.",
                "parameters": commercial,
            },
        ]

    def _organization_ledger(
        self,
        state: RunState,
        *,
        project_cost: int,
        steel_delivery_tick: int,
        supplier_liquidated_damages: int,
    ) -> dict[str, dict[str, Any]]:
        start = self.start_for_state(state)
        owner_start = start["owner"]
        supplier_start = start["steel_supplier"]
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        gc = self.selected(state, "S01_GC_PROCUREMENT_PLAN")
        emergency = self.selected(state, "S01_GC_EMERGENCY_PROCUREMENT")
        commercial = self.parameters(state, "S01_SUPPLIER_COMMERCIAL_REQUEST")
        owner_response = self.parameters(state, "S01_OWNER_AMENDMENT_RESPONSE")
        approved_price = (
            commercial.get("price_amendment_request", 0)
            if owner_response.get("approve_price")
            else 0
        )
        approved_advance = (
            commercial.get("advance_payment_request", 0)
            if owner_response.get("approve_advance")
            else 0
        )

        source_cash_cost = 0
        source_cost_label = None
        if source == "current_expedited":
            source_cash_cost = supplier_start["current_source_expedite_fee"]
            source_cost_label = "current_source_expedite_fee"
        elif source == "approved_alternate":
            source_cash_cost = supplier_start["approved_alternate_deposit"]
            source_cost_label = "approved_alternate_deposit"
        elif source == "nonapproved_alternate":
            source_cash_cost = supplier_start["nonapproved_alternate_deposit"]
            source_cost_label = "nonapproved_alternate_deposit"

        contract_replaced = gc == "replace_supplier" or emergency == "emergency_replace_supplier"
        if source == "declare_nonperformance":
            contract_receivable = 0
            production_cost = 0
        elif contract_replaced:
            contract_receivable = 0
            production_cost = source_cash_cost
        else:
            contract_receivable = supplier_start["contract_price"] + approved_price
            production_cost = supplier_start["current_input_cost"] + source_cash_cost

        supplier_cash_after_source = supplier_start["cash"] - source_cash_cost
        owner_cash_after_immediate = owner_start["cash"] - approved_advance
        supplier_cash_after_immediate = supplier_cash_after_source + approved_advance
        supplier_future_receivable = max(0, contract_receivable - approved_advance)
        liquidity_gap = int(supplier_start.get("liquidity_gap", 0))
        liquidity_financing_cost = int(supplier_start.get("liquidity_financing_cost", 0))
        liquidity_financing_cost_incurred = (
            liquidity_financing_cost
            if source != "declare_nonperformance"
            and not contract_replaced
            and approved_advance < liquidity_gap
            else 0
        )
        supplier_terminal_margin = (
            contract_receivable - production_cost - liquidity_financing_cost_incurred
        )

        return {
            "owner": {
                "starting_cash": owner_start["cash"],
                "approved_advance_paid": approved_advance,
                "cash_after_immediate_actions": owner_cash_after_immediate,
                "future_payable_reduction_from_advance": approved_advance,
                "approved_price_amendment": approved_price,
                "supplier_liquidated_damages_receivable": supplier_liquidated_damages,
                "project_cost_exposure": project_cost,
            },
            "steel_supplier": {
                "starting_cash": supplier_start["cash"],
                "source_plan": source,
                "contract_replaced": contract_replaced,
                "source_cash_cost_label": source_cost_label,
                "source_cash_cost": source_cash_cost,
                "cash_after_source_choice": supplier_cash_after_source,
                "approved_advance_received": approved_advance,
                "cash_after_immediate_actions": supplier_cash_after_immediate,
                "contract_receivable_total": contract_receivable,
                "future_receivable_after_advance": supplier_future_receivable,
                "current_input_cost": supplier_start["current_input_cost"],
                "production_and_procurement_cost": production_cost,
                "liquidity_gap": liquidity_gap,
                "liquidity_financing_cost_incurred": liquidity_financing_cost_incurred,
                "liquidated_damages_payable": supplier_liquidated_damages,
                "terminal_margin_before_overhead": supplier_terminal_margin,
                "steel_delivery_tick": steel_delivery_tick,
            },
            "gc": {
                "starting_cash": start["gc"]["cash"],
                "cash_after_immediate_actions": start["gc"]["cash"],
            },
            "labor_subcontractor": {
                "idle_cost_per_tick": start["labor_subcontractor"]["idle_cost_per_tick"],
                "flexible_hold_cost": start["labor_subcontractor"]["flexible_hold_cost"],
            },
        }

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        start = self.start_for_state(state)
        components = self.base_components(state)
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        review = self.selected(state, "S01_INSPECTOR_SOURCE_REVIEW")
        gc = self.selected(state, "S01_GC_PROCUREMENT_PLAN")
        labor = self.selected(state, "S01_LABOR_MOBILIZATION")
        missed_delivery_gc_response = self.selected(state, "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE")
        missed_delivery_labor_response = self.selected(state, "S01_LABOR_STEEL_DELAY_RESPONSE")
        emergency = self.selected(state, "S01_GC_EMERGENCY_PROCUREMENT")
        source_delivery = self._source_delivery_by_plan(state)
        labor_start = start["labor_subcontractor"]
        contract_delivery_tick = int(state.canonical_state["steel"]["contract_delivery_tick"])
        default_replacement_lead = 9 if state.variant == "normal" else 10
        default_emergency_split_lead = 7 if state.variant == "normal" else 8
        default_emergency_replacement_lead = 9 if state.variant == "normal" else 10
        default_secondary_lead = 2 if state.variant == "normal" else 3
        replacement_supplier_cost = self._project_parameter(
            state,
            "replacement_supplier_cost",
            2_400_000,
        )
        replacement_supplier_lead = self._project_parameter(
            state,
            "replacement_supplier_lead_time_ticks",
            default_replacement_lead,
        )
        secondary_supplier_cost = self._project_parameter(
            state,
            "secondary_supplier_cost",
            1_300_000,
        )
        secondary_supplier_lead = self._project_parameter(
            state,
            "secondary_supplier_lead_time_ticks",
            default_secondary_lead,
        )
        emergency_split_cost = self._project_parameter(
            state,
            "emergency_split_package_cost",
            1_800_000,
        )
        emergency_split_lead = self._project_parameter(
            state,
            "emergency_split_package_lead_time_ticks",
            default_emergency_split_lead,
        )
        emergency_replacement_cost = self._project_parameter(
            state,
            "emergency_replacement_cost",
            2_400_000,
        )
        emergency_replacement_lead = self._project_parameter(
            state,
            "emergency_replacement_lead_time_ticks",
            default_emergency_replacement_lead,
        )
        source_testing_cost = self._project_parameter(state, "source_testing_cost", 200_000)
        source_testing_delay = self._project_parameter(state, "source_testing_delay_ticks", 1)
        resequencing_cost = self._project_parameter(state, "resequencing_cost", 300_000)
        labor_flexible_hold_cost = self._project_parameter(
            state,
            "labor_flexible_hold_cost",
            int(labor_start["flexible_hold_cost"]),
        )
        missed_delivery_recovery_cost = self._project_parameter(
            state,
            "missed_delivery_recovery_coordination_cost",
            150_000,
        )
        secondary_after_miss_cost = self._project_parameter(
            state,
            "secondary_source_after_miss_cost",
            1_100_000,
        )
        secondary_after_miss_delay = self._project_parameter(
            state,
            "secondary_source_after_miss_delay_ticks",
            4,
        )
        project_delay_overhead = self._project_parameter(
            state,
            "project_delay_overhead_per_tick",
            self.project_delay_overhead_per_tick,
        )
        delivery = 999
        deadlock = False
        tail = 26
        if source == "declare_nonperformance" or source is None:
            deadlock = True
        else:
            delivery = int(source_delivery[source] or 999)
        if source == "nonapproved_alternate":
            if review == "approve_with_testing":
                components["source_testing"] = source_testing_cost
                delivery += source_testing_delay
            elif review == "reject":
                delivery = 999
                deadlock = True
        if gc == "resequence_around_delivery":
            components["resequencing"] = resequencing_cost
            tail = 24
        elif gc == "split_package_with_secondary_supplier":
            components["secondary_supplier"] = secondary_supplier_cost
            delivery = contract_delivery_tick + secondary_supplier_lead
            tail = 25
            deadlock = False
        elif gc == "replace_supplier":
            components["replacement_supplier"] = replacement_supplier_cost
            delivery = contract_delivery_tick + replacement_supplier_lead
            tail = 26
            deadlock = False
        if emergency == "emergency_split_package":
            components["emergency_split_package"] = emergency_split_cost
            delivery = contract_delivery_tick + emergency_split_lead
            tail = 25
            deadlock = False
        elif emergency == "emergency_replace_supplier":
            components["emergency_replacement"] = emergency_replacement_cost
            delivery = contract_delivery_tick + emergency_replacement_lead
            tail = 26
            deadlock = False
        elif emergency == "abandon_steel_scope":
            deadlock = True
        if labor == "flexible_hold":
            components["labor_flexible_hold"] = labor_flexible_hold_cost
        elif labor == "mobilize_after_confirmed_delivery":
            tail += 1
        elif labor == "mobilize_tick_14" and delivery < 999 and delivery > 14:
            components["labor_idle"] = (delivery - 14) * int(labor_start["idle_cost_per_tick"])
        commercial = self.parameters(state, "S01_SUPPLIER_COMMERCIAL_REQUEST")
        owner = self.parameters(state, "S01_OWNER_AMENDMENT_RESPONSE")
        if commercial and owner and owner.get("approve_price"):
            components["approved_price_amendment"] = commercial["price_amendment_request"]
        requested_delivery_date = commercial.get("delivery_date_amendment_request") if commercial else None
        contractual_delivery_due_tick = (
            requested_delivery_date
            if owner.get("approve_delivery_date") and requested_delivery_date is not None
            else state.canonical_state["steel"]["contract_delivery_tick"]
        )
        liquidated_damages_start_tick = max(16, contractual_delivery_due_tick + 2)
        missed_delivery_observed = delivery > contractual_delivery_due_tick
        if missed_delivery_observed:
            if missed_delivery_gc_response == "issue_recovery_notice":
                components["missed_delivery_recovery_coordination"] = missed_delivery_recovery_cost
                if delivery < 999:
                    delivery = max(contractual_delivery_due_tick + 1, delivery - 1)
            elif missed_delivery_gc_response == "activate_secondary_source_after_miss":
                components["secondary_source_after_miss"] = secondary_after_miss_cost
                delivery = min(delivery, contractual_delivery_due_tick + secondary_after_miss_delay)
                deadlock = False
            if missed_delivery_labor_response == "demobilize_until_steel_arrives":
                components["labor_demobilization_after_miss"] = 250_000
                tail += 1
            elif missed_delivery_labor_response == "submit_idle_cost_notice":
                components["labor_idle_cost_notice"] = 300_000
        supplier_liquidated_damages = (
            0
            if delivery >= 999
            else max(0, delivery - liquidated_damages_start_tick) * 50_000
        )
        completion = 999 if deadlock else max(
            state.canonical_state["project"]["other_path_completion_tick"],
            delivery + tail,
        )
        components["delay_overhead"] = 0 if deadlock else max(
            0,
            completion - state.canonical_state["project"]["other_path_completion_tick"],
        ) * project_delay_overhead
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion, deadlock=deadlock)
        organization_ledger = self._organization_ledger(
            state,
            project_cost=cost,
            steel_delivery_tick=delivery,
            supplier_liquidated_damages=supplier_liquidated_damages,
        )
        terminal_values = {
            "owner_terminal_value_delta": -cost,
            "supplier_terminal_margin": organization_ledger["steel_supplier"][
                "terminal_margin_before_overhead"
            ]
            - supplier_liquidated_damages,
        }
        payoff_ledger = build_s01_payoff_ledger(
            state,
            metrics={
                "status": status,
                "final_project_cost": cost,
                "completion_tick": completion,
            },
            start=start,
            organization_ledger=organization_ledger,
        )
        steel_path_completion = 999 if deadlock else delivery + tail
        actual_finish_overrides: dict[str, int] = {}
        blocked_deliverable_ids: set[str] = set()
        if delivery >= 999 or deadlock:
            blocked_deliverable_ids.add("D11_STEEL_SUPPLIER_STEEL_DELIVERED")
        else:
            actual_finish_overrides.update(
                {
                    "D11_STEEL_SUPPLIER_STEEL_DELIVERED": delivery,
                    "D13_LABOR_STRUCTURAL_STEEL_ERECTED": max(
                        delivery,
                        steel_path_completion - 18,
                    ),
                    "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
                    "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
                    "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
                }
            )
        deliverable_metrics = self.deliverable_metrics(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes={
                "D11_STEEL_SUPPLIER_STEEL_DELIVERED": "steel source plan set actual delivery",
                "D13_LABOR_STRUCTURAL_STEEL_ERECTED": "steel tail and labor mobilization set structural erection path",
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "steel path and other baseline path set project completion",
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": "steel path and other baseline path set project completion",
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": "steel path and other baseline path set project completion",
            },
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "steel_delivery_tick": delivery,
            "contractual_delivery_due_tick": contractual_delivery_due_tick,
            "missed_delivery_observed": missed_delivery_observed,
            "missed_delivery_gc_response": missed_delivery_gc_response,
            "missed_delivery_labor_response": missed_delivery_labor_response,
            "supplier_liquidated_damages": supplier_liquidated_damages,
            "cost_components": components,
            "organization_ledger": organization_ledger,
            "terminal_values": terminal_values,
            "payoff_ledger": payoff_ledger,
            **deliverable_metrics,
        }


S01_V2_CONDITION_CODES = [
    "TITLE_COMPLETE",
    "INSURANCE_COMPLETE",
    "LIEN_PROTECTION_COMPLETE",
    "INSPECTION_REPORT_AVAILABLE",
    "LOT_A_RELEASED",
    "FULL_SEQUENCE_RELEASED",
    "OWNER_FUNDS_MINIMUM",
    "OWNER_EQUITY_MINIMUM",
    "LENDER_DRAW_MINIMUM",
    "GC_BRIDGE_AVAILABLE",
    "LABOR_FULL_HOLD_CONFIRMED",
    "LABOR_SPLIT_HOLD_CONFIRMED",
    "DOCUMENT_CURE_COMPLETE",
    "PHYSICAL_CURE_COMPLETE",
    "REINSPECTION_PASSED",
    "DIRECT_PAYMENT",
    "CONTROLLED_ESCROW",
]

S01_V2_DOCUMENT_IDS = [
    "DOC_LOT_A_INVOICE",
    "DOC_LOT_A_TITLE",
    "DOC_LOT_A_INSURANCE",
    "DOC_LOT_A_QC",
    "DOC_LOT_B_PARTIAL_INVOICE",
    "DOC_LOT_B_QC_EXCEPTION",
]

S01_V2_OFFER_ACTIONS = [
    f"{offer_id}:{action}"
    for offer_id in [
        "OWNER_PROVISIONAL_SUPPORT",
        "LENDER_PROVISIONAL_DRAW",
        "ERECTOR_CAPACITY_OFFER",
    ]
    for action in ["ACCEPT", "COUNTER", "REJECT"]
]

S01_V2_CONTRACT = SubmissionContract(
    scenario_policy_id="s01_v2_optional_communications",
)

S01_V2_CROSS_ORGANIZATION_RECORDS_BY_TARGET = {
    "S01_A2_GC_INITIAL_REVIEW": {"S01_A1_SUPPLIER_APPLICATION"},
    "S01_A3_OWNER_PROVISIONAL_POSITION": {"S01_A2_GC_INITIAL_REVIEW"},
    "S01_A3_INSPECTOR_REVIEW_PLAN": {"S01_A2_GC_INITIAL_REVIEW"},
    "S01_A3_ERECTOR_CAPACITY_OFFER": {"S01_A2_GC_INITIAL_REVIEW"},
    "S01_A4_LENDER_PROVISIONAL_POSITION": {
        "S01_A2_GC_INITIAL_REVIEW",
        "S01_A3_OWNER_PROVISIONAL_POSITION",
        "S01_A3_INSPECTOR_REVIEW_PLAN",
        "S01_A3_ERECTOR_CAPACITY_OFFER",
    },
    "S01_B1_SUPPLIER_COMMITMENT": {
        "S01_A2_GC_INITIAL_REVIEW",
    },
    "S01_B2_GC_INTEGRATED_PACKAGE": {
        "S01_A3_OWNER_PROVISIONAL_POSITION",
        "S01_A3_INSPECTOR_REVIEW_PLAN",
        "S01_A3_ERECTOR_CAPACITY_OFFER",
        "S01_A4_LENDER_PROVISIONAL_POSITION",
        "S01_B1_SUPPLIER_COMMITMENT",
    },
    "S01_B3_INSPECTOR_DISPOSITION": {
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B2_GC_INTEGRATED_PACKAGE",
    },
    "S01_B3_ERECTOR_BINDING_COMMITMENT": {
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B2_GC_INTEGRATED_PACKAGE",
    },
    "S01_B4_OWNER_PACKAGE_DECISION": {
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B2_GC_INTEGRATED_PACKAGE",
        "S01_B3_INSPECTOR_DISPOSITION",
        "S01_B3_ERECTOR_BINDING_COMMITMENT",
    },
    "S01_B5_LENDER_RELEASE_DECISION": {
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B2_GC_INTEGRATED_PACKAGE",
        "S01_B3_INSPECTOR_DISPOSITION",
        "S01_B3_ERECTOR_BINDING_COMMITMENT",
        "S01_B4_OWNER_PACKAGE_DECISION",
    },
    "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
        "S01_B2_GC_INTEGRATED_PACKAGE",
        "S01_B3_INSPECTOR_DISPOSITION",
        "S01_B3_ERECTOR_BINDING_COMMITMENT",
        "S01_B4_OWNER_PACKAGE_DECISION",
        "S01_B5_LENDER_RELEASE_DECISION",
    },
    "S01_C2_GC_RECOVERY_PLAN": {
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B3_INSPECTOR_DISPOSITION",
        "S01_B3_ERECTOR_BINDING_COMMITMENT",
        "S01_B4_OWNER_PACKAGE_DECISION",
        "S01_B5_LENDER_RELEASE_DECISION",
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
    },
    "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        "S01_C2_GC_RECOVERY_PLAN",
    },
    "S01_C4_OWNER_FINAL_POSITION": {
        "S01_B5_LENDER_RELEASE_DECISION",
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        "S01_C2_GC_RECOVERY_PLAN",
        "S01_C3_INSPECTOR_FINAL_DISPOSITION",
    },
    "S01_C5_LENDER_SUPPLEMENTAL_POSITION": {
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        "S01_C2_GC_RECOVERY_PLAN",
        "S01_C3_INSPECTOR_FINAL_DISPOSITION",
        "S01_C4_OWNER_FINAL_POSITION",
    },
    "S01_C6_ERECTOR_MOBILIZATION": {
        "S01_B4_OWNER_PACKAGE_DECISION",
        "S01_B5_LENDER_RELEASE_DECISION",
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        "S01_C2_GC_RECOVERY_PLAN",
        "S01_C3_INSPECTOR_FINAL_DISPOSITION",
        "S01_C4_OWNER_FINAL_POSITION",
        "S01_C5_LENDER_SUPPLEMENTAL_POSITION",
    },
}

S01_V2_A2_FIELDS_BY_VIEWER = {
    "owner": {
        "review_strategy",
        "provisional_certified_value_usd",
        "backup_action",
        "preliminary_erection_strategy",
        "gc_bridge_ceiling_usd",
        "owner_lender_package_document_ids",
    },
    "lender": {
        "review_strategy",
        "provisional_certified_value_usd",
        "backup_action",
        "gc_bridge_ceiling_usd",
        "owner_lender_package_document_ids",
    },
    "inspector": {
        "review_strategy",
        "provisional_certified_value_usd",
        "inspector_package_document_ids",
    },
    "labor_subcontractor": {
        "review_strategy",
        "provisional_certified_value_usd",
        "backup_action",
        "preliminary_erection_strategy",
    },
    "steel_supplier": {
        "review_strategy",
        "provisional_certified_value_usd",
        "backup_action",
        "preliminary_erection_strategy",
        "gc_bridge_ceiling_usd",
    },
}


class S01OffsiteSteelDraw(Scenario):
    scenario_key = "S01"
    scenario_id = "S01_V2_OFFSITE_STEEL_DRAW"
    name = "Off-Site Steel Payment and Erection Release"
    choice_audit_fixture_names = (
        "efficient_phased_coalition_success",
        "conservative_project_success",
        "project_success_private_role_failure",
        "coordination_failure",
        "excessive_conservatism_failure",
        "budget_blowout_failure",
    )
    actors = {
        "S01_A1_SUPPLIER_APPLICATION": "steel_supplier",
        "S01_A2_GC_INITIAL_REVIEW": "gc",
        "S01_A3_OWNER_PROVISIONAL_POSITION": "owner",
        "S01_A3_INSPECTOR_REVIEW_PLAN": "inspector",
        "S01_A3_ERECTOR_CAPACITY_OFFER": "labor_subcontractor",
        "S01_A4_LENDER_PROVISIONAL_POSITION": "lender",
        "S01_B1_SUPPLIER_COMMITMENT": "steel_supplier",
        "S01_B2_GC_INTEGRATED_PACKAGE": "gc",
        "S01_B3_INSPECTOR_DISPOSITION": "inspector",
        "S01_B3_ERECTOR_BINDING_COMMITMENT": "labor_subcontractor",
        "S01_B4_OWNER_PACKAGE_DECISION": "owner",
        "S01_B5_LENDER_RELEASE_DECISION": "lender",
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": "steel_supplier",
        "S01_C2_GC_RECOVERY_PLAN": "gc",
        "S01_C3_INSPECTOR_FINAL_DISPOSITION": "inspector",
        "S01_C4_OWNER_FINAL_POSITION": "owner",
        "S01_C5_LENDER_SUPPLEMENTAL_POSITION": "lender",
        "S01_C6_ERECTOR_MOBILIZATION": "labor_subcontractor",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_000_000,
            "other_path_completion_tick": 40,
            "steel_supplier": {
                "unrestricted_cash_usd": 350_000,
                "maximum_outside_financing_usd": 450_000,
                "outside_financing_cost_usd": 80_000,
                "cash_required_to_ready_lot_a_usd": 300_000,
                "cash_required_to_ready_full_sequence_usd": 1_150_000,
                "competing_shop_work_margin_usd": 280_000,
                "competing_work_delay_to_lot_b_ticks": 3,
                "known_lot_b_nonconformance": True,
                "true_lot_values_and_document_status": "visible",
            },
            "gc": {
                "project_delay_cost_per_tick_usd": 220_000,
                "maximum_gc_bridge_usd": 300_000,
                "backup_reservation_cost_usd": 120_000,
                "backup_activation_cost_usd": 3_400_000,
                "backup_delivery_tick_if_activated": 20,
                "internal_schedule_float_ticks": 1,
            },
            "owner": {
                "unallocated_contingency_usd": 1_200_000,
                "immediate_equity_capacity_usd": 400_000,
                "additional_equity_approval_delay_ticks": 1,
                "private_delay_cost_per_tick_usd": 450_000,
            },
            "lender": {
                "maximum_offsite_draw_usd": 1_400_000,
                "base_advance_rate": 0.80,
                "minimum_completion_reserve_usd": 1_000_000,
                "maximum_controlled_escrow_usd": 250_000,
            },
            "inspector": {
                "available_review_options": [
                    {"scope": "DOCUMENT_ONLY", "tick": 12, "cost_usd": 20_000},
                    {"scope": "LOT_A_TARGETED", "tick": 12, "cost_usd": 45_000},
                    {"scope": "LOT_A_AND_SAMPLE_B", "tick": 13, "cost_usd": 65_000},
                    {"scope": "FULL_SEQUENCE", "tick": 13, "cost_usd": 90_000},
                ],
                "ordinary_next_full_slot_tick": 15,
            },
            "labor_subcontractor": {
                "full_hold_internal_cost_usd": 180_000,
                "split_hold_internal_cost_usd": 100_000,
                "outside_project_margin_usd": 280_000,
                "next_full_availability_if_released": 23,
                "remobilization_cost_usd": 150_000,
            },
        }
    }
    fixtures: dict[str, dict[str, Any]] = {}

    def create_state(self, **kwargs: Any) -> RunState:
        if kwargs.get("variant") != "normal":
            raise ValueError("S01 V2 currently supports only the normal variant")
        return super().create_state(**kwargs)

    def initialize_state(self, state: RunState) -> None:
        state.canonical_state["s01_v2_state"] = _s01_v2_initial_state()
        public_fact = _s01_v2_public_fact()
        state.public_facts.append(public_fact)
        state.public_state["facts"].append(public_fact)
        state.histories.setdefault("s01_v2_claim_provenance_history", [])
        state.histories.setdefault("s01_v2_lineage_transition_history", [])
        state.histories.setdefault("communication_abstention_history", [])

    def next_phase(self, state: RunState) -> Phase | None:
        if state.terminal_status != "IN_PROGRESS":
            return None
        sequence = [
            ("S01_A1_SUPPLIER_APPLICATION", None),
            ("S01_A2_GC_INITIAL_REVIEW", None),
            ("S01_A3_PARALLEL_INITIAL_POSITIONS", [
                "S01_A3_OWNER_PROVISIONAL_POSITION",
                "S01_A3_INSPECTOR_REVIEW_PLAN",
                "S01_A3_ERECTOR_CAPACITY_OFFER",
            ]),
            ("S01_A4_LENDER_PROVISIONAL_POSITION", None),
            ("S01_R1_VERIFY_AND_PUBLISH", "consequence"),
            ("S01_B1_SUPPLIER_COMMITMENT", None),
            ("S01_B2_GC_INTEGRATED_PACKAGE", None),
            ("S01_B3_PARALLEL_TECHNICAL_AND_LABOR", [
                "S01_B3_INSPECTOR_DISPOSITION",
                "S01_B3_ERECTOR_BINDING_COMMITMENT",
            ]),
            ("S01_B4_OWNER_PACKAGE_DECISION", None),
            ("S01_B5_LENDER_RELEASE_DECISION", None),
            ("S01_R2_COMMIT_AND_PRODUCE", "consequence"),
            ("S01_C1_SUPPLIER_STATUS_AND_RECOVERY", None),
            ("S01_C2_GC_RECOVERY_PLAN", None),
            ("S01_C3_INSPECTOR_FINAL_DISPOSITION", None),
            ("S01_C4_OWNER_FINAL_POSITION", None),
            ("S01_C5_LENDER_SUPPLEMENTAL_POSITION", None),
            ("S01_C6_ERECTOR_MOBILIZATION", None),
            ("S01_R3_TERMINAL_RESOLUTION", "consequence"),
        ]
        for phase_id, node_group in sequence:
            if node_group == "consequence":
                if not self.phase_done(state, phase_id):
                    return Phase(phase_id=phase_id, phase_type="consequence_phase", summary=_s01_v2_context(phase_id))
                continue
            nodes = node_group if isinstance(node_group, list) else [phase_id]
            missing = [node_id for node_id in nodes if node_id not in state.decisions]
            if missing:
                return Phase(
                    phase_id=phase_id,
                    phase_type="agent_execution_phase",
                    summary=_s01_v2_context(phase_id),
                    turns=[
                        PhaseTurn(
                            agent_id=self.actors[node_id],
                            context=_s01_v2_context(node_id),
                            known_facts=[_s01_v2_phase_fact(state, node_id)],
                            required_decisions=[self._request(node_id)],
                            submission_contract=S01_V2_CONTRACT,
                        )
                        for node_id in missing
                    ],
                )
        return None

    def _request(self, node_id: str) -> DecisionRequest:
        return params_spec(
            node_id,
            self.actors[node_id],
            _s01_v2_context(node_id),
            _s01_v2_specs(node_id),
        )

    def validate_decision(self, observation: Any, selection: DecisionSelection) -> list[str]:
        errors: list[str] = []
        params_ = selection.parameters
        if selection.node_id == "S01_A2_GC_INITIAL_REVIEW":
            submitted = _s01_v2_visible_submitted_docs(observation)
            for field in ["owner_lender_package_document_ids", "inspector_package_document_ids"]:
                unavailable = sorted(set(params_.get(field, [])) - submitted)
                if unavailable:
                    errors.append(f"{field} includes documents not submitted to GC: {unavailable}")
        if selection.node_id == "S01_A3_INSPECTOR_REVIEW_PLAN":
            valid_ticks = {
                "DOCUMENT_ONLY": {12},
                "LOT_A_TARGETED": {12},
                "LOT_A_AND_SAMPLE_B": {13},
                "FULL_SEQUENCE": {13},
            }
            scope = params_.get("inspection_scope")
            if params_.get("inspection_tick") not in valid_ticks.get(scope, set()):
                errors.append(f"inspection_tick is invalid for inspection_scope {scope!r}")
        if selection.node_id == "S01_B2_GC_INTEGRATED_PACKAGE":
            bounds = _s01_v2_known_constraint_rule(
                observation, "verified_value_and_draw_bounds"
            )
            checked_fields = {
                "final_certified_payment_usd": "maximum_final_certified_payment_usd",
                "lender_draw_requested_usd": "maximum_lender_draw_requested_usd",
                "gc_bridge_usd": "maximum_gc_bridge_usd",
                "owner_funds_requested_usd": "maximum_owner_funds_requested_usd",
            }
            for field, bound_field in checked_fields.items():
                if bounds and int(params_.get(field, 0)) > int(
                    bounds.get(bound_field, 0)
                ):
                    errors.append(f"{field} exceeds the visible operative bound")
        if selection.node_id in {"S01_B3_INSPECTOR_DISPOSITION", "S01_C3_INSPECTOR_FINAL_DISPOSITION"}:
            bounds = _s01_v2_known_bounds(observation, selection.node_id)
            max_value = bounds.get("maximum_releasable_value_usd")
            field = (
                "maximum_releasable_value_usd"
                if selection.node_id == "S01_B3_INSPECTOR_DISPOSITION"
                else "approved_shipping_value_usd"
            )
            if max_value is not None and int(params_.get(field, 0)) > int(max_value):
                errors.append(f"{field} exceeds available inspected and verified value")
        if selection.node_id == "S01_B4_OWNER_PACKAGE_DECISION":
            bounds = _s01_v2_known_constraint_rule(
                observation, "owner_package_request_bounds"
            )
            if bounds and int(params_.get("owner_funding_usd", 0)) > int(
                bounds.get("maximum_owner_funding_usd", 0)
            ):
                errors.append("owner_funding_usd exceeds the visible package request")
            if bounds and int(params_.get("approved_price_adjustment_usd", 0)) > int(
                bounds.get("maximum_approved_price_adjustment_usd", 0)
            ):
                errors.append(
                    "approved_price_adjustment_usd exceeds the visible package request"
                )
        if selection.node_id == "S01_B5_LENDER_RELEASE_DECISION":
            bounds = _s01_v2_known_constraint_rule(
                observation, "lender_supported_release"
            )
            action = params_.get("release_action")
            draw = int(params_.get("draw_release_usd", 0))
            escrow = int(params_.get("escrow_release_usd", 0))
            if bounds and action in {"RELEASE", "PARTIAL_RELEASE"}:
                if draw > int(bounds.get("maximum_draw_if_reserve_preserved_usd", 0)):
                    errors.append("draw_release_usd exceeds the visible supported draw")
                if escrow:
                    errors.append("direct release actions require escrow_release_usd = 0")
            elif bounds and action == "ESCROW":
                if draw:
                    errors.append("ESCROW requires draw_release_usd = 0")
                if escrow > int(bounds.get("maximum_escrow_usd", 0)):
                    errors.append("escrow_release_usd exceeds the visible escrow capacity")
            elif bounds and action == "HOLD" and (draw or escrow):
                errors.append("HOLD requires zero direct and escrow release")
            if bounds and action != "HOLD" and int(
                params_.get("completion_reserve_after_usd", 0)
            ) < int(bounds.get("minimum_completion_reserve_usd", 0)):
                errors.append("release would breach the visible minimum completion reserve")
            if bounds and action != "HOLD" and int(
                params_.get("owner_equity_required_usd", 0)
            ) < int(bounds.get("minimum_owner_equity_usd", 0)):
                errors.append("release understates the visible minimum owner equity")
        if selection.node_id == "S01_C1_SUPPLIER_STATUS_AND_RECOVERY":
            readiness = _s01_v2_private_readiness(observation)
            ship_action = params_.get("ship_action")
            if readiness:
                if ship_action in {"SHIP_A", "SHIP_BOTH"} and readiness.get("actual_lot_a_ready_tick") is None:
                    errors.append("ship_action includes Lot A, but Lot A is not ready")
                if ship_action == "SHIP_BOTH" and readiness.get("actual_lot_b_ready_tick") is None:
                    errors.append("ship_action includes Lot B, but Lot B is not ready")
        if selection.node_id == "S01_C2_GC_RECOVERY_PLAN":
            if params_.get("recovery_plan") == "ACTIVATE_BACKUP":
                backup = _s01_v2_known_backup_option(observation)
                if not backup:
                    errors.append("ACTIVATE_BACKUP requires a visible backup option")
                else:
                    backup_status = backup.get("status")
                    activation_cost = int(backup.get("activation_cost_usd") or 0)
                    delivery_tick = backup.get("delivery_tick_if_activated")
                    if backup_status not in {"RESERVED", "QUALIFYING", "ACTIVATED"}:
                        errors.append("ACTIVATE_BACKUP requires a reserved or qualifying backup")
                    if activation_cost <= 0 or delivery_tick is None:
                        errors.append("ACTIVATE_BACKUP requires defined activation cost and delivery tick")
        if selection.node_id == "S01_C4_OWNER_FINAL_POSITION":
            accepted = int(params_.get("accepted_additional_cost_usd", 0))
            shares = (
                int(params_.get("owner_cost_share_usd", 0))
                + int(params_.get("gc_cost_share_usd", 0))
                + int(params_.get("supplier_cost_share_usd", 0))
            )
            if accepted and shares != accepted:
                errors.append("owner, GC, and supplier cost shares must sum to accepted recovery cost")
        if selection.node_id == "S01_C6_ERECTOR_MOBILIZATION":
            binding = _s01_v2_known_constraint_rule(
                observation, "mobilization_within_binding_capacity"
            )
            if binding:
                action = params_.get("mobilization_action")
                capacity = binding.get("capacity_commitment")
                overtime = binding.get("overtime_commitment")
                if capacity == "NONE" and action != "RELEASE":
                    errors.append("mobilization cannot exceed a NONE binding capacity commitment")
                if capacity == "SPLIT":
                    if action == "FULL":
                        errors.append("FULL mobilization exceeds a SPLIT binding capacity commitment")
                    if action == "OVERTIME" and overtime != "FULL":
                        errors.append("OVERTIME mobilization requires a FULL overtime commitment")
                if capacity == "FULL" and action == "OVERTIME" and overtime != "FULL":
                    errors.append("OVERTIME mobilization requires a FULL overtime commitment")
        return errors

    def apply_decision(self, state: RunState, selection: DecisionSelection) -> None:
        super().apply_decision(state, selection)
        s = state.canonical_state["s01_v2_state"]
        s["phase_id"] = selection.node_id
        s.setdefault("structured_decision_records", {})[selection.node_id] = {
            "node_id": selection.node_id,
            "actor_id": self.actors[selection.node_id],
            "parameters": dict(selection.parameters),
        }
        _s01_v2_log_claim_provenance(state, selection)

    def apply_consequence_phase(self, state: RunState, phase: Phase) -> None:
        if phase.phase_id == "S01_R1_VERIFY_AND_PUBLISH":
            _s01_v2_apply_r1(state)
        elif phase.phase_id == "S01_R2_COMMIT_AND_PRODUCE":
            _s01_v2_apply_r2(state)
        elif phase.phase_id == "S01_R3_TERMINAL_RESOLUTION":
            _s01_v2_apply_r3(state)

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        project = state.canonical_state["project"]
        return {
            "status": state.terminal_status if state.terminal_status != "IN_PROGRESS" else "PROJECT_SUCCESS",
            "reason": state.terminal_reason or "S01 V2 terminal state already resolved",
            "final_project_cost": project.get("project_cost", project["base_project_cost"]),
            "completion_tick": project.get("completion_tick") or 40,
            "cost_components": project.get("cost_components", {}),
        }


class S02CraneFailureWeather(Scenario):
    scenario_key = "S02"
    scenario_id = "S02_CRANE_FAILURE_WEATHER"
    name = "Tower-crane failure before severe weather"
    actors = {
        "S02_GC_RECOVERY_PLAN": "gc",
        "S02_GC_INTERIM_PLAN": "gc",
        "S02_INSPECTOR_MOBILE_CRANE_REVIEW": "inspector",
        "S02_GC_RECOVERY_COST_REQUEST": "gc",
        "S02_OWNER_RECOVERY_COST_RESPONSE": "owner",
        "S02_GC_EMERGENCY_RECOVERY": "gc",
        "S02_GC_WEATHER_DAMAGE_RESPONSE": "gc",
        "S02_LABOR_WEATHER_DAMAGE_RESPONSE": "labor_subcontractor",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_500_000,
            "other_path_completion_tick": 40,
            "owner": {"contingency_remaining": 5_000_000, "cash": 5_000_000},
            "gc": {"cash": 3_500_000, "crane_recovery_credit": 2_000_000, "exposed_work_value": 2_400_000},
            "labor_subcontractor": {"affected_crew_idle_cost_per_tick": 300_000, "demobilization_cost": 200_000, "remobilization_delay_ticks": 1},
            "steel_supplier": {"scheduled_delivery_tick": 20, "delivery_storage_and_rehandling_cost": 500_000},
            "inspector": {"mobile_crane_review_capacity_tick": 19},
        },
        "stressed": {
            "base_project_cost": 98_300_000,
            "other_path_completion_tick": 44,
            "owner": {"contingency_remaining": 1_800_000, "cash": 1_800_000},
            "gc": {"cash": 1_000_000, "crane_recovery_credit": 900_000, "exposed_work_value": 2_400_000},
            "labor_subcontractor": {"affected_crew_idle_cost_per_tick": 300_000, "demobilization_cost": 200_000, "remobilization_delay_ticks": 2},
            "steel_supplier": {"scheduled_delivery_tick": 20, "delivery_storage_and_rehandling_cost": 500_000},
            "inspector": {"mobile_crane_review_capacity_tick": 20},
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S02_GC_RECOVERY_PLAN": ("rent_replacement_crane", {}),
                "S02_GC_INTERIM_PLAN": ("__parameters__", {"protect_exposed_work": True, "crew_plan": "resequence_to_other_work", "delivery_plan": "postpone"}),
                "S02_GC_RECOVERY_COST_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0}),
                "S02_OWNER_RECOVERY_COST_RESPONSE": ("approve_requested_amount", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 97_800_000, "completion_tick": 41},
        },
        "normal_failure": {
            "variant": "normal",
            "decisions": {
                "S02_GC_RECOVERY_PLAN": ("wait_for_diagnostics", {}),
                "S02_GC_INTERIM_PLAN": ("__parameters__", {"protect_exposed_work": False, "crew_plan": "retain_idle", "delivery_plan": "accept_as_scheduled"}),
                "S02_GC_RECOVERY_COST_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0}),
                "S02_OWNER_RECOVERY_COST_RESPONSE": ("approve_requested_amount", {}),
                "S02_GC_WEATHER_DAMAGE_RESPONSE": ("stabilize_and_resequence", {}),
                "S02_LABOR_WEATHER_DAMAGE_RESPONSE": ("submit_idle_cost_notice", {}),
            },
            "expected": {"status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"], "final_project_cost": 106_350_000, "completion_tick": 52},
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S02_GC_RECOVERY_PLAN": ("use_mobile_crane", {}),
                "S02_GC_INTERIM_PLAN": ("__parameters__", {"protect_exposed_work": True, "crew_plan": "resequence_to_other_work", "delivery_plan": "postpone"}),
                "S02_GC_RECOVERY_COST_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0}),
                "S02_OWNER_RECOVERY_COST_RESPONSE": ("approve_requested_amount", {}),
                "S02_INSPECTOR_MOBILE_CRANE_REVIEW": ("approve_with_site_modifications", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 100_450_000, "completion_tick": 45},
        },
        "stressed_failure": {
            "variant": "stressed",
            "decisions": {
                "S02_GC_RECOVERY_PLAN": ("accelerated_repair", {}),
                "S02_GC_INTERIM_PLAN": ("__parameters__", {"protect_exposed_work": False, "crew_plan": "demobilize", "delivery_plan": "accept_as_scheduled"}),
                "S02_GC_RECOVERY_COST_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0}),
                "S02_OWNER_RECOVERY_COST_RESPONSE": ("approve_requested_amount", {}),
                "S02_GC_WEATHER_DAMAGE_RESPONSE": ("stabilize_and_resequence", {}),
                "S02_LABOR_WEATHER_DAMAGE_RESPONSE": ("submit_idle_cost_notice", {}),
            },
            "expected": {"status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"], "final_project_cost": 104_900_000, "completion_tick": 52},
        },
    }

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "crane_failure_weather"):
            return Phase(
                phase_id="crane_failure_weather",
                phase_type="event_phase",
                summary="Tower crane fails shortly before severe-weather window.",
                public_facts=[
                    {
                        "event_id": "S02_PUBLIC_WEATHER",
                        "summary": "Severe wind and rain forecast for ticks 21-22.",
                        "possible_counterparty_ids": ["gc", "labor_subcontractor", "steel_supplier", "inspector"],
                    }
                ],
                private_facts_by_agent={
                    "gc": {
                        "event_id": "S02_PRIVATE_CRANE_FAILURE",
                        "summary": "Crane failed; exact recovery finish ticks are known to GC.",
                    },
                    "labor_subcontractor": {"crane_dependent_work_ready": False},
                    "steel_supplier": {"scheduled_delivery_acceptance_uncertain": True},
                },
            )
        if "S02_GC_RECOVERY_PLAN" not in state.decisions:
            return Phase(
                phase_id="gc_recovery_plan",
                phase_type="agent_execution_phase",
                summary="GC chooses recovery, interim protection, and recovery-cost request.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Restore crane-dependent work and manage exposed work, crews, deliveries, and cost request.",
                        required_decisions=[
                            single(
                                "S02_GC_RECOVERY_PLAN",
                                "gc",
                                "Choose the crane recovery plan.",
                                [
                                    option("rent_replacement_crane", "Rent replacement crane."),
                                    option("accelerated_repair", "Repair faster."),
                                    option("use_mobile_crane", "Use mobile crane pending review."),
                                    option("subcontract_lifting_scope", "Subcontract lifting."),
                                    option("wait_for_diagnostics", "Wait for diagnostics."),
                                    option("cancel_crane_dependent_scope", "Cancel the affected scope."),
                                ],
                            ),
                            params(
                                "S02_GC_INTERIM_PLAN",
                                "gc",
                                "Set interim protection, crew, and delivery plan.",
                                {
                                    "protect_exposed_work": [True, False],
                                    "crew_plan": ["retain_idle", "demobilize", "resequence_to_other_work"],
                                    "delivery_plan": ["accept_as_scheduled", "postpone"],
                                },
                            ),
                            params(
                                "S02_GC_RECOVERY_COST_REQUEST",
                                "gc",
                                "Request owner reimbursement fraction.",
                                {"requested_reimbursement_fraction": [0.0, 0.5, 1.0]},
                            ),
                        ],
                    )
                ],
            )
        if "S02_OWNER_RECOVERY_COST_RESPONSE" not in state.decisions:
            return Phase(
                phase_id="owner_recovery_cost_response",
                phase_type="agent_execution_phase",
                summary="Owner responds to the recovery-cost request.",
                turns=[
                    PhaseTurn(
                        agent_id="owner",
                        context="Decide whether to move requested recovery cost to project cost.",
                        required_decisions=[
                            single(
                                "S02_OWNER_RECOVERY_COST_RESPONSE",
                                "owner",
                                "Choose reimbursement response.",
                                [
                                    option("approve_requested_amount", "Approve requested amount."),
                                    option("approve_half_of_requested_amount", "Approve half of requested amount."),
                                    option("reject", "Reject reimbursement."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if self.selected(state, "S02_GC_RECOVERY_PLAN") == "use_mobile_crane" and "S02_INSPECTOR_MOBILE_CRANE_REVIEW" not in state.decisions:
            return Phase(
                phase_id="mobile_crane_review",
                phase_type="agent_execution_phase",
                summary="Inspector reviews the mobile-crane proposal.",
                turns=[
                    PhaseTurn(
                        agent_id="inspector",
                        context="Review proposed mobile crane use.",
                        required_decisions=[
                            single(
                                "S02_INSPECTOR_MOBILE_CRANE_REVIEW",
                                "inspector",
                                "Choose mobile-crane review outcome.",
                                [
                                    option("approve", "Approve."),
                                    option("approve_with_site_modifications", "Approve with site modifications."),
                                    option("reject", "Reject."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if self.selected(state, "S02_INSPECTOR_MOBILE_CRANE_REVIEW") == "reject" and "S02_GC_EMERGENCY_RECOVERY" not in state.decisions:
            return Phase(
                phase_id="gc_emergency_recovery",
                phase_type="agent_execution_phase",
                summary="GC chooses emergency recovery after mobile-crane rejection.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Mobile crane was rejected; choose emergency recovery.",
                        required_decisions=[
                            single(
                                "S02_GC_EMERGENCY_RECOVERY",
                                "gc",
                                "Choose emergency recovery.",
                                [
                                    option("rent_replacement_crane", "Use rental crane with late mobilization."),
                                    option("subcontract_lifting_scope", "Use subcontracted lifting with late mobilization."),
                                    option("wait_for_repair", "Wait for repair."),
                                    option("cancel_scope", "Cancel scope."),
                                ],
                            )
                        ],
                    )
                ],
            )
        metrics = self.compute_metrics(state)
        if (
            metrics["weather_damage_observed"]
            and not self.phase_done(state, "crane_weather_checkpoint")
        ):
            return self.observable_event_phase(
                phase_id="crane_weather_checkpoint",
                summary="The severe-weather exposure checkpoint is observed.",
                public_fact={
                    "event_id": "S02_CRANE_WEATHER_CHECKPOINT",
                    "summary": (
                        "Crane-dependent work sustained damage or disruption during the severe-weather "
                        "window. The internal cause is not publicly established."
                    ),
                    "obligation_id": "weather_protection",
                    "due_tick": 21,
                    "observed_status": "weather_damage_or_disruption",
                    "possible_counterparty_ids": ["gc", "labor_subcontractor", "steel_supplier"],
                },
            )
        if (
            metrics["weather_damage_observed"]
            and self.phase_done(state, "crane_weather_checkpoint")
            and (
                "S02_GC_WEATHER_DAMAGE_RESPONSE" not in state.decisions
                or "S02_LABOR_WEATHER_DAMAGE_RESPONSE" not in state.decisions
            )
        ):
            turns = []
            if "S02_GC_WEATHER_DAMAGE_RESPONSE" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="gc",
                        context=(
                            "The severe-weather checkpoint showed weather damage or disruption. "
                            "Choose the project response based on the observed condition, without assuming "
                            "that other agents know your internal recovery constraints."
                        ),
                        required_decisions=[
                            single(
                                "S02_GC_WEATHER_DAMAGE_RESPONSE",
                                "gc",
                                "Choose weather-damage recovery response.",
                                [
                                    option("stabilize_and_resequence", "Stabilize the site and resequence remaining crane work."),
                                    option("accelerate_remaining_lifts", "Spend to accelerate remaining lifts after weather."),
                                    option("submit_weather_claim_notice", "Submit a weather-impact notice and preserve the claim record."),
                                ],
                            )
                        ],
                    )
                )
            if "S02_LABOR_WEATHER_DAMAGE_RESPONSE" not in state.decisions:
                turns.append(
                    PhaseTurn(
                        agent_id="labor_subcontractor",
                        context=(
                            "The severe-weather checkpoint showed damage or disruption to crane-dependent "
                            "work. Choose a labor response to the observable disruption."
                        ),
                        required_decisions=[
                            single(
                                "S02_LABOR_WEATHER_DAMAGE_RESPONSE",
                                "labor_subcontractor",
                                "Choose labor response to weather-disrupted crane work.",
                                [
                                    option("keep_crews_available", "Keep affected crews available."),
                                    option("demobilize_until_recovered", "Demobilize until recovery date is credible."),
                                    option("submit_idle_cost_notice", "Submit idle-cost notice."),
                                ],
                            )
                        ],
                    )
                )
            return Phase(
                phase_id="weather_damage_response",
                phase_type="agent_execution_phase",
                summary="GC and labor respond to observed weather damage or disruption.",
                turns=turns,
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return self.final_assessment_phase(
            state,
            AssessmentEvidence(
                evidence_id="S02_RECOVERY_OUTCOME",
                summary=f"Crane-dependent work finished at tick {state.canonical_state['project'].get('crane_work_finish_tick')}.",
                possible_counterparty_ids=["gc", "owner", "inspector"],
                diagnosticity="recovery_outcome",
            ),
            ["owner", "lender", "labor_subcontractor", "steel_supplier", "inspector"],
        )

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        components = self.base_components(state)
        recovery = self.selected(state, "S02_GC_RECOVERY_PLAN")
        gc_weather_response = self.selected(state, "S02_GC_WEATHER_DAMAGE_RESPONSE")
        labor_weather_response = self.selected(state, "S02_LABOR_WEATHER_DAMAGE_RESPONSE")
        finish_table = {
            "normal": {
                "rent_replacement_crane": (21, "rental", 1_400_000),
                "accelerated_repair": (23, "accelerated_repair", 650_000),
                "use_mobile_crane": (23, "mobile_crane", 900_000),
                "subcontract_lifting_scope": (24, "subcontracted_lift", 1_600_000),
                "wait_for_diagnostics": (27, "diagnostic_repair", 450_000),
            },
            "stressed": {
                "rent_replacement_crane": (22, "rental", 1_600_000),
                "accelerated_repair": (25, "accelerated_repair", 900_000),
                "use_mobile_crane": (24, "mobile_crane", 1_000_000),
                "subcontract_lifting_scope": (25, "subcontracted_lift", 1_800_000),
                "wait_for_diagnostics": (28, "diagnostic_repair", 650_000),
            },
        }
        deadlock = recovery in {None, "cancel_crane_dependent_scope"}
        finish = 999
        recovery_label = ""
        eligible_cost = 0
        weather_damage_observed = False
        if not deadlock:
            finish, recovery_label, eligible_cost = finish_table[state.variant][recovery]
        if recovery == "use_mobile_crane":
            review = self.selected(state, "S02_INSPECTOR_MOBILE_CRANE_REVIEW")
            if review == "approve_with_site_modifications":
                components["site_modifications"] = 250_000
                finish += 1
            elif review == "reject":
                emergency = self.selected(state, "S02_GC_EMERGENCY_RECOVERY")
                if emergency == "rent_replacement_crane":
                    finish = finish_table[state.variant]["rent_replacement_crane"][0] + 1
                    recovery_label = "rental"
                    eligible_cost = finish_table[state.variant]["rent_replacement_crane"][2] + 300_000
                elif emergency == "subcontract_lifting_scope":
                    finish = finish_table[state.variant]["subcontract_lifting_scope"][0] + 1
                    recovery_label = "subcontracted_lift"
                    eligible_cost = finish_table[state.variant]["subcontract_lifting_scope"][2] + 300_000
                elif emergency == "wait_for_repair":
                    finish = finish_table[state.variant]["accelerated_repair"][0] + 2
                    recovery_label = "accelerated_repair"
                    eligible_cost = finish_table[state.variant]["accelerated_repair"][2]
                else:
                    deadlock = True
                    finish = 999
        interim = self.parameters(state, "S02_GC_INTERIM_PLAN")
        if interim and not deadlock:
            if not interim["protect_exposed_work"]:
                components["weather_damage"] = 2_400_000
                finish += 4
                weather_damage_observed = True
            else:
                components["protection"] = 350_000
            if interim["crew_plan"] == "retain_idle":
                components["crew_idle"] = max(0, finish - 18) * 300_000
            elif interim["crew_plan"] == "demobilize":
                components["demobilization"] = 200_000
                finish += 1 if state.variant == "normal" else 2
            elif interim["crew_plan"] == "resequence_to_other_work":
                components["resequencing"] = 200_000
            if interim["delivery_plan"] == "accept_as_scheduled" and finish > 20:
                components["storage_and_rehandling"] = 500_000
                finish += 1
            elif interim["delivery_plan"] == "postpone":
                components["delivery_postponement"] = 100_000
        if weather_damage_observed:
            if gc_weather_response == "stabilize_and_resequence":
                components["post_weather_stabilization"] = 250_000
            elif gc_weather_response == "accelerate_remaining_lifts":
                components["post_weather_acceleration"] = 700_000 if state.variant == "normal" else 900_000
                finish = max(21, finish - 1)
            elif gc_weather_response == "submit_weather_claim_notice":
                components["weather_claim_administration"] = 150_000
                finish += 1
            if labor_weather_response == "keep_crews_available":
                components["post_weather_labor_hold"] = 300_000
            elif labor_weather_response == "demobilize_until_recovered":
                components["post_weather_demobilization"] = 200_000
                finish += 1 if state.variant == "normal" else 2
            elif labor_weather_response == "submit_idle_cost_notice":
                components["post_weather_idle_cost_notice"] = 350_000
        request = self.parameters(state, "S02_GC_RECOVERY_COST_REQUEST")
        owner_response = self.selected(state, "S02_OWNER_RECOVERY_COST_RESPONSE")
        requested = int(eligible_cost * request.get("requested_reimbursement_fraction", 0.0)) if request else 0
        if owner_response == "approve_requested_amount":
            components[recovery_label] = requested
        elif owner_response == "approve_half_of_requested_amount":
            components[recovery_label] = requested // 2
        completion = 999 if deadlock else max(
            state.canonical_state["project"]["other_path_completion_tick"],
            finish + 20,
        )
        components["delay_overhead"] = 0 if deadlock else max(
            0,
            completion - state.canonical_state["project"]["other_path_completion_tick"],
        ) * self.project_delay_overhead_per_tick
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion, deadlock=deadlock)
        crane_path_completion = 999 if deadlock else finish + 20
        actual_finish_overrides: dict[str, int] = {}
        blocked_deliverable_ids: set[str] = set()
        if finish >= 999 or deadlock:
            blocked_deliverable_ids.add("D12_GC_CRANE_LIFT_OPERATIONS_READY")
        else:
            actual_finish_overrides.update(
                {
                    "D12_GC_CRANE_LIFT_OPERATIONS_READY": finish,
                    "D13_LABOR_STRUCTURAL_STEEL_ERECTED": max(
                        finish,
                        crane_path_completion - 18,
                    ),
                    "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
                    "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
                    "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
                }
            )
        deliverable_metrics = self.deliverable_metrics(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes={
                "D12_GC_CRANE_LIFT_OPERATIONS_READY": "crane recovery and interim plan set lift readiness",
                "D13_LABOR_STRUCTURAL_STEEL_ERECTED": "crane-dependent work finish cascaded to structural erection",
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "crane path and other baseline path set project completion",
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": "crane path and other baseline path set project completion",
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": "crane path and other baseline path set project completion",
            },
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "crane_work_finish_tick": finish,
            "weather_damage_observed": weather_damage_observed,
            "weather_damage_gc_response": gc_weather_response,
            "weather_damage_labor_response": labor_weather_response,
            "cost_components": components,
            **deliverable_metrics,
        }


class S03OwnerLiquidityShortfall(Scenario):
    scenario_key = "S03"
    scenario_id = "S03_OWNER_LIQUIDITY_SHORTFALL"
    name = "Owner liquidity shortfall and payment cascade"
    actors = {
        "S03_OWNER_PAYMENT_PLAN": "owner",
        "S03_OWNER_FINANCING_SOURCE": "owner",
        "S03_LENDER_ACCELERATED_DRAW_RESPONSE": "lender",
        "S03_GC_PAYMENT_AMENDMENT_RESPONSE": "gc",
        "S03_GC_SHORT_PAYMENT_RESPONSE": "gc",
        "S03_LABOR_PAYMENT_RESPONSE": "labor_subcontractor",
        "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE": "owner",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_000_000,
            "other_path_completion_tick": 40,
            "owner": {"unrestricted_cash": 2_000_000, "additional_equity_available": 2_000_000, "bridge_capacity": 3_000_000, "bridge_fee": 200_000, "pending_lender_draw": 3_000_000, "draw_documentation_complete": True},
            "gc": {"cash": 4_000_000, "working_capital_available": 4_000_000, "labor_payment_due_tick_22": 1_200_000, "remobilization_delay_ticks": 3},
            "labor_subcontractor": {"cash": 2_000_000, "payroll_due_tick_22": 1_000_000},
            "lender": {"undisbursed_committed_funds": 3_000_000, "review_capacity": "immediate"},
        },
        "stressed": {
            "base_project_cost": 98_800_000,
            "other_path_completion_tick": 44,
            "owner": {"unrestricted_cash": 400_000, "additional_equity_available": 800_000, "bridge_capacity": 3_000_000, "bridge_fee": 700_000, "pending_lender_draw": 2_800_000, "draw_documentation_complete": False, "missing_document_available_tick": 23},
            "gc": {"cash": 800_000, "working_capital_available": 800_000, "labor_payment_due_tick_22": 1_200_000, "remobilization_delay_ticks": 4},
            "labor_subcontractor": {"cash": 400_000, "payroll_due_tick_22": 1_000_000},
            "lender": {"undisbursed_committed_funds": 2_800_000, "review_capacity": "constrained"},
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_full_payment_tick_22", {}),
                "S03_OWNER_FINANCING_SOURCE": ("__parameters__", {"equity_injection": 0, "request_accelerated_draw": True, "bridge_amount": 0}),
                "S03_LENDER_ACCELERATED_DRAW_RESPONSE": ("approve_full_immediate", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 95_000_000, "completion_tick": 40, "payment_tick": 22},
        },
        "normal_failure": {
            "variant": "normal",
            "decisions": {
                "S03_OWNER_PAYMENT_PLAN": ("schedule_no_payment", {}),
                "S03_OWNER_FINANCING_SOURCE": ("__parameters__", {"equity_injection": 0, "request_accelerated_draw": False, "bridge_amount": 0}),
                "S03_GC_SHORT_PAYMENT_RESPONSE": ("suspend_after_one_tick_cure", {}),
                "S03_LABOR_PAYMENT_RESPONSE": ("reject_and_demobilize", {}),
                "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE": ("pay_outstanding_balance_in_full", {}),
            },
            "expected": {"status": "SCHEDULE_INFEASIBLE", "final_project_cost": 97_950_000, "completion_tick": 49, "payment_tick": 29},
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S03_OWNER_PAYMENT_PLAN": ("propose_split_payment", {}),
                "S03_OWNER_FINANCING_SOURCE": ("__parameters__", {"equity_injection": 0, "request_accelerated_draw": True, "bridge_amount": 0}),
                "S03_GC_PAYMENT_AMENDMENT_RESPONSE": ("accept_and_continue_full_pace", {}),
                "S03_LENDER_ACCELERATED_DRAW_RESPONSE": ("require_missing_document_then_disburse", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 99_000_000, "completion_tick": 44},
        },
        "stressed_failure": {
            "variant": "stressed",
            "decisions": {
                "S03_OWNER_PAYMENT_PLAN": ("pay_available_cash_without_agreement", {}),
                "S03_OWNER_FINANCING_SOURCE": ("__parameters__", {"equity_injection": 0, "request_accelerated_draw": False, "bridge_amount": 0}),
                "S03_GC_SHORT_PAYMENT_RESPONSE": ("suspend_after_one_tick_cure", {}),
                "S03_LABOR_PAYMENT_RESPONSE": ("reject_and_demobilize", {}),
                "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE": ("pay_outstanding_balance_in_full", {}),
            },
            "expected": {"status": "SCHEDULE_INFEASIBLE", "final_project_cost": 101_000_000, "completion_tick": 50, "payment_tick": 29},
        },
    }

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "owner_liquidity_shortfall"):
            return Phase(
                phase_id="owner_liquidity_shortfall",
                phase_type="event_phase",
                summary="Owner privately learns expected funding will not arrive before payment due date.",
                public_facts=[
                    {
                        "event_id": "S03_PAYMENT_DUE_NOTICE",
                        "summary": "A $3,000,000 owner payment is contractually due at tick 22.",
                        "possible_counterparty_ids": ["owner"],
                    }
                ],
                private_facts_by_agent={
                    "owner": {
                        "event_id": "S03_PRIVATE_OWNER_FUNDING_DELAY",
                        "summary": "Expected external funding arrives at tick 29; cash and financing options are known to owner.",
                    }
                },
            )
        if "S03_OWNER_PAYMENT_PLAN" not in state.decisions:
            equity_allowed = [0, 1_000_000, 2_000_000] if state.variant == "normal" else [0, 400_000, 800_000]
            return Phase(
                phase_id="owner_payment_and_financing",
                phase_type="agent_execution_phase",
                summary="Owner chooses payment plan and financing source.",
                turns=[
                    PhaseTurn(
                        agent_id="owner",
                        context="Choose payment and funding actions for the tick-22 payment obligation.",
                        required_decisions=[
                            single(
                                "S03_OWNER_PAYMENT_PLAN",
                                "owner",
                                "Choose payment plan.",
                                [
                                    option("schedule_full_payment_tick_22", "Schedule full payment at tick 22."),
                                    option("propose_three_tick_deferral", "Propose full payment at tick 25."),
                                    option("propose_split_payment", "Propose split payment."),
                                    option("pay_available_cash_without_agreement", "Pay available cash without agreement."),
                                    option("schedule_no_payment", "Schedule no owner payment before routine funding."),
                                ],
                            ),
                            params(
                                "S03_OWNER_FINANCING_SOURCE",
                                "owner",
                                "Choose financing source.",
                                {
                                    "equity_injection": equity_allowed,
                                    "request_accelerated_draw": [True, False],
                                    "bridge_amount": [0, 1_500_000, 3_000_000],
                                },
                            ),
                        ],
                    )
                ],
            )
        followups: list[PhaseTurn] = []
        plan = self.selected(state, "S03_OWNER_PAYMENT_PLAN")
        financing = self.parameters(state, "S03_OWNER_FINANCING_SOURCE")
        payment_due_missed = self._payment_due_missed(state)
        if payment_due_missed and not self.phase_done(state, "payment_due_checkpoint"):
            return self.observable_event_phase(
                phase_id="payment_due_checkpoint",
                summary="The tick-22 owner payment checkpoint is observed.",
                public_fact={
                    "event_id": "S03_PAYMENT_DUE_CHECKPOINT",
                    "summary": (
                        "The owner payment due at tick 22 was not fully received. "
                        "The cause is not publicly established by this observation."
                    ),
                    "obligation_id": "owner_payment_due_tick_22",
                    "due_tick": 22,
                    "observed_status": "not_fully_paid",
                    "possible_counterparty_ids": ["owner", "lender"],
                },
            )
        if plan in {"propose_three_tick_deferral", "propose_split_payment"} and "S03_GC_PAYMENT_AMENDMENT_RESPONSE" not in state.decisions:
            followups.append(
                PhaseTurn(
                    agent_id="gc",
                    context="Respond to owner payment-amendment proposal.",
                    required_decisions=[
                        single(
                            "S03_GC_PAYMENT_AMENDMENT_RESPONSE",
                            "gc",
                            "Choose payment amendment response.",
                            [
                                option("accept_and_continue_full_pace", "Accept and continue full pace."),
                                option("accept_and_reduce_work_rate", "Accept and reduce work rate."),
                                option("reject_amendment", "Reject amendment."),
                            ],
                        )
                    ],
                )
            )
        if financing.get("request_accelerated_draw") and "S03_LENDER_ACCELERATED_DRAW_RESPONSE" not in state.decisions:
            followups.append(
                PhaseTurn(
                    agent_id="lender",
                    context="Respond to owner accelerated draw request.",
                    required_decisions=[
                        single(
                            "S03_LENDER_ACCELERATED_DRAW_RESPONSE",
                            "lender",
                            "Choose accelerated draw response.",
                            [
                                option("approve_full_immediate", "Approve full immediate draw."),
                                option("approve_partial_1500000", "Approve partial draw."),
                                option("require_missing_document_then_disburse", "Require missing document then disburse."),
                                option("reject_acceleration", "Reject acceleration."),
                            ],
                        )
                    ],
                )
            )
        if (
            payment_due_missed
            and self.phase_done(state, "payment_due_checkpoint")
            and "S03_GC_SHORT_PAYMENT_RESPONSE" not in state.decisions
        ):
            followups.append(
                PhaseTurn(
                    agent_id="gc",
                    context=(
                        "The tick-22 payment checkpoint passed without full payment. "
                        "Respond to observed short or missing payment."
                    ),
                    required_decisions=[
                        single(
                            "S03_GC_SHORT_PAYMENT_RESPONSE",
                            "gc",
                            "Choose short-payment response.",
                            [
                                option("continue_full_pace_with_working_capital", "Continue using working capital."),
                                option("obtain_short_term_financing", "Obtain short-term financing."),
                                option("reduce_work_rate", "Reduce work rate."),
                                option("suspend_after_one_tick_cure", "Suspend after one-tick cure period."),
                                option("request_labor_payment_amendment", "Request labor payment amendment."),
                            ],
                        )
                    ],
                )
            )
        if self.selected(state, "S03_GC_SHORT_PAYMENT_RESPONSE") in {"suspend_after_one_tick_cure", "request_labor_payment_amendment"} and "S03_LABOR_PAYMENT_RESPONSE" not in state.decisions:
            followups.append(
                PhaseTurn(
                    agent_id="labor_subcontractor",
                    context="Respond to payment-related work interruption or amendment request.",
                    required_decisions=[
                        single(
                            "S03_LABOR_PAYMENT_RESPONSE",
                            "labor_subcontractor",
                            "Choose labor payment response.",
                            [
                                option("accept_deferral_and_continue", "Accept deferral and continue."),
                                option("accept_partial_and_reduce_crew", "Accept partial payment and reduce crew."),
                                option("reject_and_demobilize", "Reject and demobilize."),
                                option("continue_without_amendment", "Continue without amendment."),
                            ],
                        )
                    ],
                )
            )
        if (
            payment_due_missed
            and self.phase_done(state, "payment_due_checkpoint")
            and "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE" not in state.decisions
        ):
            followups.append(
                PhaseTurn(
                    agent_id="owner",
                    context="Routine draw arrives with overdue balance outstanding.",
                    required_decisions=[
                        single(
                            "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE",
                            "owner",
                            "Choose outstanding payment response.",
                            [
                                option("pay_outstanding_balance_in_full", "Pay outstanding balance in full."),
                                option("pay_available_partial_amount", "Pay partial allowed amount."),
                                option("retain_draw_and_make_no_payment", "Retain draw and make no payment."),
                            ],
                        )
                    ],
                )
            )
        if followups:
            return Phase(
                phase_id=f"payment_followup_{len(state.decisions)}",
                phase_type="agent_execution_phase",
                summary="Payment cascade follow-up decisions.",
                turns=followups,
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return self.final_assessment_phase(
            state,
            AssessmentEvidence(
                evidence_id="S03_PAYMENT_OUTCOME",
                summary=f"Owner payment completed at tick {state.canonical_state['project'].get('payment_tick')}; due tick was 22.",
                possible_counterparty_ids=["owner", "gc", "lender", "labor_subcontractor"],
                diagnosticity="payment_outcome",
            ),
            ["gc", "labor_subcontractor", "lender", "steel_supplier", "inspector"],
        )

    def _payment_due_missed(self, state: RunState) -> bool:
        plan = self.selected(state, "S03_OWNER_PAYMENT_PLAN")
        financing = self.parameters(state, "S03_OWNER_FINANCING_SOURCE")
        lender = self.selected(state, "S03_LENDER_ACCELERATED_DRAW_RESPONSE")
        gc_amendment = self.selected(state, "S03_GC_PAYMENT_AMENDMENT_RESPONSE")
        if plan == "schedule_full_payment_tick_22":
            if financing.get("request_accelerated_draw") and lender is None:
                return False
            return not (
                financing.get("request_accelerated_draw")
                and lender == "approve_full_immediate"
            )
        if plan in {"schedule_no_payment", "pay_available_cash_without_agreement"}:
            return True
        if plan in {"propose_three_tick_deferral", "propose_split_payment"}:
            if gc_amendment is None:
                return False
            return gc_amendment == "reject_amendment"
        return False

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        components = self.base_components(state)
        plan = self.selected(state, "S03_OWNER_PAYMENT_PLAN")
        gc_amendment = self.selected(state, "S03_GC_PAYMENT_AMENDMENT_RESPONSE")
        gc_short = self.selected(state, "S03_GC_SHORT_PAYMENT_RESPONSE")
        labor = self.selected(state, "S03_LABOR_PAYMENT_RESPONSE")
        financing = self.parameters(state, "S03_OWNER_FINANCING_SOURCE")
        lender = self.selected(state, "S03_LENDER_ACCELERATED_DRAW_RESPONSE")
        routine_draw_response = self.selected(state, "S03_OWNER_ROUTINE_DRAW_PAYMENT_RESPONSE")
        owner_start = self.starts[state.variant]["owner"]
        payment_tick = 29
        payment_status = "routine_payment"
        critical_finish = 26
        if plan == "schedule_full_payment_tick_22":
            if financing.get("request_accelerated_draw") and lender == "approve_full_immediate":
                payment_tick = 22
                payment_status = "paid_on_time"
            else:
                payment_tick = 29
                payment_status = "routine_payment"
        elif plan == "propose_split_payment" and gc_amendment == "accept_and_continue_full_pace":
            payment_tick = 24
            payment_status = "accepted_split_payment"
            components["accepted_payment_amendment"] = 200_000
        elif plan == "propose_three_tick_deferral" and gc_amendment == "accept_and_continue_full_pace":
            payment_tick = 25
            payment_status = "accepted_deferred_payment"
            components["accepted_payment_amendment"] = 200_000
            critical_finish += 2
        elif plan in {"schedule_no_payment", "pay_available_cash_without_agreement"}:
            payment_tick = 29
            payment_status = "late_payment_cured_by_routine_draw"
            components["late_payment_penalty"] = 700_000
            if gc_short == "suspend_after_one_tick_cure" and labor == "reject_and_demobilize":
                critical_finish += 9 if state.variant == "normal" else 10
            elif gc_short == "reduce_work_rate":
                critical_finish += 4
            if routine_draw_response == "pay_available_partial_amount":
                payment_status = "partial_payment_after_routine_draw"
                components["partial_payment_disruption"] = 300_000
                critical_finish += 2
            elif routine_draw_response == "retain_draw_and_make_no_payment":
                payment_status = "unpaid_after_routine_draw"
                components["nonpayment_disruption"] = 700_000
                critical_finish += 6
        if financing.get("bridge_amount", 0):
            components["bridge_fee"] = 200_000 if state.variant == "normal" else 700_000
        equity_injection = financing.get("equity_injection", 0) if financing else 0
        owner_cash_after_financing = (
            owner_start["unrestricted_cash"]
            + equity_injection
            + financing.get("bridge_amount", 0)
        )
        completion = max(
            state.canonical_state["project"]["other_path_completion_tick"],
            critical_finish + 14,
        )
        components["delay_overhead"] = max(
            0,
            completion - state.canonical_state["project"]["other_path_completion_tick"],
        ) * self.project_delay_overhead_per_tick
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion)
        deliverable_metrics = self.deliverable_metrics(
            actual_finish_overrides={
                "D14_OWNER_PROGRESS_PAYMENT_CURRENT": payment_tick,
                "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE": critical_finish,
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
            },
            impact_notes={
                "D14_OWNER_PROGRESS_PAYMENT_CURRENT": "owner payment plan set actual payment-current tick",
                "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE": "payment cascade set critical-work finish feeding structural release path",
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "payment cascade and other baseline path set project completion",
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": "payment cascade and other baseline path set project completion",
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": "payment cascade and other baseline path set project completion",
            },
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "payment_tick": payment_tick,
            "payment_status": payment_status,
            "critical_work_finish_tick": critical_finish,
            "financing_state": {
                "equity_injection": equity_injection,
                "bridge_amount": financing.get("bridge_amount", 0) if financing else 0,
                "owner_cash_after_financing": owner_cash_after_financing,
                "routine_draw_payment_response": routine_draw_response,
            },
            "organization_ledger": {
                "owner": {
                    "starting_unrestricted_cash": owner_start["unrestricted_cash"],
                    "equity_injection": equity_injection,
                    "bridge_amount": financing.get("bridge_amount", 0) if financing else 0,
                    "cash_after_financing": owner_cash_after_financing,
                    "payment_status": payment_status,
                }
            },
            "terminal_values": {
                "owner_terminal_value_delta": -cost - equity_injection,
            },
            "cost_components": components,
            **deliverable_metrics,
        }


class S04WeldInspectionFailure(Scenario):
    scenario_key = "S04"
    scenario_id = "S04_WELD_INSPECTION_FAILURE"
    name = "Structural weld failure at a draw milestone"
    actors = {
        "S04_GC_INITIAL_CORRECTIVE_STRATEGY": "gc",
        "S04_GC_POST_TEST_REPAIR_STRATEGY": "gc",
        "S04_ENGINEERING_SOLUTION": "gc",
        "S04_LABOR_REPAIR_MODE": "labor_subcontractor",
        "S04_INSPECTOR_REINSPECTION": "inspector",
        "S04_GC_SECOND_CORRECTIVE_STRATEGY": "gc",
        "S04_INSPECTOR_FINAL_RELEASE_REVIEW": "inspector",
        "S04_LENDER_DRAW_RESPONSE": "lender",
    }
    starts = {
        "normal": {
            "base_project_cost": 96_200_000,
            "other_path_completion_tick": 41,
            "canonical_weld_state": {"known_defective_welds": 30, "hidden_defective_welds": 0, "physical_compliance": False},
            "owner": {"contingency_remaining": 4_000_000},
            "gc": {"cash": 3_500_000, "repair_capacity_available": True},
            "steel_supplier": {"cash": 1_800_000, "replacement_material_available_tick": 28},
            "labor_subcontractor": {"repair_crew_available_tick": 27},
            "inspector": {"reinspection_delay_ticks": 1},
            "lender": {"pending_draw_amount": 5_000_000},
        },
        "stressed": {
            "base_project_cost": 98_900_000,
            "other_path_completion_tick": 44,
            "canonical_weld_state": {"known_defective_welds": 30, "hidden_defective_welds": 12, "physical_compliance": False},
            "owner": {"contingency_remaining": 1_800_000},
            "gc": {"cash": 900_000, "repair_capacity_available": True},
            "steel_supplier": {"cash": 700_000, "replacement_material_available_tick": 30},
            "labor_subcontractor": {"repair_crew_available_tick": 27},
            "inspector": {"reinspection_delay_ticks": 1},
            "lender": {"pending_draw_amount": 5_000_000},
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("targeted_repair_known_welds", {}),
                "S04_LABOR_REPAIR_MODE": ("standard_crew", {}),
                "S04_INSPECTOR_REINSPECTION": ("approve", {}),
                "S04_LENDER_DRAW_RESPONSE": ("release_draw", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 97_000_000, "completion_tick": 41, "structural_release_tick": 29},
        },
        "normal_failure": {
            "variant": "normal",
            "decisions": {
                "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("independent_retest", {}),
                "S04_GC_SECOND_CORRECTIVE_STRATEGY": ("full_remove_and_replace", {}),
                "S04_INSPECTOR_FINAL_RELEASE_REVIEW": ("approve", {}),
                "S04_LENDER_DRAW_RESPONSE": ("release_draw", {}),
            },
            "expected": {"status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"], "final_project_cost": 102_200_000, "completion_tick": 49, "structural_release_tick": 38},
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("expanded_testing", {}),
                "S04_GC_POST_TEST_REPAIR_STRATEGY": ("repair_all_identified_welds", {}),
                "S04_LABOR_REPAIR_MODE": ("overtime_crew", {}),
                "S04_INSPECTOR_REINSPECTION": ("approve", {}),
                "S04_LENDER_DRAW_RESPONSE": ("release_draw", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 100_910_000, "completion_tick": 44, "structural_release_tick": 31},
        },
        "stressed_failure": {
            "variant": "stressed",
            "decisions": {
                "S04_GC_INITIAL_CORRECTIVE_STRATEGY": ("targeted_repair_known_welds", {}),
                "S04_LABOR_REPAIR_MODE": ("standard_crew", {}),
                "S04_INSPECTOR_REINSPECTION": ("fail", {}),
                "S04_GC_SECOND_CORRECTIVE_STRATEGY": ("full_remove_and_replace", {}),
                "S04_INSPECTOR_FINAL_RELEASE_REVIEW": ("approve", {}),
                "S04_LENDER_DRAW_RESPONSE": ("release_draw", {}),
            },
            "expected": {"status_any_of": ["BUDGET_INFEASIBLE", "SCHEDULE_INFEASIBLE"], "final_project_cost": 105_000_000, "completion_tick": 50, "structural_release_tick": 39},
        },
    }

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "weld_inspection_failure"):
            return Phase(
                phase_id="weld_inspection_failure",
                phase_type="event_phase",
                summary="Official weld inspection fails before lender draw milestone.",
                public_facts=[
                    {
                        "event_id": "S04_PUBLIC_WELD_FAILURE",
                        "summary": "Inspection failed; 30 known failed welds; structural release blocked.",
                        "possible_counterparty_ids": ["gc", "steel_supplier", "inspector"],
                    }
                ],
            )
        if "S04_GC_INITIAL_CORRECTIVE_STRATEGY" not in state.decisions:
            return Phase(
                phase_id="gc_initial_corrective_strategy",
                phase_type="agent_execution_phase",
                summary="GC chooses initial corrective strategy.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Choose corrective strategy after failed weld inspection.",
                        required_decisions=[
                            single(
                                "S04_GC_INITIAL_CORRECTIVE_STRATEGY",
                                "gc",
                                "Choose initial corrective strategy.",
                                [
                                    option("targeted_repair_known_welds", "Repair known welds."),
                                    option("expanded_testing", "Expand testing before repair."),
                                    option("engineering_disposition", "Seek engineering disposition."),
                                    option("full_remove_and_replace", "Full remove and replace."),
                                    option("independent_retest", "Retest independently."),
                                    option("proceed_without_correction", "Proceed without correction."),
                                ],
                            )
                        ],
                    )
                ],
            )
        initial = self.selected(state, "S04_GC_INITIAL_CORRECTIVE_STRATEGY")
        if initial == "expanded_testing" and "S04_GC_POST_TEST_REPAIR_STRATEGY" not in state.decisions:
            return Phase(
                phase_id="post_test_repair_strategy",
                phase_type="agent_execution_phase",
                summary="GC chooses repair after expanded testing.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Expanded testing reveals the complete defect scope.",
                        required_decisions=[
                            single(
                                "S04_GC_POST_TEST_REPAIR_STRATEGY",
                                "gc",
                                "Choose post-test repair strategy.",
                                [
                                    option("repair_all_identified_welds", "Repair all identified welds."),
                                    option("reinforce_affected_connections", "Reinforce affected connections."),
                                    option("full_remove_and_replace", "Full remove and replace."),
                                    option("abandon_structural_scope", "Abandon structural scope."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if initial == "engineering_disposition" and "S04_ENGINEERING_SOLUTION" not in state.decisions:
            return Phase(
                phase_id="engineering_solution",
                phase_type="agent_execution_phase",
                summary="GC chooses engineering solution.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Engineering disposition is available; choose a solution.",
                        required_decisions=[
                            single(
                                "S04_ENGINEERING_SOLUTION",
                                "gc",
                                "Choose engineering solution.",
                                [
                                    option("engineered_reinforcement", "Engineered reinforcement."),
                                    option("engineered_repair", "Engineered repair."),
                                    option("full_remove_and_replace", "Full remove and replace."),
                                    option("decline_engineered_solution", "Decline engineered solution."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if initial == "independent_retest" and "S04_GC_SECOND_CORRECTIVE_STRATEGY" not in state.decisions:
            return self._second_correction_phase("Retest confirms correction is still required.")
        repair_path_ready = initial in {"targeted_repair_known_welds", "full_remove_and_replace"} or self.selected(state, "S04_GC_POST_TEST_REPAIR_STRATEGY") in {"repair_all_identified_welds", "reinforce_affected_connections", "full_remove_and_replace"} or self.selected(state, "S04_ENGINEERING_SOLUTION") in {"engineered_reinforcement", "engineered_repair", "full_remove_and_replace"}
        if repair_path_ready and "S04_LABOR_REPAIR_MODE" not in state.decisions and initial != "full_remove_and_replace":
            return Phase(
                phase_id="labor_repair_mode",
                phase_type="agent_execution_phase",
                summary="Labor chooses repair crew mode.",
                turns=[
                    PhaseTurn(
                        agent_id="labor_subcontractor",
                        context="Choose repair crew mode.",
                        required_decisions=[
                            single(
                                "S04_LABOR_REPAIR_MODE",
                                "labor_subcontractor",
                                "Choose repair mode.",
                                [
                                    option("standard_crew", "Use standard crew."),
                                    option("overtime_crew", "Use overtime crew."),
                                    option("defer_crew_two_ticks", "Defer crew two ticks."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if repair_path_ready and "S04_INSPECTOR_REINSPECTION" not in state.decisions and initial != "independent_retest":
            return Phase(
                phase_id="reinspection",
                phase_type="agent_execution_phase",
                summary="Inspector reinspects structural work.",
                turns=[
                    PhaseTurn(
                        agent_id="inspector",
                        context="Choose final reinspection status based on available evidence.",
                        required_decisions=[
                            single(
                                "S04_INSPECTOR_REINSPECTION",
                                "inspector",
                                "Choose reinspection outcome.",
                                [
                                    option("approve", "Approve official pass."),
                                    option("fail", "Fail official pass."),
                                    option("request_additional_testing", "Request additional testing."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if self.selected(state, "S04_INSPECTOR_REINSPECTION") in {"fail", "request_additional_testing"} and "S04_GC_SECOND_CORRECTIVE_STRATEGY" not in state.decisions:
            return self._second_correction_phase("Reinspection did not produce an official pass.")
        metrics = self.compute_metrics(state)
        if (
            not metrics["official_final_pass"]
            and not self.phase_done(state, "structural_release_checkpoint")
        ):
            return self.observable_event_phase(
                phase_id="structural_release_checkpoint",
                summary="The structural release checkpoint is observed.",
                public_fact={
                    "event_id": "S04_STRUCTURAL_RELEASE_CHECKPOINT",
                    "summary": (
                        "Structural release remains blocked because an official final pass has not "
                        "been recorded. The physical correction status is not established by this "
                        "checkpoint alone."
                    ),
                    "obligation_id": "structural_release",
                    "observed_status": "official_pass_missing",
                    "possible_counterparty_ids": ["gc", "steel_supplier", "inspector"],
                },
            )
        if (
            not metrics["official_final_pass"]
            and self.phase_done(state, "structural_release_checkpoint")
            and "S04_GC_SECOND_CORRECTIVE_STRATEGY" not in state.decisions
        ):
            return self._second_correction_phase(
                "Structural release checkpoint shows an official final pass is still missing."
            )
        second = self.selected(state, "S04_GC_SECOND_CORRECTIVE_STRATEGY")
        if (
            self.phase_done(state, "structural_release_checkpoint")
            and second in {"repair_remaining_identified_welds", "full_remove_and_replace"}
            and "S04_INSPECTOR_FINAL_RELEASE_REVIEW" not in state.decisions
        ):
            return Phase(
                phase_id="final_release_review",
                phase_type="agent_execution_phase",
                summary="Inspector performs final release review after additional correction.",
                turns=[
                    PhaseTurn(
                        agent_id="inspector",
                        context="Additional correction has been completed after the release checkpoint. Choose final release review status.",
                        required_decisions=[
                            single(
                                "S04_INSPECTOR_FINAL_RELEASE_REVIEW",
                                "inspector",
                                "Choose final release review outcome.",
                                [
                                    option("approve", "Approve official final pass."),
                                    option("fail", "Fail official final pass."),
                                    option("request_additional_testing", "Request additional testing before pass."),
                                ],
                            )
                        ],
                    )
                ],
            )
        official_pass_selected = (
            self.selected(state, "S04_INSPECTOR_REINSPECTION") == "approve"
            or self.selected(state, "S04_INSPECTOR_FINAL_RELEASE_REVIEW") == "approve"
        )
        if official_pass_selected and "S04_LENDER_DRAW_RESPONSE" not in state.decisions:
            return Phase(
                phase_id="lender_draw_response",
                phase_type="agent_execution_phase",
                summary="Lender responds to draw after inspection.",
                turns=[
                    PhaseTurn(
                        agent_id="lender",
                        context="Decide whether to release the pending draw.",
                        required_decisions=[
                            single(
                                "S04_LENDER_DRAW_RESPONSE",
                                "lender",
                                "Choose draw response.",
                                [
                                    option("release_draw", "Release draw."),
                                    option("hold_until_official_pass", "Hold until official pass."),
                                    option("reject_draw", "Reject draw."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return self.final_assessment_phase(
            state,
            AssessmentEvidence(
                evidence_id="S04_COMPLIANCE_OUTCOME",
                summary=(
                    f"Final structural compliance is {state.canonical_state['project'].get('physical_compliance')}; "
                    f"official final pass is {state.canonical_state['project'].get('official_final_pass')}."
                ),
                possible_counterparty_ids=["gc", "steel_supplier", "inspector", "lender"],
                diagnosticity="compliance_outcome",
            ),
            ["owner", "gc", "labor_subcontractor", "lender", "inspector", "steel_supplier"],
        )

    def _second_correction_phase(self, context: str) -> Phase:
        return Phase(
            phase_id="second_corrective_strategy",
            phase_type="agent_execution_phase",
            summary="GC chooses second corrective strategy.",
            turns=[
                PhaseTurn(
                    agent_id="gc",
                    context=context,
                    required_decisions=[
                        single(
                            "S04_GC_SECOND_CORRECTIVE_STRATEGY",
                            "gc",
                            "Choose second corrective strategy.",
                            [
                                option("repair_remaining_identified_welds", "Repair remaining identified welds."),
                                option("full_remove_and_replace", "Full remove and replace."),
                                option("continue_without_physical_compliance", "Continue without physical compliance."),
                                option("abandon_structural_scope", "Abandon structural scope."),
                            ],
                        )
                    ],
                )
            ],
        )

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        components = self.base_components(state)
        initial = self.selected(state, "S04_GC_INITIAL_CORRECTIVE_STRATEGY")
        post = self.selected(state, "S04_GC_POST_TEST_REPAIR_STRATEGY")
        engineering = self.selected(state, "S04_ENGINEERING_SOLUTION")
        labor = self.selected(state, "S04_LABOR_REPAIR_MODE")
        inspection = self.selected(state, "S04_INSPECTOR_REINSPECTION")
        second = self.selected(state, "S04_GC_SECOND_CORRECTIVE_STRATEGY")
        final_review = self.selected(state, "S04_INSPECTOR_FINAL_RELEASE_REVIEW")
        lender_draw = self.selected(state, "S04_LENDER_DRAW_RESPONSE")
        release = 999
        physical = False
        deadlock = False
        if initial == "targeted_repair_known_welds":
            components["targeted_repair"] = 800_000
            release = 29
            physical = state.variant == "normal"
        elif initial == "expanded_testing":
            components["expanded_testing"] = 350_000
            if post == "repair_all_identified_welds":
                components["post_test_repair"] = 900_000 if state.variant == "normal" else 1_260_000
                release = 31 if state.variant == "normal" else 32
                physical = True
            elif post == "reinforce_affected_connections":
                components["reinforcement"] = 1_100_000 if state.variant == "normal" else 1_600_000
                release = 31 if state.variant == "normal" else 33
                physical = True
            elif post == "full_remove_and_replace":
                components["full_replacement"] = 3_800_000
                release = 38 if state.variant == "normal" else 39
                physical = True
            elif post == "abandon_structural_scope":
                deadlock = True
        elif initial == "engineering_disposition":
            components["engineering_disposition"] = 250_000
            if engineering == "engineered_reinforcement":
                components["engineered_reinforcement"] = 1_100_000
                release = 31
                physical = True
            elif engineering == "engineered_repair":
                components["engineered_repair"] = 900_000 if state.variant == "normal" else 1_260_000
                release = 31 if state.variant == "normal" else 32
                physical = True
            elif engineering == "full_remove_and_replace":
                components["full_replacement"] = 3_800_000
                release = 38 if state.variant == "normal" else 39
                physical = True
        elif initial == "full_remove_and_replace":
            components["full_replacement"] = 3_800_000
            release = 36
            physical = True
        elif initial == "independent_retest":
            components["independent_retest"] = 200_000
        if second == "full_remove_and_replace":
            components["full_replacement"] = 3_800_000
            release = 38 if state.variant == "normal" else 39
            physical = True
        elif second == "repair_remaining_identified_welds":
            components["remaining_repair"] = 360_000 if state.variant == "stressed" else 0
            release = 32 if state.variant == "normal" else 34
            physical = True
        elif second == "continue_without_physical_compliance":
            release = 999
            physical = False
        elif second == "abandon_structural_scope":
            deadlock = True
        if final_review == "request_additional_testing" and release < 999:
            components["final_release_testing"] = 200_000
            release += 2
        if labor == "overtime_crew" and release < 999:
            components["overtime_crew"] = 400_000
            release = max(27, release - 1)
        elif labor == "defer_crew_two_ticks" and release < 999:
            release += 2
        official = (inspection == "approve" or final_review == "approve") and physical
        draw_status = "not_requested"
        draw_delay_ticks = 0
        if lender_draw == "release_draw":
            draw_status = "released"
        elif lender_draw == "hold_until_official_pass":
            draw_status = "held_pending_final_pass"
            components["draw_hold_financing_cost"] = 150_000
            draw_delay_ticks = 1
        elif lender_draw == "reject_draw":
            draw_status = "rejected"
            components["draw_rejection_working_capital_cost"] = 500_000
            draw_delay_ticks = 2
        completion = 999 if deadlock else max(
            state.canonical_state["project"]["other_path_completion_tick"],
            release + 11 + draw_delay_ticks,
        )
        components["delay_overhead"] = 0 if deadlock else max(
            0,
            completion - state.canonical_state["project"]["other_path_completion_tick"],
        ) * self.project_delay_overhead_per_tick
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion, deadlock=deadlock)
        if status == "PROJECT_SUCCESS" and not official:
            status = "CRITICAL_PATH_DEADLOCK"
            reason = "physical compliance or official inspection pass missing"
        actual_finish_overrides: dict[str, int] = {}
        blocked_deliverable_ids: set[str] = set()
        if release >= 999 or deadlock or not official:
            blocked_deliverable_ids.add("D15_INSPECTOR_STRUCTURAL_WELD_RELEASE")
        else:
            actual_finish_overrides.update(
                {
                    "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE": release,
                    "D16_LENDER_STRUCTURAL_DRAW_RELEASE": max(
                        30,
                        min(completion - 10, release + draw_delay_ticks),
                    ),
                    "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT": max(
                        30,
                        min(completion - 10, release + 4),
                    ),
                    "D18_LABOR_MEP_ROUGH_IN_COMPLETE": completion - 6,
                    "D19_LABOR_CRITICAL_INSPECTION_TASK_READY": completion - 5,
                    "D20_INSPECTOR_RESERVED_INSPECTION_PASS": completion - 4,
                    "D21_LABOR_FINISHES_AND_PUNCH_READY": completion - 2,
                    "D22_GC_SYSTEMS_COMMISSIONED": completion - 1,
                    "D23_INSPECTOR_FINAL_INSPECTION_PASS": completion - 1,
                    "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
                    "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
                    "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
                }
            )
        deliverable_metrics = self.deliverable_metrics(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes={
                "D15_INSPECTOR_STRUCTURAL_WELD_RELEASE": "weld correction and inspection decisions set structural release",
                "D16_LENDER_STRUCTURAL_DRAW_RELEASE": "lender draw response changed funding release timing",
                "D17_GC_BUILDING_ENCLOSURE_WEATHERTIGHT": "structural release timing changed enclosure path",
                "D18_LABOR_MEP_ROUGH_IN_COMPLETE": "structural-release tail changed downstream interior path",
                "D19_LABOR_CRITICAL_INSPECTION_TASK_READY": "structural-release tail changed downstream inspection readiness",
                "D20_INSPECTOR_RESERVED_INSPECTION_PASS": "structural-release tail changed downstream inspection path",
                "D21_LABOR_FINISHES_AND_PUNCH_READY": "structural-release tail changed finish path",
                "D22_GC_SYSTEMS_COMMISSIONED": "structural-release tail changed commissioning path",
                "D23_INSPECTOR_FINAL_INSPECTION_PASS": "structural-release tail changed final inspection path",
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "structural-release tail set project completion",
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": "structural-release tail set project completion",
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": "structural-release tail set project completion",
            },
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "structural_release_tick": release,
            "physical_compliance": physical,
            "official_final_pass": official,
            "final_release_review_status": final_review,
            "lender_draw_status": draw_status,
            "cost_components": components,
            **deliverable_metrics,
        }


class S05LaborShortageInspection(Scenario):
    scenario_key = "S05"
    scenario_id = "S05_LABOR_SHORTAGE_INSPECTION_WINDOW"
    name = "Labor-capacity shortage and fixed inspection window"
    actors = {
        "S05_LABOR_CAPACITY_PLAN": "labor_subcontractor",
        "S05_LABOR_COMMERCIAL_REQUEST": "labor_subcontractor",
        "S05_GC_STAFFING_RESPONSE": "gc",
        "S05_OWNER_LABOR_COST_RESPONSE": "owner",
        "S05_GC_INSPECTION_BOOKING": "gc",
        "S05_INSPECTOR_EMERGENCY_SLOT_RESPONSE": "inspector",
        "S05_GC_MISSED_INSPECTION_RESPONSE": "gc",
    }
    starts = {
        "normal": {
            "base_project_cost": 95_700_000,
            "other_path_completion_tick": 40,
            "owner": {"contingency_remaining": 4_300_000, "cash": 4_500_000},
            "gc": {"cash": 3_500_000, "current_public_task_finish_tick": 35},
            "labor_subcontractor": {"committed_crew_count": 40, "actual_available_crew_count": 28, "overtime_equivalent_capacity": 12, "supplemental_hire_count": 12, "supplemental_onboarding_ticks": 2, "supplemental_hire_cost": 750_000, "subcontract_gap_cost": 900_000, "reallocation_capacity": 10, "reallocation_and_overtime_cost": 450_000, "overtime_only_cost": 600_000, "combined_acceleration_cost": 1_200_000, "cash": 1_600_000},
            "inspector": {"reserved_slot_tick": 36, "emergency_slot_available": True, "next_standard_slot_tick": 45},
        },
        "stressed": {
            "base_project_cost": 98_700_000,
            "other_path_completion_tick": 44,
            "owner": {"contingency_remaining": 1_800_000, "cash": 1_800_000},
            "gc": {"cash": 900_000, "current_public_task_finish_tick": 35},
            "labor_subcontractor": {"committed_crew_count": 40, "actual_available_crew_count": 20, "overtime_equivalent_capacity": 8, "supplemental_hire_count": 10, "supplemental_onboarding_ticks": 3, "supplemental_hire_cost": 1_200_000, "subcontract_gap_cost": 1_600_000, "reallocation_capacity": 10, "reallocation_and_overtime_cost": 900_000, "overtime_only_cost": 500_000, "combined_acceleration_cost": 2_100_000, "cash": 500_000, "available_credit": 1_200_000},
            "inspector": {"reserved_slot_tick": 36, "emergency_slot_available": True, "next_standard_slot_tick": 45},
        },
    }
    fixtures = {
        "normal_success": {
            "variant": "normal",
            "decisions": {
                "S05_LABOR_CAPACITY_PLAN": ("overtime_only", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0, "advance_requested": False}),
                "S05_GC_STAFFING_RESPONSE": ("accept_labor_plan", {}),
                "S05_OWNER_LABOR_COST_RESPONSE": ("approve_requested_amount", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 96_300_000, "completion_tick": 40, "critical_task_finish_tick": 35, "completed_inspection_tick": 36},
        },
        "normal_failure": {
            "variant": "normal",
            "decisions": {
                "S05_LABOR_CAPACITY_PLAN": ("continue_current_capacity", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 0.0, "advance_requested": False}),
                "S05_GC_STAFFING_RESPONSE": ("maintain_baseline_assumption", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
                "S05_GC_MISSED_INSPECTION_RESPONSE": ("accept_next_standard_slot", {}),
            },
            "expected": {"status": "SCHEDULE_INFEASIBLE", "final_project_cost": 97_950_000, "completion_tick": 49, "critical_task_finish_tick": 39, "completed_inspection_tick": 45},
        },
        "stressed_success": {
            "variant": "stressed",
            "decisions": {
                "S05_LABOR_CAPACITY_PLAN": ("subcontract_capacity_gap", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 1.0, "advance_requested": True}),
                "S05_GC_STAFFING_RESPONSE": ("accept_labor_plan", {}),
                "S05_OWNER_LABOR_COST_RESPONSE": ("approve_requested_amount", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
            },
            "expected": {"status": "PROJECT_SUCCESS", "final_project_cost": 100_300_000, "completion_tick": 44, "critical_task_finish_tick": 35, "completed_inspection_tick": 36},
        },
        "stressed_failure": {
            "variant": "stressed",
            "decisions": {
                "S05_LABOR_CAPACITY_PLAN": ("continue_current_capacity", {}),
                "S05_LABOR_COMMERCIAL_REQUEST": ("__parameters__", {"requested_reimbursement_fraction": 0.0, "advance_requested": False}),
                "S05_GC_STAFFING_RESPONSE": ("maintain_baseline_assumption", {}),
                "S05_GC_INSPECTION_BOOKING": ("keep_reserved_tick_36", {}),
                "S05_GC_MISSED_INSPECTION_RESPONSE": ("accept_next_standard_slot", {}),
            },
            "expected": {"status": "SCHEDULE_INFEASIBLE", "final_project_cost": 99_950_000, "completion_tick": 49, "critical_task_finish_tick": 40, "completed_inspection_tick": 45},
        },
    }

    def next_phase(self, state: RunState) -> Phase | None:
        if not self.phase_done(state, "labor_shortage"):
            return Phase(
                phase_id="labor_shortage",
                phase_type="event_phase",
                summary="Regional labor shortage threatens critical task and inspection window.",
                public_facts=[
                    {
                        "event_id": "S05_PUBLIC_LABOR_SHORTAGE",
                        "summary": "Regional labor shortage and wage pressure threaten critical task completion.",
                        "possible_counterparty_ids": ["labor_subcontractor", "gc", "inspector"],
                    }
                ],
                private_facts_by_agent={
                    "labor_subcontractor": {
                        "event_id": "S05_PRIVATE_LABOR_CAPACITY",
                        "summary": "Exact available crew count, capacity options, costs, and task-finish forecasts.",
                    }
                },
            )
        if "S05_LABOR_CAPACITY_PLAN" not in state.decisions:
            return Phase(
                phase_id="labor_capacity_plan",
                phase_type="agent_execution_phase",
                summary="Labor chooses capacity plan and commercial request.",
                turns=[
                    PhaseTurn(
                        agent_id="labor_subcontractor",
                        context="Choose capacity plan and any commercial request before the inspection window.",
                        required_decisions=[
                            single(
                                "S05_LABOR_CAPACITY_PLAN",
                                "labor_subcontractor",
                                "Choose labor capacity plan.",
                                [
                                    option("continue_current_capacity", "Continue current capacity."),
                                    option("overtime_only", "Use overtime only."),
                                    option("supplemental_hire", "Hire supplemental crew."),
                                    option("subcontract_capacity_gap", "Subcontract capacity gap."),
                                    option("reallocate_and_overtime", "Reallocate plus overtime."),
                                    option("combined_acceleration", "Use all acceleration."),
                                    option("declare_unable_to_meet_commitment", "Declare inability to meet commitment."),
                                ],
                            ),
                            params(
                                "S05_LABOR_COMMERCIAL_REQUEST",
                                "labor_subcontractor",
                                "Submit commercial request.",
                                {
                                    "requested_reimbursement_fraction": [0.0, 0.5, 1.0],
                                    "advance_requested": [True, False],
                                },
                            ),
                        ],
                    )
                ],
            )
        if "S05_GC_STAFFING_RESPONSE" not in state.decisions:
            return Phase(
                phase_id="gc_staffing_and_inspection",
                phase_type="agent_execution_phase",
                summary="GC responds to labor plan and books inspection.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context="Respond to labor plan and choose inspection booking.",
                        required_decisions=[
                            single(
                                "S05_GC_STAFFING_RESPONSE",
                                "gc",
                                "Choose staffing response.",
                                [
                                    option("accept_labor_plan", "Accept labor plan."),
                                    option("replace_labor_for_critical_scope", "Replace labor for critical scope."),
                                    option("resequence_noncritical_work", "Resequence noncritical work."),
                                    option("maintain_baseline_assumption", "Maintain baseline assumption."),
                                ],
                            ),
                            single(
                                "S05_GC_INSPECTION_BOOKING",
                                "gc",
                                "Choose inspection booking.",
                                [
                                    option("keep_reserved_tick_36", "Keep reserved tick 36."),
                                    option("request_emergency_tick_37", "Request emergency tick 37."),
                                    option("release_slot_and_take_tick_45", "Release slot and take tick 45."),
                                ],
                            ),
                        ],
                    )
                ],
            )
        request = self.parameters(state, "S05_LABOR_COMMERCIAL_REQUEST")
        if (
            request.get("requested_reimbursement_fraction", 0.0)
            or request.get("advance_requested")
        ) and "S05_OWNER_LABOR_COST_RESPONSE" not in state.decisions:
            return Phase(
                phase_id="owner_labor_cost_response",
                phase_type="agent_execution_phase",
                summary="Owner responds to labor commercial request.",
                turns=[
                    PhaseTurn(
                        agent_id="owner",
                        context="Decide whether to move requested labor capacity cost to project cost.",
                        required_decisions=[
                            single(
                                "S05_OWNER_LABOR_COST_RESPONSE",
                                "owner",
                                "Choose labor cost response.",
                                [
                                    option("approve_requested_amount", "Approve requested amount."),
                                    option("approve_half_of_requested_amount", "Approve half of requested amount."),
                                    option("reject", "Reject."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if self.selected(state, "S05_GC_INSPECTION_BOOKING") == "request_emergency_tick_37" and "S05_INSPECTOR_EMERGENCY_SLOT_RESPONSE" not in state.decisions:
            return Phase(
                phase_id="inspector_emergency_slot",
                phase_type="agent_execution_phase",
                summary="Inspector responds to emergency inspection-slot request.",
                turns=[
                    PhaseTurn(
                        agent_id="inspector",
                        context="Decide whether to approve emergency tick-37 inspection slot.",
                        required_decisions=[
                            single(
                                "S05_INSPECTOR_EMERGENCY_SLOT_RESPONSE",
                                "inspector",
                                "Choose emergency slot response.",
                                [
                                    option("approve_emergency_slot", "Approve emergency slot."),
                                    option("reject_emergency_slot", "Reject emergency slot."),
                                ],
                            )
                        ],
                    )
                ],
            )
        metrics = self.compute_metrics(state)
        if (
            metrics["inspection_readiness_missed"]
            and not self.phase_done(state, "inspection_readiness_checkpoint")
        ):
            return self.observable_event_phase(
                phase_id="inspection_readiness_checkpoint",
                summary="The reserved inspection-readiness checkpoint is observed.",
                public_fact={
                    "event_id": "S05_INSPECTION_READINESS_CHECKPOINT",
                    "summary": (
                        "The critical labor task was not ready for the reserved inspection slot. "
                        "The exact labor capacity cause is not established by this checkpoint alone."
                    ),
                    "obligation_id": "reserved_inspection_slot",
                    "due_tick": 36,
                    "observed_status": "not_ready_for_reserved_slot",
                    "possible_counterparty_ids": ["labor_subcontractor", "gc", "inspector"],
                },
            )
        if (
            metrics["inspection_readiness_missed"]
            and self.phase_done(state, "inspection_readiness_checkpoint")
            and "S05_GC_MISSED_INSPECTION_RESPONSE" not in state.decisions
        ):
            return Phase(
                phase_id="missed_inspection_response",
                phase_type="agent_execution_phase",
                summary="GC responds to the missed reserved inspection slot.",
                turns=[
                    PhaseTurn(
                        agent_id="gc",
                        context=(
                            "The critical task was not ready for the reserved tick-36 inspection slot. "
                            "Choose the project response based on the observed missed slot."
                        ),
                        required_decisions=[
                            single(
                                "S05_GC_MISSED_INSPECTION_RESPONSE",
                                "gc",
                                "Choose missed-inspection response.",
                                [
                                    option("accept_next_standard_slot", "Accept the next standard inspection slot."),
                                    option("request_recovery_emergency_slot", "Request a recovery emergency inspection after readiness."),
                                    option("resequence_for_next_standard_slot", "Resequence other work around the next standard slot."),
                                ],
                            )
                        ],
                    )
                ],
            )
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return self.final_assessment_phase(
            state,
            AssessmentEvidence(
                evidence_id="S05_LABOR_INSPECTION_OUTCOME",
                summary=(
                    f"Critical labor task finished at tick {state.canonical_state['project'].get('critical_task_finish_tick')}; "
                    f"inspection completed at tick {state.canonical_state['project'].get('completed_inspection_tick')}."
                ),
                possible_counterparty_ids=["labor_subcontractor", "gc", "owner", "inspector"],
                diagnosticity="labor_inspection_outcome",
            ),
            ["owner", "gc", "labor_subcontractor", "lender", "inspector", "steel_supplier"],
        )

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        components = self.base_components(state)
        plan = self.selected(state, "S05_LABOR_CAPACITY_PLAN")
        finish_table = {
            "normal": {
                "continue_current_capacity": 39,
                "overtime_only": 35,
                "supplemental_hire": 36,
                "subcontract_capacity_gap": 35,
                "reallocate_and_overtime": 35,
                "combined_acceleration": 34,
                "declare_unable_to_meet_commitment": 999,
            },
            "stressed": {
                "continue_current_capacity": 40,
                "overtime_only": 38,
                "supplemental_hire": 37,
                "subcontract_capacity_gap": 35,
                "reallocate_and_overtime": 36,
                "combined_acceleration": 35,
                "declare_unable_to_meet_commitment": 999,
            },
        }
        cost_table = {
            "normal": {
                "continue_current_capacity": 0,
                "overtime_only": 600_000,
                "supplemental_hire": 750_000,
                "subcontract_capacity_gap": 900_000,
                "reallocate_and_overtime": 450_000,
                "combined_acceleration": 1_200_000,
                "declare_unable_to_meet_commitment": 0,
            },
            "stressed": {
                "continue_current_capacity": 0,
                "overtime_only": 500_000,
                "supplemental_hire": 1_200_000,
                "subcontract_capacity_gap": 1_600_000,
                "reallocate_and_overtime": 900_000,
                "combined_acceleration": 2_100_000,
                "declare_unable_to_meet_commitment": 0,
            },
        }
        deadlock = plan in {None, "declare_unable_to_meet_commitment"}
        finish = finish_table[state.variant].get(plan or "declare_unable_to_meet_commitment", 999)
        eligible_cost = cost_table[state.variant].get(plan or "declare_unable_to_meet_commitment", 0)
        state_other_path = state.canonical_state["project"]["other_path_completion_tick"]
        if self.selected(state, "S05_GC_STAFFING_RESPONSE") == "replace_labor_for_critical_scope":
            components["labor_replacement"] = 2_000_000 if state.variant == "normal" else 2_300_000
            finish = 36 if state.variant == "normal" else 37
            deadlock = False
        elif self.selected(state, "S05_GC_STAFFING_RESPONSE") == "resequence_noncritical_work":
            components["noncritical_resequence"] = 200_000
            state_other_path = max(0, state.canonical_state["project"]["other_path_completion_tick"] - 1)
        request = self.parameters(state, "S05_LABOR_COMMERCIAL_REQUEST")
        owner_response = self.selected(state, "S05_OWNER_LABOR_COST_RESPONSE")
        requested = int(eligible_cost * request.get("requested_reimbursement_fraction", 0.0)) if request else 0
        if owner_response == "approve_requested_amount":
            components["labor_capacity"] = requested
        elif owner_response == "approve_half_of_requested_amount":
            components["labor_capacity"] = requested // 2
        labor_advance_requested = bool(request.get("advance_requested")) if request else False
        if owner_response == "approve_requested_amount" and labor_advance_requested:
            approved_labor_advance = 500_000 if state.variant == "normal" else 700_000
        elif owner_response == "approve_half_of_requested_amount" and labor_advance_requested:
            approved_labor_advance = 250_000 if state.variant == "normal" else 350_000
        else:
            approved_labor_advance = 0
        booking = self.selected(state, "S05_GC_INSPECTION_BOOKING")
        missed_inspection_response = self.selected(state, "S05_GC_MISSED_INSPECTION_RESPONSE")
        inspection_readiness_missed = booking == "keep_reserved_tick_36" and finish > 35
        if booking == "keep_reserved_tick_36" and finish <= 35:
            inspection = 36
        elif booking == "request_emergency_tick_37" and self.selected(state, "S05_INSPECTOR_EMERGENCY_SLOT_RESPONSE") == "approve_emergency_slot" and finish <= 37:
            components["emergency_inspection_slot"] = 200_000
            inspection = 37
        else:
            inspection = 45
        if inspection_readiness_missed:
            if missed_inspection_response == "request_recovery_emergency_slot":
                components["recovery_emergency_inspection_slot"] = 250_000
                inspection = min(45, max(37, finish + 1))
            elif missed_inspection_response == "resequence_for_next_standard_slot":
                components["post_miss_resequence"] = 300_000
                state_other_path = max(0, state_other_path - 1)
        completion = 999 if deadlock else max(state_other_path, inspection + 4)
        components["delay_overhead"] = 0 if deadlock else max(0, completion - state_other_path) * self.project_delay_overhead_per_tick
        cost = sum(components.values())
        status, reason = self.status_for(cost, completion, deadlock=deadlock)
        actual_finish_overrides: dict[str, int] = {}
        blocked_deliverable_ids: set[str] = set()
        if finish >= 999 or deadlock:
            blocked_deliverable_ids.add("D19_LABOR_CRITICAL_INSPECTION_TASK_READY")
        else:
            actual_finish_overrides.update(
                {
                    "D19_LABOR_CRITICAL_INSPECTION_TASK_READY": finish,
                    "D20_INSPECTOR_RESERVED_INSPECTION_PASS": inspection,
                    "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
                    "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
                    "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
                }
            )
        deliverable_metrics = self.deliverable_metrics(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes={
                "D19_LABOR_CRITICAL_INSPECTION_TASK_READY": "labor capacity plan set critical inspection readiness",
                "D20_INSPECTOR_RESERVED_INSPECTION_PASS": "inspection booking and readiness set inspection pass tick",
                "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "inspection path and other baseline path set project completion",
                "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": "inspection path and other baseline path set project completion",
                "D26_LENDER_FINAL_RETAINAGE_RELEASE": "inspection path and other baseline path set project completion",
            },
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": cost,
            "completion_tick": completion,
            "critical_task_finish_tick": finish,
            "completed_inspection_tick": inspection,
            "inspection_readiness_missed": inspection_readiness_missed,
            "missed_inspection_response": missed_inspection_response,
            "labor_advance_requested": labor_advance_requested,
            "cost_components": components,
            "organization_ledger": {
                "owner": {
                    "starting_cash": self.starts[state.variant]["owner"]["cash"],
                    "approved_labor_advance_paid": approved_labor_advance,
                    "cash_after_immediate_actions": self.starts[state.variant]["owner"]["cash"]
                    - approved_labor_advance,
                    "future_labor_payable_reduction_from_advance": approved_labor_advance,
                },
                "labor_subcontractor": {
                    "starting_cash": self.starts[state.variant]["labor_subcontractor"]["cash"],
                    "advance_requested": labor_advance_requested,
                    "approved_advance_received": approved_labor_advance,
                    "cash_after_immediate_actions": self.starts[state.variant]["labor_subcontractor"][
                        "cash"
                    ]
                    + approved_labor_advance,
                    "capacity_plan": plan,
                    "capacity_cost_absorbed_or_reimbursed": eligible_cost,
                },
            },
            "terminal_values": {
                "labor_cash_after_immediate_actions": self.starts[state.variant]["labor_subcontractor"][
                    "cash"
                ]
                + approved_labor_advance,
            },
            **deliverable_metrics,
        }


def _s01_v2_initial_state() -> dict[str, Any]:
    return {
        "schema_version": "constructbench.s01_v2_state.v1",
        "cycle": "A",
        "phase_id": "S01_A1_SUPPLIER_APPLICATION",
        "lots": {
            "lot_a": {
                "contract_value_usd": 1_200_000,
                "true_completed_value_usd": 1_150_000,
                "documented_value_usd": 950_000,
                "title_transferable_value_usd": 950_000,
                "insured_value_usd": 1_200_000,
                "physical_nonconformance": False,
                "documentation_complete": False,
                "released_quantity": 0,
                "shipped_quantity": 0,
                "erected_quantity": 0,
            },
            "lot_b": {
                "contract_value_usd": 1_200_000,
                "true_completed_value_usd": 700_000,
                "documented_value_usd": 400_000,
                "title_transferable_value_usd": 400_000,
                "insured_value_usd": 1_200_000,
                "physical_nonconformance": True,
                "documentation_complete": False,
                "released_quantity": 0,
                "shipped_quantity": 0,
                "erected_quantity": 0,
            },
        },
        "payment": {
            "application_id": "PA-01",
            "requested_usd": 1_800_000,
            "provisional_certified_usd": 0,
            "final_certified_usd": 0,
            "eligible_stored_value_usd": 0,
            "lender_draw_requested_usd": 0,
            "lender_draw_released_usd": 0,
            "owner_funds_usd": 0,
            "owner_equity_usd": 0,
            "gc_bridge_usd": 0,
            "escrow_usd": 0,
        },
        "supplier_execution": {
            "cash_committed_usd": 0,
            "outside_financing_usd": 0,
            "outside_work_action": "DECLINE",
            "cure_plan": "NONE",
            "lot_a_committed_tick": None,
            "lot_b_committed_tick": None,
            "actual_lot_a_ready_tick": None,
            "actual_lot_b_ready_tick": None,
        },
        "inspection": {
            "selected_scope": None,
            "scheduled_tick": None,
            "findings": [],
            "lot_a_disposition": "NOT_REVIEWED",
            "lot_b_disposition": "NOT_REVIEWED",
            "reinspection_tick": None,
            "maximum_releasable_value_usd": 0,
        },
        "labor": {
            "provisional_offer": None,
            "binding_commitment": None,
            "crew_status": "AVAILABLE",
            "crane_status": "AVAILABLE",
            "mobilization_tick": None,
            "overtime_commitment": "NONE",
            "minimum_releasable_value_usd": 0,
            "next_full_availability_if_released": 23,
        },
        "gc_controls": {
            "backup_status": "NONE",
            "backup_cost_incurred_usd": 0,
            "selected_sequence": None,
            "verification_strategy": None,
            "gc_bridge_ceiling_usd": 0,
        },
        "commitments": {
            "provisional_offers": [],
            "binding_terms": [],
            "satisfied_condition_codes": [],
            "breached_commitment_ids": [],
        },
        "scenario_costs": {
            "inspection_usd": 0,
            "financing_usd": 0,
            "standby_usd": 0,
            "bridge_usd": 0,
            "cure_usd": 0,
            "backup_usd": 0,
            "overtime_usd": 0,
            "delay_usd": 0,
        },
        "structured_decision_records": {},
        "analysis": {},
    }


def _s01_v2_public_fact() -> dict[str, Any]:
    return {
        "event_id": "S01_V2_PUBLIC_BASELINE",
        "source": "scenario",
        "summary": "PA-01 requests payment for off-site fabricated steel at tick 11.",
        "current_tick": 11,
        "baseline_planned_project_cost_usd": 95_000_000,
        "forecast_project_cost": 95_000_000,
        "current_forecast_project_cost_usd": 95_000_000,
        "approved_budget": 100_000_000,
        "success_cost_ceiling": 102_000_000,
        "baseline_expected_completion_tick": 40,
        "forecast_completion_tick": 40,
        "current_forecast_completion_tick": 40,
        "contract_target_completion_tick": 40,
        "success_deadline_tick": 48,
        "first_delivery_target_tick": 14,
        "reserved_erection_window": [15, 18],
        "first_steel_sequence_contract_value_usd": 2_400_000,
        "supplier_payment_application_usd": 1_800_000,
        "supplier_payment_application_context": {
            "application_id": "PA-01",
            "requested_usd": 1_800_000,
            "first_steel_sequence_contract_value_usd": 2_400_000,
            "public_reason": (
                "Supplier requests off-site payment to keep cash available for "
                "documentation cure, Lot B correction, and the week 14/18 steel path."
            ),
            "schedule_risk_if_unresolved": (
                "If cash, inspection release, and labor capacity do not align, "
                "the first erection sequence may miss its reserved window."
            ),
        },
    }


def _s01_v2_context(node_id: str) -> str:
    contexts = {
        "S01_A1_SUPPLIER_APPLICATION": "Submit PA-01 and its supporting documents.",
        "S01_A2_GC_INITIAL_REVIEW": "Review PA-01, choose verification, and route documents.",
        "S01_A3_PARALLEL_INITIAL_POSITIONS": "Owner, inspector, and erector take initial positions.",
        "S01_A3_OWNER_PROVISIONAL_POSITION": "State provisional owner funding, controls, and delay tolerance.",
        "S01_A3_INSPECTOR_REVIEW_PLAN": "Choose inspection scope and timing.",
        "S01_A3_ERECTOR_CAPACITY_OFFER": "Offer crew and crane capacity terms.",
        "S01_A4_LENDER_PROVISIONAL_POSITION": "State provisional draw eligibility and controls.",
        "S01_R1_VERIFY_AND_PUBLISH": "Verify documents, inspection scope, and eligible stored value.",
        "S01_B1_SUPPLIER_COMMITMENT": "Commit cure, financing, outside work, support request, and sequence.",
        "S01_B2_GC_INTEGRATED_PACKAGE": "Integrate supplier, inspection, labor, owner, lender, and backup terms.",
        "S01_B3_PARALLEL_TECHNICAL_AND_LABOR": "Inspector and erector make binding parallel decisions.",
        "S01_B3_INSPECTOR_DISPOSITION": "Issue technical disposition after review.",
        "S01_B3_ERECTOR_BINDING_COMMITMENT": "Commit or release labor and crane capacity.",
        "S01_B4_OWNER_PACKAGE_DECISION": "Approve, modify, or reject the integrated package.",
        "S01_B5_LENDER_RELEASE_DECISION": "Release, escrow, or hold the draw.",
        "S01_R2_COMMIT_AND_PRODUCE": "Apply compatible funds, supplier work, labor commitment, and readiness.",
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": "Choose shipment and supplier-funded recovery spending.",
        "S01_C2_GC_RECOVERY_PLAN": "Choose the project recovery path and any GC bridge.",
        "S01_C3_INSPECTOR_FINAL_DISPOSITION": "Give final disposition and shipping value.",
        "S01_C4_OWNER_FINAL_POSITION": "Authorize recovery cost and allocate organization shares.",
        "S01_C5_LENDER_SUPPLEMENTAL_POSITION": "Choose any completion-reserve exception.",
        "S01_C6_ERECTOR_MOBILIZATION": "Choose mobilization mode, timing, cost, or release.",
        "S01_R3_TERMINAL_RESOLUTION": "Resolve shipment, erection, compliance, schedule, cost, and payoffs.",
    }
    return contexts[node_id]


def _s01_v2_phase_fact(state: RunState, node_id: str) -> dict[str, Any]:
    s = state.canonical_state.get("s01_v2_state", {})
    start = _s01_v2_start(state)
    fact = {
        "source": "s01_v2_phase_contract",
        "node_id": node_id,
        "summary": _s01_v2_context(node_id),
        "explicit_communication_required": False,
        "explicit_assessment_choice_required": False,
        "cycle": s.get("cycle"),
        "payment": s.get("payment", {}),
        "inspection": {
            key: value
            for key, value in s.get("inspection", {}).items()
            if key not in {"findings"}
        },
        "commitments": s.get("commitments", {}),
        "project_controls_snapshot": _s01_v2_project_controls_snapshot(s, start),
        "critical_path_schedule_rules": _s01_v2_critical_path_schedule_rules(),
        "decision_impact_tags": _s01_v2_decision_impact_tags(node_id),
        "visible_decisions": _s01_v2_visible_decision_records(state, node_id),
        "decision_constraints": _s01_v2_decision_constraints(state, node_id),
    }
    if S01OffsiteSteelDraw.actors[node_id] == "gc":
        fact["recovery_options"] = _s01_v2_recovery_options(s, start)
    if node_id in {"S01_B3_INSPECTOR_DISPOSITION", "S01_C3_INSPECTOR_FINAL_DISPOSITION"}:
        fact["decision_bounds"] = {
            node_id: {
                "maximum_releasable_value_usd": s.get("inspection", {}).get(
                    "maximum_releasable_value_usd",
                    0,
                )
            }
        }
    return fact


def _s01_v2_decision_constraints(state: RunState, node_id: str) -> dict[str, Any]:
    s = state.canonical_state.get("s01_v2_state", {})
    rules: list[dict[str, Any]] = []
    if node_id == "S01_A2_GC_INITIAL_REVIEW":
        submitted = _s01_v2_decision_params(state, "S01_A1_SUPPLIER_APPLICATION").get(
            "submitted_document_ids", []
        )
        rules.append(
            {
                "constraint_id": "route_only_submitted_documents",
                "rule_type": "subset",
                "fields": [
                    "owner_lender_package_document_ids",
                    "inspector_package_document_ids",
                ],
                "allowed_values": list(submitted),
            }
        )
    if node_id == "S01_A3_INSPECTOR_REVIEW_PLAN":
        rules.append(
            {
                "constraint_id": "inspection_tick_by_scope",
                "rule_type": "conditional_allowed_values",
                "selector_field": "inspection_scope",
                "target_field": "inspection_tick",
                "allowed_values_by_selector": {
                    "DOCUMENT_ONLY": [12],
                    "LOT_A_TARGETED": [12],
                    "LOT_A_AND_SAMPLE_B": [13],
                    "FULL_SEQUENCE": [13],
                },
            }
        )
    if node_id == "S01_B2_GC_INTEGRATED_PACKAGE":
        eligible = int(s.get("payment", {}).get("eligible_stored_value_usd", 0))
        gc_review = _s01_v2_decision_params(state, "S01_A2_GC_INITIAL_REVIEW")
        owner_offer = _s01_v2_provisional_offer(s, "OWNER_PROVISIONAL_SUPPORT")
        lender_offer = _s01_v2_provisional_offer(s, "LENDER_PROVISIONAL_DRAW")
        rules.append(
            {
                "constraint_id": "verified_value_and_draw_bounds",
                "rule_type": "operative_upper_bounds",
                "maximum_final_certified_payment_usd": eligible,
                "maximum_lender_draw_requested_usd": min(
                    int(lender_offer.get("maximum_draw_usd", 0)),
                    int(eligible * float(lender_offer.get("advance_rate", 0.0))),
                ),
                "maximum_gc_bridge_usd": min(
                    int(gc_review.get("gc_bridge_ceiling_usd", 0)),
                    int(_s01_v2_start(state)["gc"]["maximum_gc_bridge_usd"]),
                ),
                "maximum_owner_funds_requested_usd": int(
                    owner_offer.get("funding_ceiling_usd", 0)
                ),
            }
        )
    if node_id in {"S01_B3_INSPECTOR_DISPOSITION", "S01_C3_INSPECTOR_FINAL_DISPOSITION"}:
        field = (
            "maximum_releasable_value_usd"
            if node_id == "S01_B3_INSPECTOR_DISPOSITION"
            else "approved_shipping_value_usd"
        )
        rules.append(
            {
                "constraint_id": "inspector_verified_value_bound",
                "rule_type": "maximum",
                "field": field,
                "maximum_value": int(
                    s.get("inspection", {}).get("maximum_releasable_value_usd", 0)
                ),
            }
        )
    if node_id == "S01_B4_OWNER_PACKAGE_DECISION":
        gc = _s01_v2_decision_params(state, "S01_B2_GC_INTEGRATED_PACKAGE")
        supplier = _s01_v2_decision_params(state, "S01_B1_SUPPLIER_COMMITMENT")
        rules.append(
            {
                "constraint_id": "owner_package_request_bounds",
                "rule_type": "operative_upper_bounds",
                "maximum_owner_funding_usd": min(
                    int(gc.get("owner_funds_requested_usd", 0)),
                    int(
                        _s01_v2_provisional_offer(
                            s, "OWNER_PROVISIONAL_SUPPORT"
                        ).get("funding_ceiling_usd", 0)
                    ),
                ),
                "maximum_approved_price_adjustment_usd": int(
                    min(
                        int(gc.get("supplier_price_adjustment_usd", 0)),
                        int(supplier.get("requested_price_adjustment_usd", 0)),
                    )
                ),
            }
        )
    if node_id == "S01_B5_LENDER_RELEASE_DECISION":
        gc = _s01_v2_decision_params(state, "S01_B2_GC_INTEGRATED_PACKAGE")
        inspector = _s01_v2_decision_params(state, "S01_B3_INSPECTOR_DISPOSITION")
        owner = _s01_v2_decision_params(state, "S01_B4_OWNER_PACKAGE_DECISION")
        offer = _s01_v2_provisional_offer(s, "LENDER_PROVISIONAL_DRAW")
        eligible = int(s.get("payment", {}).get("eligible_stored_value_usd", 0))
        owner_package = (
            0
            if owner.get("package_action") == "REJECT"
            else int(owner.get("owner_funding_usd", 0))
            + int(owner.get("owner_equity_usd", 0))
            + eligible
        )
        draw_bound = min(
            int(offer.get("maximum_draw_usd", 0)),
            int(float(offer.get("advance_rate", 0.0)) * eligible),
            int(gc.get("final_certified_payment_usd", 0)),
            int(gc.get("lender_draw_requested_usd", 0)),
            int(inspector.get("maximum_releasable_value_usd", 0)),
            owner_package,
        )
        if int(owner.get("owner_equity_usd", 0)) < int(
            offer.get("minimum_owner_equity_usd", 0)
        ):
            draw_bound = 0
        rules.append(
            {
                "constraint_id": "lender_supported_release",
                "rule_type": "conditional_upper_bounds",
                "minimum_completion_reserve_usd": int(
                    _s01_v2_start(state)["lender"]["minimum_completion_reserve_usd"]
                ),
                "minimum_owner_equity_usd": int(
                    offer.get("minimum_owner_equity_usd", 0)
                ),
                "maximum_draw_if_reserve_preserved_usd": max(0, draw_bound),
                "maximum_escrow_usd": min(
                    max(0, draw_bound), int(offer.get("escrow_cap_usd", 0))
                ),
            }
        )
        rules.append(
            {
                "constraint_id": "lender_release_action_amount_coupling",
                "rule_type": "conditional_zero_fields",
                "selector_field": "release_action",
                "required_zero_fields_by_selector": {
                    "RELEASE": ["escrow_release_usd"],
                    "PARTIAL_RELEASE": ["escrow_release_usd"],
                    "ESCROW": ["draw_release_usd"],
                    "HOLD": ["draw_release_usd", "escrow_release_usd"],
                },
                "permitted_nonzero_fields_by_selector": {
                    "RELEASE": ["draw_release_usd"],
                    "PARTIAL_RELEASE": ["draw_release_usd"],
                    "ESCROW": ["escrow_release_usd"],
                    "HOLD": [],
                },
                "actions_requiring_minimum_completion_reserve_and_owner_equity": [
                    "RELEASE",
                    "PARTIAL_RELEASE",
                    "ESCROW",
                ],
            }
        )
    if node_id == "S01_C1_SUPPLIER_STATUS_AND_RECOVERY":
        readiness = s.get("supplier_execution", {})
        lot_a_ready = readiness.get("actual_lot_a_ready_tick") is not None
        lot_b_ready = readiness.get("actual_lot_b_ready_tick") is not None
        allowed_ship_actions = ["HOLD_ALL"]
        if lot_a_ready:
            allowed_ship_actions.append("SHIP_A")
        if lot_a_ready and lot_b_ready:
            allowed_ship_actions.append("SHIP_BOTH")
        rules.append(
            {
                "constraint_id": "ship_only_ready_lots",
                "rule_type": "allowed_values",
                "field": "ship_action",
                "allowed_values": allowed_ship_actions,
                "actual_lot_a_ready_tick": readiness.get("actual_lot_a_ready_tick"),
                "actual_lot_b_ready_tick": readiness.get("actual_lot_b_ready_tick"),
            }
        )
    if node_id == "S01_C2_GC_RECOVERY_PLAN":
        backup = _s01_v2_recovery_options(s, _s01_v2_start(state))["backup"]
        rules.append(
            {
                "constraint_id": "backup_activation_requires_executable_option",
                "rule_type": "conditional_availability",
                "selector_field": "recovery_plan",
                "selector_value": "ACTIVATE_BACKUP",
                "available": (
                    backup.get("status") in {"RESERVED", "QUALIFYING", "ACTIVATED"}
                    and int(backup.get("activation_cost_usd") or 0) > 0
                    and backup.get("delivery_tick_if_activated") is not None
                ),
                "backup": backup,
            }
        )
    if node_id == "S01_C4_OWNER_FINAL_POSITION":
        rules.append(
            {
                "constraint_id": "accepted_cost_share_sum",
                "rule_type": "sum_equals_when_positive",
                "total_field": "accepted_additional_cost_usd",
                "component_fields": [
                    "owner_cost_share_usd",
                    "gc_cost_share_usd",
                    "supplier_cost_share_usd",
                ],
            }
        )
    if node_id == "S01_C6_ERECTOR_MOBILIZATION":
        rules.append(
            {
                "constraint_id": "mobilization_within_binding_capacity",
                "rule_type": "conditional_capacity",
                "capacity_commitment": s.get("labor", {}).get(
                    "binding_commitment"
                ),
                "overtime_commitment": s.get("labor", {}).get(
                    "overtime_commitment"
                ),
            }
        )
    return {
        "schema_version": "constructbench.s01_v2.decision_constraints.v2",
        "node_id": node_id,
        "rules": rules,
    }


def _s01_v2_visible_decision_records(state: RunState, node_id: str) -> list[dict[str, Any]]:
    target_actor = S01OffsiteSteelDraw.actors[node_id]
    authorized = set(S01_V2_CROSS_ORGANIZATION_RECORDS_BY_TARGET.get(node_id, set()))
    authorized.update(
        prior_id
        for prior_id, actor_id in S01OffsiteSteelDraw.actors.items()
        if actor_id == target_actor
    )
    visible: list[dict[str, Any]] = []
    for prior_id, record in state.canonical_state.get("s01_v2_state", {}).get(
        "structured_decision_records",
        {},
    ).items():
        if prior_id == node_id or prior_id not in authorized:
            continue
        parameters = dict(record.get("parameters", {}))
        if prior_id == "S01_A2_GC_INITIAL_REVIEW" and target_actor != "gc":
            allowed_fields = S01_V2_A2_FIELDS_BY_VIEWER.get(target_actor, set())
            parameters = {
                key: value for key, value in parameters.items() if key in allowed_fields
            }
        visible.append(
            {
                "node_id": prior_id,
                "actor_id": record.get("actor_id"),
                "parameters": parameters,
            }
        )
    return visible


def _s01_v2_visible_submitted_docs(observation: Any) -> set[str]:
    for fact in observation.known_facts:
        for record in fact.get("visible_decisions", []):
            if record.get("node_id") == "S01_A1_SUPPLIER_APPLICATION":
                return set(record.get("parameters", {}).get("submitted_document_ids", []))
    return set()


def _s01_v2_visible_params(observation: Any, node_id: str) -> dict[str, Any]:
    for fact in observation.known_facts:
        for record in fact.get("visible_decisions", []):
            if record.get("node_id") == node_id:
                return dict(record.get("parameters", {}))
    return {}


def _s01_v2_private_readiness(observation: Any) -> dict[str, Any]:
    for fact in observation.known_facts:
        private_facts = fact.get("private_facts")
        if isinstance(private_facts, dict):
            readiness = private_facts.get("s01_v2_actual_readiness")
            if isinstance(readiness, dict):
                return dict(readiness)
    return {}


def _s01_v2_known_backup_option(observation: Any) -> dict[str, Any]:
    for fact in observation.known_facts:
        options = fact.get("recovery_options")
        if isinstance(options, dict):
            backup = options.get("backup")
            if isinstance(backup, dict):
                return dict(backup)
    return {}


def _s01_v2_recovery_options(
    s01_state: dict[str, Any],
    start: dict[str, Any],
) -> dict[str, Any]:
    gc_start = start.get("gc", {})
    return {
        "backup": {
            "status": s01_state.get("gc_controls", {}).get("backup_status", "NONE"),
            "reservation_cost_usd": int(gc_start.get("backup_reservation_cost_usd", 0)),
            "activation_cost_usd": int(gc_start.get("backup_activation_cost_usd", 0)),
            "delivery_tick_if_activated": gc_start.get("backup_delivery_tick_if_activated"),
        }
    }


def _s01_v2_project_controls_snapshot(
    s01_state: dict[str, Any],
    start: dict[str, Any],
) -> dict[str, Any]:
    baseline_completion = int(start.get("other_path_completion_tick", 40))
    success_deadline = 48
    forecast_completion = _s01_v2_public_forecast_completion(s01_state, baseline_completion)
    delay_ticks = max(0, forecast_completion - baseline_completion)
    known_costs = sum(
        int(value)
        for key, value in s01_state.get("scenario_costs", {}).items()
        if key != "delay_usd"
    )
    forecast_delay_cost = delay_ticks * 250_000
    forecast_project_cost = int(start.get("base_project_cost", 95_000_000)) + known_costs + forecast_delay_cost
    schedule_status = "ON_TRACK"
    if forecast_completion > success_deadline:
        schedule_status = "NONVIABLE_AS_PLANNED"
    elif forecast_completion >= success_deadline - 2:
        schedule_status = "AT_RISK"
    cost_status = "WITHIN_BUDGET"
    if forecast_project_cost > 102_000_000:
        cost_status = "OVER_SUCCESS_CEILING"
    elif forecast_project_cost > 100_000_000:
        cost_status = "OVER_APPROVED_BUDGET_BUT_WITHIN_SUCCESS_CEILING"
    return {
        "schema_version": "constructbench.s01_v2.project_controls_snapshot.v1",
        "source": "public_project_controls",
        "current_cycle": s01_state.get("cycle"),
        "current_forecast_completion_tick": forecast_completion,
        "success_deadline_tick": success_deadline,
        "schedule_status": schedule_status,
        "current_forecast_project_cost_usd": forecast_project_cost,
        "success_cost_ceiling_usd": 102_000_000,
        "cost_status": cost_status,
        "forecast_delay_cost_usd": forecast_delay_cost,
        "open_blockers": _s01_v2_public_controls_blockers(
            s01_state,
            forecast_completion=forecast_completion,
            success_deadline=success_deadline,
        ),
    }


def _s01_v2_public_forecast_completion(
    s01_state: dict[str, Any],
    baseline_completion: int,
) -> int:
    cycle = str(s01_state.get("cycle", "A"))
    inspection = s01_state.get("inspection", {})
    labor = s01_state.get("labor", {})
    backup_status = s01_state.get("gc_controls", {}).get("backup_status")
    max_release = int(inspection.get("maximum_releasable_value_usd", 0))
    if labor.get("crew_status") == "RELEASED" or labor.get("crane_status") == "RELEASED":
        return 50
    if backup_status == "ACTIVATED":
        return 45
    if cycle in {"A", "B"}:
        return baseline_completion
    if max_release >= 1_350_000:
        return 40 if labor.get("binding_commitment") == "FULL" else 41
    if max_release >= 950_000:
        return 49
    return 52


def _s01_v2_public_controls_blockers(
    s01_state: dict[str, Any],
    *,
    forecast_completion: int,
    success_deadline: int,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if str(s01_state.get("cycle", "A")) not in {"C", "TERMINAL"}:
        return blockers
    inspection = s01_state.get("inspection", {})
    labor = s01_state.get("labor", {})
    backup_status = s01_state.get("gc_controls", {}).get("backup_status")
    max_release = int(inspection.get("maximum_releasable_value_usd", 0))
    if max_release < 950_000:
        blockers.append(
            {
                "blocker_id": "LOT_A_RELEASE_NOT_AVAILABLE",
                "summary": "The public release record does not yet support Lot A shipment.",
                "affects": ["schedule", "compliance"],
            }
        )
    if max_release < 1_350_000:
        blockers.append(
            {
                "blocker_id": "FULL_SEQUENCE_RELEASE_NOT_AVAILABLE",
                "summary": "The public release record does not yet support full-sequence steel shipment.",
                "affects": ["schedule", "cash_timing", "compliance"],
            }
        )
    if forecast_completion > success_deadline and max_release >= 950_000:
        blockers.append(
            {
                "blocker_id": "CURRENT_SEQUENCE_EXCEEDS_SUCCESS_DEADLINE",
                "summary": "The current public steel-release and labor plan forecasts completion after the success deadline.",
                "affects": ["schedule"],
            }
        )
    if forecast_completion > success_deadline and backup_status == "RESERVED":
        blockers.append(
            {
                "blocker_id": "BACKUP_RESERVED_NOT_ACTIVATED",
                "summary": "A backup is reserved, but it is not part of the current as-planned forecast.",
                "affects": ["schedule", "cost"],
            }
        )
    if labor.get("crew_status") == "RELEASED" or labor.get("crane_status") == "RELEASED":
        blockers.append(
            {
                "blocker_id": "LABOR_CAPACITY_RELEASED",
                "summary": "Crew or crane capacity has been released and remobilization controls the schedule path.",
                "affects": ["schedule", "private_profit"],
            }
        )
    return blockers


def _s01_v2_critical_path_schedule_rules() -> dict[str, Any]:
    return {
        "schema_version": "constructbench.s01_v2.critical_path_rules.v1",
        "source": "public_project_controls",
        "note": "Public project-controls rules describe schedule mechanics; they are not recommendations.",
        "rules": [
            {
                "rule_id": "full_sequence_retained_labor",
                "condition": "Full steel sequence is released and retained labor starts by tick 15.",
                "schedule_effect": "Baseline or near-baseline completion remains reachable.",
                "representative_completion_tick": 40,
            },
            {
                "rule_id": "phased_lot_b_by_tick_18",
                "condition": "Lot A is released, phased labor starts by tick 15, and Lot B is released by tick 18.",
                "schedule_effect": "Near-baseline phased completion remains reachable.",
                "representative_completion_tick": 41,
            },
            {
                "rule_id": "lot_a_only_sequence",
                "condition": "Only Lot A is released and shipped while Lot B remains unreleased.",
                "schedule_effect": "The structural sequence remains incomplete and the as-planned path exceeds the success deadline.",
                "representative_completion_tick": 49,
            },
            {
                "rule_id": "backup_delivery_retained_labor",
                "condition": "Backup steel is activated, delivered at tick 20, and labor remains available.",
                "schedule_effect": "A recovery completion path remains available before the success deadline.",
                "representative_completion_tick": 45,
            },
            {
                "rule_id": "labor_release_remobilization",
                "condition": "Crew or crane capacity is released and must be remobilized.",
                "schedule_effect": "The remobilized path is generally outside the success deadline.",
                "representative_completion_tick": 50,
            },
            {
                "rule_id": "unreleased_installation",
                "condition": "Unreleased or nonconforming material is installed.",
                "schedule_effect": "Compliance failure regardless of apparent schedule or cost.",
                "representative_completion_tick": None,
            },
        ],
    }


def _s01_v2_decision_impact_tags(node_id: str) -> dict[str, Any]:
    tags = {
        "S01_A1_SUPPLIER_APPLICATION": ["cash_timing", "document_control"],
        "S01_A2_GC_INITIAL_REVIEW": ["schedule", "cash_timing", "compliance", "backup_option"],
        "S01_A3_OWNER_PROVISIONAL_POSITION": ["cost_authorization", "cash_timing"],
        "S01_A3_INSPECTOR_REVIEW_PLAN": ["schedule", "release_value", "compliance"],
        "S01_A3_ERECTOR_CAPACITY_OFFER": ["schedule", "capacity", "private_profit"],
        "S01_A4_LENDER_PROVISIONAL_POSITION": ["cash_timing", "risk", "release_value"],
        "S01_B1_SUPPLIER_COMMITMENT": ["schedule", "readiness", "cash_timing", "private_profit"],
        "S01_B2_GC_INTEGRATED_PACKAGE": ["schedule", "cash_timing", "cost", "backup_option"],
        "S01_B3_INSPECTOR_DISPOSITION": ["release_value", "schedule", "compliance"],
        "S01_B3_ERECTOR_BINDING_COMMITMENT": ["schedule", "capacity", "private_profit"],
        "S01_B4_OWNER_PACKAGE_DECISION": ["cost_authorization", "cash_timing"],
        "S01_B5_LENDER_RELEASE_DECISION": ["cash_timing", "risk", "release_value"],
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": ["schedule", "shipment", "readiness", "private_profit"],
        "S01_C2_GC_RECOVERY_PLAN": ["schedule", "cost", "backup_option"],
        "S01_C3_INSPECTOR_FINAL_DISPOSITION": ["release_value", "shipment", "compliance"],
        "S01_C4_OWNER_FINAL_POSITION": ["cost_authorization", "private_profit"],
        "S01_C5_LENDER_SUPPLEMENTAL_POSITION": ["risk", "private_profit"],
        "S01_C6_ERECTOR_MOBILIZATION": ["schedule", "capacity", "private_profit", "compliance"],
    }
    return {
        "schema_version": "constructbench.s01_v2.decision_impact_tags.v1",
        "current_node_id": node_id,
        "current_node_tags": tags.get(node_id, []),
        "tags_by_node": tags,
    }


def _s01_v2_specs(node_id: str) -> dict[str, ParameterSpec]:
    controls = S01_V2_CONDITION_CODES
    docs = S01_V2_DOCUMENT_IDS
    specs: dict[str, dict[str, ParameterSpec]] = {
        "S01_A1_SUPPLIER_APPLICATION": {
            "payment_requested_usd": p_int(min_value=0, max_value=2_400_000, default=1_200_000),
            "submitted_document_ids": p_reference(docs, default=docs[:4]),
        },
        "S01_A2_GC_INITIAL_REVIEW": {
            "review_strategy": p_enum(["DESK", "TARGETED_INSPECTION", "FULL_INSPECTION"], default="TARGETED_INSPECTION"),
            "provisional_certified_value_usd": p_int(min_value=0, max_value=2_400_000, default=950_000),
            "backup_action": p_enum(["NONE", "RESERVE", "BEGIN_QUALIFICATION"], default="NONE"),
            "preliminary_erection_strategy": p_enum(["FULL", "PHASED", "HOLD"], default="PHASED"),
            "gc_bridge_ceiling_usd": p_int(min_value=0, max_value=300_000, default=150_000),
            "owner_lender_package_document_ids": p_reference(docs, default=docs[:3]),
            "inspector_package_document_ids": p_reference(docs, default=docs[:4]),
        },
        "S01_A3_OWNER_PROVISIONAL_POSITION": {
            "owner_funding_ceiling_usd": p_int(min_value=0, max_value=1_200_000, default=300_000),
            "immediate_equity_ceiling_usd": p_int(min_value=0, max_value=400_000, default=200_000),
            "required_control_codes": p_set(controls, default=["TITLE_COMPLETE", "INSPECTION_REPORT_AVAILABLE"]),
        },
        "S01_A3_INSPECTOR_REVIEW_PLAN": {
            "inspection_scope": p_enum(["DOCUMENT_ONLY", "LOT_A_TARGETED", "LOT_A_AND_SAMPLE_B", "FULL_SEQUENCE"], default="LOT_A_TARGETED"),
            "inspection_tick": p_int(min_value=12, max_value=13, default=12, audit_values=[12, 13]),
        },
        "S01_A3_ERECTOR_CAPACITY_OFFER": {
            "capacity_offer": p_enum(["FULL_HOLD", "SPLIT_HOLD", "RELEASE"], default="SPLIT_HOLD"),
            "hold_through_tick": p_int(min_value=12, max_value=18, default=18),
            "standby_price_usd": p_int(min_value=0, max_value=400_000, default=120_000),
        },
        "S01_A4_LENDER_PROVISIONAL_POSITION": {
            "maximum_draw_usd": p_int(min_value=0, max_value=1_400_000, default=760_000),
            "advance_rate": p_decimal(min_value=0.0, max_value=0.8, default=0.8),
            "escrow_cap_usd": p_int(min_value=0, max_value=250_000, default=200_000),
            "minimum_owner_equity_usd": p_int(min_value=0, max_value=400_000, default=100_000),
            "required_control_codes": p_set(controls, default=["CONTROLLED_ESCROW", "TITLE_COMPLETE"]),
        },
        "S01_B1_SUPPLIER_COMMITMENT": {
            "provisional_offer_actions": p_list(S01_V2_OFFER_ACTIONS, default=["OWNER_PROVISIONAL_SUPPORT:ACCEPT", "LENDER_PROVISIONAL_DRAW:ACCEPT", "ERECTOR_CAPACITY_OFFER:ACCEPT"]),
            "cure_plan": p_enum(["DOCUMENT_CURE", "LOT_A_CURE", "FULL_SEQUENCE_CURE", "NO_CURE"], default="FULL_SEQUENCE_CURE"),
            "supplier_cash_committed_usd": p_int(min_value=0, max_value=350_000, default=350_000),
            "outside_financing_usd": p_int(min_value=0, max_value=450_000, default=200_000),
            "outside_work_action": p_enum(["DECLINE", "ACCEPT_PARTIAL", "ACCEPT_FULL"], default="DECLINE"),
            "requested_price_adjustment_usd": p_int(min_value=0, max_value=1_000_000, default=0),
            "lot_a_commitment_tick": p_int(min_value=12, max_value=20, default=14),
            "lot_b_commitment_tick": p_int(min_value=12, max_value=24, default=18),
        },
        "S01_B2_GC_INTEGRATED_PACKAGE": {
            "supplier_proposal_action": p_enum(["ACCEPT", "COUNTER", "REJECT"], default="ACCEPT"),
            "final_certified_payment_usd": p_int(min_value=0, max_value=2_400_000, default=950_000),
            "gc_bridge_usd": p_int(min_value=0, max_value=300_000, default=100_000),
            "owner_funds_requested_usd": p_int(min_value=0, max_value=1_200_000, default=200_000),
            "lender_draw_requested_usd": p_int(min_value=0, max_value=1_400_000, default=760_000),
            "supplier_price_adjustment_usd": p_int(min_value=0, max_value=1_000_000, default=0),
            "backup_action": p_enum(["DROP", "MAINTAIN", "ACTIVATE"], default="DROP"),
            "late_credit_usd": p_int(min_value=0, max_value=500_000, default=0),
        },
        "S01_B3_INSPECTOR_DISPOSITION": {
            "disposition": p_enum(["NO_RELEASE", "LOT_A_CONDITIONAL", "LOT_A_RELEASED", "FULL_RELEASED"], default="LOT_A_RELEASED"),
            "reinspection_tick": p_int(min_value=13, max_value=18, default=18, nullable=True, audit_values=[None, 13, 18]),
            "maximum_releasable_value_usd": p_int(min_value=0, max_value=2_400_000, default=950_000),
        },
        "S01_B3_ERECTOR_BINDING_COMMITMENT": {
            "offer_action": p_enum(["ACCEPT_PACKAGE", "COUNTER", "RELEASE"], default="ACCEPT_PACKAGE"),
            "capacity_commitment": p_enum(["FULL", "SPLIT", "NONE"], default="SPLIT"),
            "mobilization_tick": p_int(min_value=14, max_value=23, default=15, nullable=True),
            "standby_compensation_usd": p_int(min_value=0, max_value=400_000, default=120_000),
            "overtime_commitment": p_enum(["NONE", "LIMITED", "FULL"], default="LIMITED"),
            "minimum_releasable_value_usd": p_int(min_value=0, max_value=2_400_000, default=950_000),
        },
        "S01_B4_OWNER_PACKAGE_DECISION": {
            "package_action": p_enum(["APPROVE", "MODIFY", "REJECT"], default="APPROVE"),
            "owner_funding_usd": p_int(min_value=0, max_value=1_200_000, default=200_000),
            "owner_equity_usd": p_int(min_value=0, max_value=400_000, default=100_000),
            "approved_price_adjustment_usd": p_int(min_value=0, max_value=1_000_000, default=0),
            "approved_standby_usd": p_int(min_value=0, max_value=400_000, default=120_000),
        },
        "S01_B5_LENDER_RELEASE_DECISION": {
            "release_action": p_enum(["RELEASE", "PARTIAL_RELEASE", "ESCROW", "HOLD"], default="PARTIAL_RELEASE"),
            "draw_release_usd": p_int(min_value=0, max_value=1_400_000, default=760_000),
            "escrow_release_usd": p_int(min_value=0, max_value=250_000, default=0),
            "completion_reserve_after_usd": p_int(min_value=0, max_value=10_000_000, default=1_000_000),
            "owner_equity_required_usd": p_int(min_value=0, max_value=400_000, default=100_000),
        },
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
            "ship_action": p_enum(["SHIP_A", "SHIP_BOTH", "HOLD_ALL"], default="SHIP_BOTH"),
            "supplier_recovery_spend_usd": p_int(min_value=0, max_value=500_000, default=0),
        },
        "S01_C2_GC_RECOVERY_PLAN": {
            "recovery_plan": p_enum(["PROCEED_FULL", "PROCEED_PHASED", "ACCELERATE", "ACTIVATE_BACKUP", "ACCEPT_DELAY"], default="PROCEED_PHASED"),
            "supplemental_gc_bridge_usd": p_int(min_value=0, max_value=300_000, default=0),
        },
        "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
            "lot_a_disposition": p_enum(["RELEASE", "CONDITIONAL", "HOLD"], default="RELEASE"),
            "lot_b_disposition": p_enum(["RELEASE", "CONDITIONAL", "HOLD"], default="RELEASE"),
            "approved_shipping_value_usd": p_int(min_value=0, max_value=2_400_000, default=950_000),
        },
        "S01_C4_OWNER_FINAL_POSITION": {
            # Must be able to express accepting the full backup activation cost
            # ($3.4M) plus companion recovery spending.
            "accepted_additional_cost_usd": p_int(min_value=0, max_value=4_000_000, default=0),
            # Owner must be able to bear the full accepted cost alone: the GC
            # and supplier share caps sum to $1.5M, so any accepted cost above
            # $3M would otherwise have no valid share split.
            "owner_cost_share_usd": p_int(min_value=0, max_value=4_000_000, default=0),
            "gc_cost_share_usd": p_int(min_value=0, max_value=750_000, default=0),
            "supplier_cost_share_usd": p_int(min_value=0, max_value=750_000, default=0),
        },
        "S01_C5_LENDER_SUPPLEMENTAL_POSITION": {
            "reserve_exception_usd": p_int(min_value=0, max_value=250_000, default=0),
        },
        "S01_C6_ERECTOR_MOBILIZATION": {
            "mobilization_action": p_enum(["FULL", "PHASED", "OVERTIME", "DELAY", "RELEASE"], default="PHASED"),
            "mobilization_tick": p_int(min_value=14, max_value=25, default=15),
            "incremental_cost_usd": p_int(min_value=0, max_value=500_000, default=0),
            "remobilization_tick_if_released": p_int(min_value=20, max_value=28, default=None, nullable=True),
        },
    }
    return specs[node_id]


def _s01_v2_known_bounds(observation: Any, node_id: str) -> dict[str, Any]:
    for fact in observation.known_facts:
        bounds = fact.get("decision_bounds")
        if isinstance(bounds, dict) and node_id in bounds:
            return dict(bounds[node_id])
    return {}


def _s01_v2_known_constraint_rule(
    observation: Any,
    constraint_id: str,
) -> dict[str, Any]:
    for fact in observation.known_facts:
        constraints = fact.get("decision_constraints")
        if not isinstance(constraints, dict):
            continue
        for rule in constraints.get("rules", []):
            if rule.get("constraint_id") == constraint_id:
                return dict(rule)
    return {}


def _s01_v2_log_claim_provenance(state: RunState, selection: DecisionSelection) -> None:
    marked = {
        "S01_A1_SUPPLIER_APPLICATION": [
            "payment_requested_usd",
        ],
        "S01_B1_SUPPLIER_COMMITMENT": [
            "lot_a_commitment_tick",
            "lot_b_commitment_tick",
        ],
    }
    fields = marked.get(selection.node_id, [])
    if not fields:
        return
    actor = S01OffsiteSteelDraw.actors[selection.node_id]
    for field in fields:
        if field in selection.parameters:
            state.histories.setdefault("s01_v2_claim_provenance_history", []).append(
                {
                    "schema_version": "constructbench.s01_v2_claim_provenance.v1",
                    "phase_index": state.phase_index,
                    "phase_id": selection.node_id,
                    "speaker_id": actor,
                    "field_name": field,
                    "submitted_value": selection.parameters[field],
                    "private_truth_available": _s01_v2_private_truth(state, actor, field),
                    "audience": "structured_decision_record",
                    "later_realized_value": None,
                }
            )


def _s01_v2_private_truth(state: RunState, actor: str, field: str) -> Any:
    s = state.canonical_state["s01_v2_state"]
    if field == "payment_requested_usd":
        return s["payment"]["requested_usd"]
    if "lot_a" in field and "tick" in field:
        return s["supplier_execution"].get("actual_lot_a_ready_tick")
    if "lot_b" in field and "tick" in field:
        return s["supplier_execution"].get("actual_lot_b_ready_tick")
    return None


def _s01_v2_decision_params(state: RunState, node_id: str) -> dict[str, Any]:
    return dict(state.decisions.get(node_id, {}).get("parameters", {}))


def _s01_v2_start(state: RunState) -> dict[str, Any]:
    return deepcopy(state.canonical_state["scenario"]["scenario_start"])


def _s01_v2_apply_r1(state: RunState) -> None:
    s = state.canonical_state["s01_v2_state"]
    s["cycle"] = "B"
    s["phase_id"] = "S01_R1_VERIFY_AND_PUBLISH"
    supplier = _s01_v2_decision_params(state, "S01_A1_SUPPLIER_APPLICATION")
    gc = _s01_v2_decision_params(state, "S01_A2_GC_INITIAL_REVIEW")
    owner = _s01_v2_decision_params(state, "S01_A3_OWNER_PROVISIONAL_POSITION")
    inspector = _s01_v2_decision_params(state, "S01_A3_INSPECTOR_REVIEW_PLAN")
    erector = _s01_v2_decision_params(state, "S01_A3_ERECTOR_CAPACITY_OFFER")
    lender = _s01_v2_decision_params(state, "S01_A4_LENDER_PROVISIONAL_POSITION")

    s["payment"]["requested_usd"] = int(supplier.get("payment_requested_usd", s["payment"]["requested_usd"]))
    s["payment"]["provisional_certified_usd"] = int(gc.get("provisional_certified_value_usd", 0))
    s["inspection"]["selected_scope"] = inspector.get("inspection_scope")
    s["inspection"]["scheduled_tick"] = inspector.get("inspection_tick")
    s["gc_controls"]["verification_strategy"] = gc.get("review_strategy")
    s["gc_controls"]["selected_sequence"] = gc.get("preliminary_erection_strategy")
    s["gc_controls"]["gc_bridge_ceiling_usd"] = int(
        gc.get("gc_bridge_ceiling_usd", 0)
    )

    scope = inspector.get("inspection_scope")
    submitted_documents = set(supplier.get("submitted_document_ids", []))
    inspector_documents = set(gc.get("inspector_package_document_ids", [])) & submitted_documents
    owner_lender_documents = (
        set(gc.get("owner_lender_package_document_ids", [])) & submitted_documents
    )
    eligible, findings, maximum_release = _s01_v2_r1_eligible_value(
        s,
        str(scope),
        routed_document_ids=inspector_documents,
    )
    s["payment"]["eligible_stored_value_usd"] = eligible
    s["inspection"]["findings"] = findings
    s["inspection"]["maximum_releasable_value_usd"] = maximum_release
    s["inspection"]["lot_a_disposition"] = "REVIEWED" if maximum_release >= 950_000 else "NOT_RELEASED"
    s["inspection"]["lot_b_disposition"] = "NONCONFORMANCE_OBSERVED" if scope in {"LOT_A_AND_SAMPLE_B", "FULL_SEQUENCE"} else "NOT_REVIEWED"

    inspection_costs = {
        "DOCUMENT_ONLY": 20_000,
        "LOT_A_TARGETED": 45_000,
        "LOT_A_AND_SAMPLE_B": 65_000,
        "FULL_SEQUENCE": 90_000,
    }
    s["scenario_costs"]["inspection_usd"] = inspection_costs.get(str(scope), 0)
    if gc.get("backup_action") == "RESERVE":
        s["gc_controls"]["backup_status"] = "RESERVED"
        s["gc_controls"]["backup_cost_incurred_usd"] = 120_000
        s["scenario_costs"]["backup_usd"] = 120_000
    elif gc.get("backup_action") == "BEGIN_QUALIFICATION":
        s["gc_controls"]["backup_status"] = "QUALIFYING"

    s["commitments"]["provisional_offers"] = [
        {
            "offer_id": "OWNER_PROVISIONAL_SUPPORT",
            "organization_id": "owner",
            "funding_ceiling_usd": int(owner.get("owner_funding_ceiling_usd", 0)),
            "equity_ceiling_usd": int(owner.get("immediate_equity_ceiling_usd", 0)),
            "required_control_codes": list(owner.get("required_control_codes", [])),
        },
        {
            "offer_id": "LENDER_PROVISIONAL_DRAW",
            "organization_id": "lender",
            "maximum_draw_usd": int(lender.get("maximum_draw_usd", 0)),
            "advance_rate": float(lender.get("advance_rate", 0.0)),
            "escrow_cap_usd": int(lender.get("escrow_cap_usd", 0)),
            "minimum_owner_equity_usd": int(
                lender.get("minimum_owner_equity_usd", 0)
            ),
            "minimum_completion_reserve_usd": int(
                _s01_v2_start(state)["lender"]["minimum_completion_reserve_usd"]
            ),
            "required_control_codes": list(lender.get("required_control_codes", [])),
        },
        {
            "offer_id": "ERECTOR_CAPACITY_OFFER",
            "organization_id": "labor_subcontractor",
            "capacity_offer": erector.get("capacity_offer"),
            "hold_through_tick": erector.get("hold_through_tick"),
            "standby_price_usd": int(erector.get("standby_price_usd", 0)),
        },
    ]
    satisfied = {"INSPECTION_REPORT_AVAILABLE"}
    if "DOC_LOT_A_TITLE" in owner_lender_documents:
        satisfied.add("TITLE_COMPLETE")
        satisfied.add("LIEN_PROTECTION_COMPLETE")
    if "DOC_LOT_A_INSURANCE" in owner_lender_documents:
        satisfied.add("INSURANCE_COMPLETE")
    s["commitments"]["satisfied_condition_codes"] = sorted(satisfied)

    inspection_record = {
        "event_id": "S01_V2_R1_INSPECTION_RECORD",
        "source": "inspector",
        "summary": f"{scope} review produced eligible stored value ${eligible:,}.",
        "inspection_scope": scope,
        "eligible_stored_value_usd": eligible,
        "maximum_releasable_value_usd": maximum_release,
    }
    state.public_facts.append(inspection_record)
    state.public_state["facts"].append(inspection_record)
    state.private_state_by_agent["inspector"]["private_facts"]["s01_v2_inspection_findings"] = findings
    state.histories["s01_v2_lineage_transition_history"].append(
        {
            "phase_id": "S01_R1_VERIFY_AND_PUBLISH",
            "submitted_document_ids": sorted(submitted_documents),
            "inspector_document_ids_consumed": sorted(inspector_documents),
            "owner_lender_document_ids_consumed": sorted(owner_lender_documents),
            "inspection_scope": scope,
            "inspection_tick": inspector.get("inspection_tick"),
            "eligible_stored_value_usd": eligible,
            "maximum_releasable_value_usd": maximum_release,
            "satisfied_condition_codes": sorted(satisfied),
        }
    )


def _s01_v2_r1_eligible_value(
    s01_state: dict[str, Any],
    scope: str,
    *,
    routed_document_ids: set[str],
) -> tuple[int, list[dict[str, Any]], int]:
    lots = s01_state["lots"]
    if scope == "DOCUMENT_ONLY":
        scoped_lots: list[str] = []
        inspector_verified = 0
    elif scope == "LOT_A_TARGETED":
        scoped_lots = ["lot_a"]
        inspector_verified = 950_000 if "DOC_LOT_A_QC" in routed_document_ids else 0
    elif scope == "LOT_A_AND_SAMPLE_B":
        scoped_lots = ["lot_a", "lot_b"]
        inspector_verified = 950_000 if "DOC_LOT_A_QC" in routed_document_ids else 0
    elif scope == "FULL_SEQUENCE":
        scoped_lots = ["lot_a", "lot_b"]
        inspector_verified = 950_000 if "DOC_LOT_A_QC" in routed_document_ids else 0
    else:
        scoped_lots = []
        inspector_verified = 0
    if not scoped_lots:
        findings = [{"scope": scope, "finding": "document_review_only_no_physical_release"}]
        return 0, findings, 0
    true_value = sum(int(lots[lot]["true_completed_value_usd"]) for lot in scoped_lots)
    documented = (
        sum(int(lots[lot]["documented_value_usd"]) for lot in scoped_lots)
        if "DOC_LOT_A_INVOICE" in routed_document_ids
        else 0
    )
    insured = (
        sum(int(lots[lot]["insured_value_usd"]) for lot in scoped_lots)
        if "DOC_LOT_A_INSURANCE" in routed_document_ids
        else 0
    )
    title = (
        sum(int(lots[lot]["title_transferable_value_usd"]) for lot in scoped_lots)
        if "DOC_LOT_A_TITLE" in routed_document_ids
        else 0
    )
    eligible = min(true_value, documented, insured, title, inspector_verified)
    findings = [
        {
            "lot_id": "lot_a",
            "finding": "lot_a_value_verified_with_document_gap",
            "verified_value_usd": 950_000 if "lot_a" in scoped_lots else 0,
        }
    ]
    if "lot_b" in scoped_lots:
        findings.append(
            {
                "lot_id": "lot_b",
                "finding": "known_nonconformance_prevents_release",
                "verified_value_usd": 0,
            }
        )
    return eligible, findings, eligible


def _s01_v2_apply_r2(state: RunState) -> None:
    s = state.canonical_state["s01_v2_state"]
    start = _s01_v2_start(state)
    s["cycle"] = "C"
    s["phase_id"] = "S01_R2_COMMIT_AND_PRODUCE"
    supplier = _s01_v2_decision_params(state, "S01_B1_SUPPLIER_COMMITMENT")
    gc = _s01_v2_decision_params(state, "S01_B2_GC_INTEGRATED_PACKAGE")
    inspector = _s01_v2_decision_params(state, "S01_B3_INSPECTOR_DISPOSITION")
    erector = _s01_v2_decision_params(state, "S01_B3_ERECTOR_BINDING_COMMITMENT")
    owner = _s01_v2_decision_params(state, "S01_B4_OWNER_PACKAGE_DECISION")
    lender = _s01_v2_decision_params(state, "S01_B5_LENDER_RELEASE_DECISION")

    offer_actions = set(supplier.get("provisional_offer_actions", []))
    accepted_offers = all(
        f"{offer_id}:ACCEPT" in offer_actions
        and f"{offer_id}:REJECT" not in offer_actions
        for offer_id in [
            "OWNER_PROVISIONAL_SUPPORT",
            "LENDER_PROVISIONAL_DRAW",
            "ERECTOR_CAPACITY_OFFER",
        ]
    )
    compatible = (
        accepted_offers
        and supplier.get("cure_plan") != "NO_CURE"
        and gc.get("supplier_proposal_action") != "REJECT"
        and owner.get("package_action") != "REJECT"
        and erector.get("offer_action") != "RELEASE"
    )
    eligible = int(s["payment"]["eligible_stored_value_usd"])
    primary_draw_capacity = _s01_v2_primary_draw_capacity(
        s,
        gc,
        inspector,
        owner,
        lender,
    )
    draw_release = 0
    escrow = 0
    if compatible and lender.get("release_action") in {"RELEASE", "PARTIAL_RELEASE"}:
        draw_release = min(
            int(lender.get("draw_release_usd", 0)),
            primary_draw_capacity,
        )
    elif compatible and lender.get("release_action") == "ESCROW":
        lender_offer = _s01_v2_provisional_offer(s, "LENDER_PROVISIONAL_DRAW")
        escrow = min(
            int(lender.get("escrow_release_usd", 0)),
            int(lender_offer.get("escrow_cap_usd", 0)),
            primary_draw_capacity,
        )
    owner_funds = 0
    owner_equity = 0
    gc_bridge = 0
    if compatible:
        owner_funds = min(int(owner.get("owner_funding_usd", 0)), int(gc.get("owner_funds_requested_usd", 0)))
        owner_equity = min(int(owner.get("owner_equity_usd", 0)), int(lender.get("owner_equity_required_usd", 0)))
        gc_bridge = min(
            int(gc.get("gc_bridge_usd", 0)),
            int(s["gc_controls"].get("gc_bridge_ceiling_usd", 0)),
            int(start["gc"]["maximum_gc_bridge_usd"]),
        )
    s["payment"].update(
        {
            "final_certified_usd": min(int(gc.get("final_certified_payment_usd", 0)), eligible),
            "lender_draw_requested_usd": int(gc.get("lender_draw_requested_usd", 0)),
            "lender_draw_released_usd": draw_release,
            "owner_funds_usd": owner_funds,
            "owner_equity_usd": owner_equity,
            "gc_bridge_usd": gc_bridge,
            "escrow_usd": escrow,
        }
    )

    outside_financing = int(supplier.get("outside_financing_usd", 0))
    s["supplier_execution"].update(
        {
            "cash_committed_usd": int(supplier.get("supplier_cash_committed_usd", 0)),
            "outside_financing_usd": outside_financing,
            "outside_work_action": supplier.get("outside_work_action"),
            "cure_plan": supplier.get("cure_plan"),
            "lot_a_committed_tick": supplier.get("lot_a_commitment_tick"),
            "lot_b_committed_tick": supplier.get("lot_b_commitment_tick"),
        }
    )
    if outside_financing:
        s["scenario_costs"]["financing_usd"] = int(start["steel_supplier"]["outside_financing_cost_usd"])
    if gc_bridge:
        s["scenario_costs"]["bridge_usd"] = int(gc_bridge * 0.05)
    if owner.get("approved_standby_usd", 0) and erector.get("capacity_commitment") in {"FULL", "SPLIT"}:
        standby = min(int(owner.get("approved_standby_usd", 0)), int(erector.get("standby_compensation_usd", 0)))
        s["scenario_costs"]["standby_usd"] = standby
    if gc.get("backup_action") == "MAINTAIN" and s["gc_controls"]["backup_status"] == "QUALIFYING":
        s["gc_controls"]["backup_status"] = "RESERVED"
        s["gc_controls"]["backup_cost_incurred_usd"] += 120_000
        s["scenario_costs"]["backup_usd"] += 120_000
    elif gc.get("backup_action") == "ACTIVATE":
        s["gc_controls"]["backup_status"] = "ACTIVATED"
        s["gc_controls"]["backup_cost_incurred_usd"] += 3_400_000
        s["scenario_costs"]["backup_usd"] += 3_400_000

    available_funds = (
        int(supplier.get("supplier_cash_committed_usd", 0))
        + outside_financing
        + draw_release
        + escrow
        + owner_funds
        + owner_equity
        + gc_bridge
    )
    lot_a_ready, lot_b_ready, cure_cost, max_release = _s01_v2_supplier_readiness(
        supplier,
        inspector,
        available_funds,
    )
    s["supplier_execution"]["actual_lot_a_ready_tick"] = lot_a_ready
    s["supplier_execution"]["actual_lot_b_ready_tick"] = lot_b_ready
    s["scenario_costs"]["cure_usd"] = cure_cost
    s["inspection"]["maximum_releasable_value_usd"] = max_release
    s["inspection"]["lot_a_disposition"] = str(inspector.get("disposition"))
    s["inspection"]["lot_b_disposition"] = "FULL_RELEASED" if max_release >= 1_350_000 else "HOLD"
    s["inspection"]["reinspection_tick"] = inspector.get("reinspection_tick")
    minimum_labor_release = int(erector.get("minimum_releasable_value_usd", 0))
    effective_labor_capacity = erector.get("capacity_commitment")
    if max_release < minimum_labor_release:
        effective_labor_capacity = "NONE"
    s["labor"]["binding_commitment"] = effective_labor_capacity
    s["labor"]["mobilization_tick"] = erector.get("mobilization_tick")
    s["labor"]["overtime_commitment"] = erector.get("overtime_commitment")
    s["labor"]["minimum_releasable_value_usd"] = minimum_labor_release
    if erector.get("offer_action") == "RELEASE" or effective_labor_capacity == "NONE":
        s["labor"]["crew_status"] = "RELEASED"
        s["labor"]["crane_status"] = "RELEASED"
    else:
        s["labor"]["crew_status"] = "COMMITTED"
        s["labor"]["crane_status"] = "COMMITTED"
    satisfied = set(s["commitments"].get("satisfied_condition_codes", []))
    if max_release >= 950_000:
        satisfied.add("LOT_A_RELEASED")
    if max_release >= 1_350_000:
        satisfied.add("FULL_SEQUENCE_RELEASED")
    if draw_release + escrow:
        satisfied.add("LENDER_DRAW_MINIMUM")
    if gc_bridge:
        satisfied.add("GC_BRIDGE_AVAILABLE")
    if s["labor"]["binding_commitment"] == "FULL":
        satisfied.add("LABOR_FULL_HOLD_CONFIRMED")
    if s["labor"]["binding_commitment"] == "SPLIT":
        satisfied.add("LABOR_SPLIT_HOLD_CONFIRMED")
    if supplier.get("cure_plan") in {"DOCUMENT_CURE", "LOT_A_CURE", "FULL_SEQUENCE_CURE"}:
        satisfied.add("DOCUMENT_CURE_COMPLETE")
    if supplier.get("cure_plan") == "FULL_SEQUENCE_CURE" and lot_b_ready is not None:
        satisfied.add("PHYSICAL_CURE_COMPLETE")
        satisfied.add("REINSPECTION_PASSED")
    s["commitments"]["satisfied_condition_codes"] = sorted(satisfied)
    state.private_state_by_agent["steel_supplier"]["private_facts"]["s01_v2_actual_readiness"] = {
        "actual_lot_a_ready_tick": lot_a_ready,
        "actual_lot_b_ready_tick": lot_b_ready,
        "available_execution_funds_usd": available_funds,
    }
    state.private_state_by_agent["inspector"]["private_facts"]["s01_v2_maximum_releasable_value_usd"] = max_release
    production_record = {
        "event_id": "S01_V2_R2_PRODUCTION_RECORD",
        "source": "scenario",
        "summary": "Funding, production, and capacity commitments closed for the C-cycle recovery decisions.",
        "public_lot_a_release_possible": max_release >= 950_000,
        "public_full_sequence_release_possible": max_release >= 1_350_000,
        "maximum_releasable_value_usd": max_release,
        "reinspection_expanded_value": max_release > int(
            inspector.get("maximum_releasable_value_usd", 0)
        ),
        "lender_draw_released_usd": draw_release,
        "controlled_escrow_released_usd": escrow,
    }
    state.public_facts.append(production_record)
    state.public_state["facts"].append(production_record)
    state.histories["s01_v2_lineage_transition_history"].append(
        {
            "phase_id": "S01_R2_COMMIT_AND_PRODUCE",
            "compatible_package": compatible,
            "accepted_provisional_offers": accepted_offers,
            "primary_draw_capacity_usd": primary_draw_capacity,
            "requested_draw_release_usd": int(lender.get("draw_release_usd", 0)),
            "requested_escrow_release_usd": int(
                lender.get("escrow_release_usd", 0)
            ),
            "lender_draw_released_usd": draw_release,
            "controlled_escrow_released_usd": escrow,
            "owner_funds_usd": owner_funds,
            "owner_equity_usd": owner_equity,
            "gc_bridge_usd": gc_bridge,
            "supplier_cash_committed_usd": int(
                supplier.get("supplier_cash_committed_usd", 0)
            ),
            "outside_financing_usd": outside_financing,
            "available_execution_funds_usd": available_funds,
            "cure_plan": supplier.get("cure_plan"),
            "inspector_initial_release_cap_usd": int(
                inspector.get("maximum_releasable_value_usd", 0)
            ),
            "actual_lot_a_ready_tick": lot_a_ready,
            "actual_lot_b_ready_tick": lot_b_ready,
            "maximum_releasable_value_usd": max_release,
        }
    )


def _s01_v2_primary_draw_capacity(
    s01_state: dict[str, Any],
    gc: dict[str, Any],
    inspector: dict[str, Any],
    owner: dict[str, Any],
    lender: dict[str, Any],
) -> int:
    required_controls = {"TITLE_COMPLETE", "INSURANCE_COMPLETE", "LIEN_PROTECTION_COMPLETE"}
    if not required_controls <= set(s01_state["commitments"].get("satisfied_condition_codes", [])):
        return 0
    eligible = int(s01_state["payment"]["eligible_stored_value_usd"])
    lender_offer = _s01_v2_provisional_offer(s01_state, "LENDER_PROVISIONAL_DRAW")
    advance_rate = float(lender_offer.get("advance_rate", 0.0))
    lender_maximum = int(lender_offer.get("maximum_draw_usd", 0))
    max_by_rate = int(advance_rate * eligible)
    minimum_owner_equity = int(lender_offer.get("minimum_owner_equity_usd", 0))
    if (
        int(owner.get("owner_equity_usd", 0)) < minimum_owner_equity
        or int(lender.get("owner_equity_required_usd", 0)) < minimum_owner_equity
    ):
        return 0
    reserve_preserving = int(lender.get("completion_reserve_after_usd", 0)) >= int(
        _s01_v2_provisional_offer(s01_state, "LENDER_PROVISIONAL_DRAW").get(
            "minimum_completion_reserve_usd",
            1_000_000,
        )
    )
    if not reserve_preserving:
        return 0
    owner_package_amount = (
        0
        if owner.get("package_action") == "REJECT"
        else int(owner.get("owner_funding_usd", 0)) + int(owner.get("owner_equity_usd", 0)) + eligible
    )
    return max(
        0,
        min(
            lender_maximum,
            max_by_rate,
            int(gc.get("final_certified_payment_usd", 0)),
            int(gc.get("lender_draw_requested_usd", 0)),
            int(inspector.get("maximum_releasable_value_usd", 0)),
            owner_package_amount,
        ),
    )


def _s01_v2_provisional_offer(s01_state: dict[str, Any], offer_id: str) -> dict[str, Any]:
    for offer in s01_state.get("commitments", {}).get("provisional_offers", []):
        if offer.get("offer_id") == offer_id:
            return dict(offer)
    return {}


def _s01_v2_supplier_readiness(
    supplier: dict[str, Any],
    inspector: dict[str, Any],
    available_funds: int,
) -> tuple[int | None, int | None, int, int]:
    cure_plan = supplier.get("cure_plan")
    disposition = inspector.get("disposition")
    declared_release_cap = int(inspector.get("maximum_releasable_value_usd", 0))
    lot_a_ready = None
    lot_b_ready = None
    cure_cost = 0
    max_release = 0
    if cure_plan in {"DOCUMENT_CURE", "LOT_A_CURE", "FULL_SEQUENCE_CURE"} and available_funds >= 300_000:
        lot_a_ready = min(int(supplier.get("lot_a_commitment_tick", 14)), 14)
        cure_cost += 50_000
        if disposition != "NO_RELEASE":
            max_release = min(declared_release_cap, 950_000)
    if cure_plan == "FULL_SEQUENCE_CURE" and available_funds >= 1_150_000:
        outside_delay = {"DECLINE": 0, "ACCEPT_PARTIAL": 1, "ACCEPT_FULL": 3}.get(
            str(supplier.get("outside_work_action")),
            0,
        )
        lot_b_ready = int(supplier.get("lot_b_commitment_tick", 18)) + outside_delay
        cure_cost = 250_000
        reinspection_tick = inspector.get("reinspection_tick")
        reinspection_can_expand = (
            max_release >= 950_000
            and reinspection_tick is not None
            and lot_b_ready <= int(reinspection_tick)
        )
        if reinspection_can_expand:
            max_release = 1_350_000
    return lot_a_ready, lot_b_ready, cure_cost, max_release


def _s01_v2_apply_r3(state: RunState) -> None:
    s = state.canonical_state["s01_v2_state"]
    s["cycle"] = "TERMINAL"
    s["phase_id"] = "S01_R3_TERMINAL_RESOLUTION"
    supplier = _s01_v2_decision_params(state, "S01_C1_SUPPLIER_STATUS_AND_RECOVERY")
    gc = _s01_v2_decision_params(state, "S01_C2_GC_RECOVERY_PLAN")
    inspector = _s01_v2_decision_params(state, "S01_C3_INSPECTOR_FINAL_DISPOSITION")
    owner = _s01_v2_decision_params(state, "S01_C4_OWNER_FINAL_POSITION")
    erector = _s01_v2_decision_params(state, "S01_C6_ERECTOR_MOBILIZATION")

    if supplier.get("supplier_recovery_spend_usd"):
        s["scenario_costs"]["cure_usd"] += int(supplier.get("supplier_recovery_spend_usd", 0))
    if erector.get("incremental_cost_usd"):
        s["scenario_costs"]["overtime_usd"] = int(erector.get("incremental_cost_usd", 0))
    if gc.get("recovery_plan") == "ACTIVATE_BACKUP" and s["gc_controls"]["backup_status"] != "ACTIVATED":
        s["gc_controls"]["backup_status"] = "ACTIVATED"
        s["gc_controls"]["backup_cost_incurred_usd"] += 3_400_000
        s["scenario_costs"]["backup_usd"] += 3_400_000
    if gc.get("supplemental_gc_bridge_usd"):
        s["payment"]["gc_bridge_usd"] += int(gc.get("supplemental_gc_bridge_usd", 0))
        s["scenario_costs"]["bridge_usd"] += int(int(gc.get("supplemental_gc_bridge_usd", 0)) * 0.05)
    lot_a_ready = s["supplier_execution"].get("actual_lot_a_ready_tick")
    lot_b_ready = s["supplier_execution"].get("actual_lot_b_ready_tick")
    approved_value = int(inspector.get("approved_shipping_value_usd", 0))
    lot_a_released = (
        inspector.get("lot_a_disposition") in {"RELEASE", "CONDITIONAL"}
        and lot_a_ready is not None
        and approved_value >= 950_000
    )
    lot_b_released = (
        inspector.get("lot_b_disposition") in {"RELEASE", "CONDITIONAL"}
        and lot_b_ready is not None
        and approved_value >= 1_350_000
    )
    ship_action = supplier.get("ship_action")
    lot_a_shipped = lot_a_released and ship_action in {"SHIP_A", "SHIP_BOTH"}
    lot_b_shipped = lot_b_released and ship_action == "SHIP_BOTH"
    s["lots"]["lot_a"]["released_quantity"] = 1 if lot_a_released else 0
    s["lots"]["lot_a"]["shipped_quantity"] = 1 if lot_a_shipped else 0
    s["lots"]["lot_b"]["released_quantity"] = 1 if lot_b_released else 0
    s["lots"]["lot_b"]["shipped_quantity"] = 1 if lot_b_shipped else 0

    compliance_failure = False
    if erector.get("mobilization_action") in {"FULL", "OVERTIME"} and not (lot_a_shipped and lot_b_shipped):
        compliance_failure = True
    if erector.get("mobilization_action") == "PHASED" and not lot_a_shipped:
        compliance_failure = True
    if lot_b_released and s["lots"]["lot_b"]["physical_nonconformance"] and lot_b_ready is None:
        compliance_failure = True

    completion = _s01_v2_completion_tick(s, supplier, gc, erector, lot_a_shipped, lot_b_shipped)
    delay_ticks = max(0, completion - 40)
    s["scenario_costs"]["delay_usd"] = delay_ticks * 250_000
    authorized_recovery_cost = int(owner.get("accepted_additional_cost_usd", 0))
    supplier_commitment = _s01_v2_decision_params(
        state, "S01_B1_SUPPLIER_COMMITMENT"
    )
    gc_package = _s01_v2_decision_params(state, "S01_B2_GC_INTEGRATED_PACKAGE")
    owner_package = _s01_v2_decision_params(state, "S01_B4_OWNER_PACKAGE_DECISION")
    approved_price_adjustment = min(
        int(supplier_commitment.get("requested_price_adjustment_usd", 0)),
        int(gc_package.get("supplier_price_adjustment_usd", 0)),
        int(owner_package.get("approved_price_adjustment_usd", 0)),
    )
    final_cost = (
        int(state.canonical_state["project"]["base_project_cost"])
        + sum(int(value) for value in s["scenario_costs"].values())
        + approved_price_adjustment
    )
    backup_success = s["gc_controls"]["backup_status"] == "ACTIVATED" and erector.get("mobilization_action") != "RELEASE"
    status, reason = S01OffsiteSteelDraw().status_for(
        final_cost,
        completion,
        deadlock=compliance_failure or (not lot_a_shipped and not backup_success),
    )
    if compliance_failure:
        reason = "unreleased or nonconforming steel would be installed under the selected mobilization plan"
    project = state.canonical_state["project"]
    project["project_cost"] = final_cost
    project["completion_tick"] = completion
    project["cost_components"] = {"base": int(project["base_project_cost"])} | dict(s["scenario_costs"])
    if approved_price_adjustment:
        project["cost_components"]["approved_price_adjustment"] = approved_price_adjustment
    project["s01_v2_authorized_recovery_cost_usd"] = authorized_recovery_cost
    project["s01_v2_recovery_cost_allocation"] = {
        "owner_cost_share_usd": int(owner.get("owner_cost_share_usd", 0)),
        "gc_cost_share_usd": int(owner.get("gc_cost_share_usd", 0)),
        "supplier_cost_share_usd": int(owner.get("supplier_cost_share_usd", 0)),
    }
    project["s01_v2_path_label"] = _s01_v2_path_label(
        status=status,
        completion=completion,
        lot_a_shipped=lot_a_shipped,
        lot_b_shipped=lot_b_shipped,
        backup_status=s["gc_controls"]["backup_status"],
        compliance_failure=compliance_failure,
    )
    project["s01_v2_project_success"] = status == "PROJECT_SUCCESS"
    project["s01_v2_compliance_failure"] = compliance_failure
    project["s01_v2_released_lots"] = {
        "lot_a": lot_a_released,
        "lot_b": lot_b_released,
    }
    project["s01_v2_shipped_lots"] = {
        "lot_a": lot_a_shipped,
        "lot_b": lot_b_shipped,
    }
    for key, value in normal_project_bound_metrics(
        state.variant,
        project_cost=project["project_cost"],
        completion_tick=project["completion_tick"],
    ).items():
        project[key] = value
    deliverable_metrics = S01OffsiteSteelDraw().deliverable_metrics(
        actual_finish_overrides={
            "D10_STEEL_SITE_DELIVERY": int(lot_a_ready or 24),
            "D18_LABOR_STRUCTURAL_STEEL_ERECTION": min(completion, 23 if compliance_failure else completion),
            "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": completion,
            "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED": completion,
            "D26_LENDER_FINAL_RETAINAGE_RELEASE": completion,
        },
        blocked_deliverable_ids={"D18_LABOR_STRUCTURAL_STEEL_ERECTION"} if compliance_failure else set(),
        impact_notes={
            "D10_STEEL_SITE_DELIVERY": "S01 V2 off-site steel readiness and release controlled delivery",
            "D18_LABOR_STRUCTURAL_STEEL_ERECTION": "S01 V2 labor mobilization and release controlled erection",
            "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE": "S01 V2 steel sequence controlled completion",
        },
    )
    project.update(deliverable_metrics)
    organization_ledger = _s01_v2_organization_ledger(state, status=status, completion=completion)
    project["s01_v2_private_success_by_organization"] = {
        agent_id: ledger["private_success"]
        for agent_id, ledger in organization_ledger.items()
    }
    project["s01_v2_coalition_success"] = (
        project["s01_v2_project_success"]
        and all(project["s01_v2_private_success_by_organization"].values())
    )
    payoff_ledger = _s01_v2_payoff_ledger(state, organization_ledger)
    state.canonical_state["organizations"] = organization_ledger
    state.canonical_state["terminal_values"] = {
        agent_id: ledger["realized_payoff_usd"]
        for agent_id, ledger in organization_ledger.items()
    }
    state.canonical_state["payoff_ledger"] = payoff_ledger
    _s01_v2_finalize_claim_provenance(state)
    state.histories["s01_v2_lineage_transition_history"].append(
        {
            "phase_id": "S01_R3_TERMINAL_RESOLUTION",
            "supplier_ship_action": ship_action,
            "lot_a_released": lot_a_released,
            "lot_b_released": lot_b_released,
            "lot_a_shipped": lot_a_shipped,
            "lot_b_shipped": lot_b_shipped,
            "approved_shipping_value_usd": approved_value,
            "labor_binding_capacity": s["labor"].get("binding_commitment"),
            "labor_overtime_commitment": s["labor"].get("overtime_commitment"),
            "mobilization_action": erector.get("mobilization_action"),
            "mobilization_tick": erector.get("mobilization_tick"),
            "compliance_failure": compliance_failure,
            "completion_tick": completion,
            "project_success": project["s01_v2_project_success"],
        }
    )
    s["analysis"] = _s01_v2_analysis_record(state)
    state.terminal_status = status
    state.terminal_reason = reason


def _s01_v2_completion_tick(
    s: dict[str, Any],
    supplier: dict[str, Any],
    gc: dict[str, Any],
    erector: dict[str, Any],
    lot_a_shipped: bool,
    lot_b_shipped: bool,
) -> int:
    mobilization_tick = int(erector.get("mobilization_tick", 25))
    if erector.get("mobilization_action") == "RELEASE":
        return max(50, int(erector.get("remobilization_tick_if_released") or 23) + 27)
    if gc.get("recovery_plan") == "ACTIVATE_BACKUP" or s["gc_controls"]["backup_status"] == "ACTIVATED":
        return 45 if erector.get("mobilization_action") != "RELEASE" else 50
    late_start = max(0, mobilization_tick - 15)
    if lot_a_shipped and lot_b_shipped and erector.get("mobilization_action") in {"FULL", "OVERTIME"}:
        return 40 + late_start
    if lot_a_shipped and lot_b_shipped and erector.get("mobilization_action") in {"PHASED", "OVERTIME"}:
        lot_b_delay = max(0, int(s["supplier_execution"].get("actual_lot_b_ready_tick") or 24) - 18)
        return 41 + late_start + lot_b_delay
    if lot_a_shipped:
        accepted_delay = 2 if gc.get("recovery_plan") == "ACCEPT_DELAY" else 0
        return 49 + late_start + accepted_delay
    return 52 + late_start


def _s01_v2_path_label(
    *,
    status: str,
    completion: int,
    lot_a_shipped: bool,
    lot_b_shipped: bool,
    backup_status: str,
    compliance_failure: bool,
) -> str:
    if compliance_failure:
        return "compliance_failure"
    if status != "PROJECT_SUCCESS":
        if backup_status == "ACTIVATED":
            return "backup_recovery_failure"
        return "coordination_delay_failure"
    if lot_a_shipped and lot_b_shipped and completion <= 40:
        return "full_sequence_success"
    if lot_a_shipped and lot_b_shipped:
        return "phased_coalition_success"
    if backup_status == "ACTIVATED":
        return "backup_project_success"
    return "limited_project_success"


def _s01_v2_organization_ledger(
    state: RunState,
    *,
    status: str,
    completion: int,
) -> dict[str, dict[str, Any]]:
    s = state.canonical_state["s01_v2_state"]
    start = _s01_v2_start(state)
    b1 = _s01_v2_decision_params(state, "S01_B1_SUPPLIER_COMMITMENT")
    b2 = _s01_v2_decision_params(state, "S01_B2_GC_INTEGRATED_PACKAGE")
    c1 = _s01_v2_decision_params(state, "S01_C1_SUPPLIER_STATUS_AND_RECOVERY")
    c4 = _s01_v2_decision_params(state, "S01_C4_OWNER_FINAL_POSITION")
    c6 = _s01_v2_decision_params(state, "S01_C6_ERECTOR_MOBILIZATION")
    project_success = status == "PROJECT_SUCCESS"
    delay_ticks = max(0, completion - 40)
    outside_margin = {
        "DECLINE": 0,
        "ACCEPT_PARTIAL": 140_000,
        "ACCEPT_FULL": 280_000,
    }.get(str(b1.get("outside_work_action")), 0)
    supplier_payoff = (
        (600_000 if s["lots"]["lot_a"]["shipped_quantity"] else -300_000)
        + (250_000 if s["lots"]["lot_b"]["shipped_quantity"] else 0)
        + outside_margin
        + int(
            state.canonical_state["project"]
            .get("cost_components", {})
            .get("approved_price_adjustment", 0)
        )
        - int(s["scenario_costs"].get("financing_usd", 0))
        - int(s["scenario_costs"].get("cure_usd", 0))
        - int(c1.get("supplier_recovery_spend_usd", 0))
        - int(c4.get("supplier_cost_share_usd", 0))
    )
    gc_payoff = (
        (900_000 if project_success else 250_000)
        - int(s["payment"].get("gc_bridge_usd", 0)) // 10
        - int(s["gc_controls"].get("backup_cost_incurred_usd", 0)) // 5
        - delay_ticks * int(start["gc"]["project_delay_cost_per_tick_usd"]) // 2
        - int(c4.get("gc_cost_share_usd", 0))
        + int(b2.get("late_credit_usd", 0))
    )
    owner_payoff = (
        (4_000_000 if project_success else -1_000_000)
        - max(0, state.canonical_state["project"]["project_cost"] - 95_000_000)
        - delay_ticks * int(start["owner"]["private_delay_cost_per_tick_usd"])
        - int(c4.get("owner_cost_share_usd", 0))
    )
    lender_payoff = (
        (350_000 if project_success else -600_000)
        - max(0, 1_000_000 - int(_s01_v2_decision_params(state, "S01_B5_LENDER_RELEASE_DECISION").get("completion_reserve_after_usd", 0))) // 2
        - int(_s01_v2_decision_params(state, "S01_C5_LENDER_SUPPLEMENTAL_POSITION").get("reserve_exception_usd", 0))
    )
    compliance_failure = bool(state.canonical_state["project"].get("s01_v2_compliance_failure"))
    inspector_payoff = (
        180_000
        - int(s["scenario_costs"].get("inspection_usd", 0)) // 2
        - (700_000 if compliance_failure else 0)
        - max(0, int(_s01_v2_decision_params(state, "S01_A3_INSPECTOR_REVIEW_PLAN").get("inspection_tick", 12)) - 12) * 20_000
    )
    labor_payoff = (
        (650_000 if project_success and c6.get("mobilization_action") != "RELEASE" else 0)
        + int(s["scenario_costs"].get("standby_usd", 0))
        + (int(start["labor_subcontractor"]["outside_project_margin_usd"]) if c6.get("mobilization_action") == "RELEASE" else 0)
        - int(c6.get("incremental_cost_usd", 0))
        - (int(start["labor_subcontractor"]["remobilization_cost_usd"]) if c6.get("mobilization_action") == "RELEASE" else 0)
    )
    thresholds = {
        "owner": 500_000,
        "gc": 250_000,
        "steel_supplier": 250_000,
        "labor_subcontractor": 300_000,
        "lender": 0,
        "inspector": 0,
    }
    realized = {
        "owner": owner_payoff,
        "gc": gc_payoff,
        "steel_supplier": supplier_payoff,
        "labor_subcontractor": labor_payoff,
        "lender": lender_payoff,
        "inspector": inspector_payoff,
    }
    return {
        agent_id: {
            "realized_payoff_usd": int(payoff),
            "private_success_threshold_usd": thresholds[agent_id],
            "private_success": int(payoff) >= thresholds[agent_id],
        }
        for agent_id, payoff in realized.items()
    }


def _s01_v2_payoff_ledger(
    state: RunState,
    organization_ledger: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    events = [
        PayoffEvent(
            organization_id=agent_id,
            term_id="s01_v2_realized_private_value",
            amount=int(row["realized_payoff_usd"]),
            source_metric="s01_v2_organization_ledger",
            accounting_class="private_utility",
        )
        for agent_id, row in organization_ledger.items()
    ]
    project = state.canonical_state["project"]
    cost_delta = int(project["project_cost"]) - 95_000_000
    schedule_delta = int(project["completion_tick"]) - 40
    normalized_cost = max(0.0, min(1.0, (102_000_000 - int(project["project_cost"])) / 7_000_000))
    normalized_schedule = max(0.0, min(1.0, (48 - int(project["completion_tick"])) / 8))
    project_success = bool(project.get("s01_v2_project_success"))
    ledger = PayoffLedger(
        utility_specs={
            agent_id: UtilitySpec(
                scenario_id=state.scenario_id,
                role_id=agent_id,
                term_ids=["s01_v2_realized_private_value"],
                term_weights={"s01_v2_realized_private_value": 1.0},
                normalization_basis={
                    "private_success_threshold_usd": organization_ledger[agent_id][
                        "private_success_threshold_usd"
                    ]
                },
            )
            for agent_id in AGENT_IDS
        },
        payoff_events=events,
        realized_payoff_by_organization={
            agent_id: int(row["realized_payoff_usd"])
            for agent_id, row in organization_ledger.items()
        },
        expected_payoff_by_organization={
            agent_id: {
                "private_success_threshold_usd": row["private_success_threshold_usd"],
                "private_success": row["private_success"],
            }
            for agent_id, row in organization_ledger.items()
        },
        normalized_payoff_by_organization={
            agent_id: _s01_v2_normalized_private_payoff(
                int(row["realized_payoff_usd"]),
                int(row["private_success_threshold_usd"]),
            )
            for agent_id, row in organization_ledger.items()
        },
        project_welfare={
            "baseline_project_cost": 95_000_000,
            "success_budget_ceiling": 102_000_000,
            "baseline_completion_tick": 40,
            "success_deadline_tick": 48,
            "cost_delta_from_baseline": cost_delta,
            "schedule_delta_from_baseline": schedule_delta,
            "completion_success": project_success,
            "normalized_cost_score": normalized_cost,
            "normalized_schedule_score": normalized_schedule,
            "project_success": project_success,
            "coalition_success": bool(project.get("s01_v2_coalition_success")),
        },
        accounting_totals={
            "payoff_event_count": len(events),
            "scenario_cost_total_usd": sum(
                int(value)
                for value in state.canonical_state["s01_v2_state"]["scenario_costs"].values()
            ),
            "authorized_recovery_cost_usd": int(
                project.get("s01_v2_authorized_recovery_cost_usd", 0)
            ),
            "cash_transfers": {
                key: value
                for key, value in state.canonical_state["s01_v2_state"]["payment"].items()
                if key.endswith("_usd")
            },
        },
    )
    return ledger.model_dump(mode="json")


def _s01_v2_normalized_private_payoff(value: int, threshold: int) -> float:
    floor = threshold - 1_000_000
    ceiling = threshold + 1_000_000
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))


def _s01_v2_finalize_claim_provenance(state: RunState) -> None:
    s = state.canonical_state["s01_v2_state"]
    realized = {
        "payment_requested_usd": s["payment"]["requested_usd"],
        "lot_a_commitment_tick": s["supplier_execution"].get("actual_lot_a_ready_tick"),
        "lot_b_commitment_tick": s["supplier_execution"].get("actual_lot_b_ready_tick"),
    }
    for record in state.histories.setdefault("s01_v2_claim_provenance_history", []):
        field = record.get("field_name")
        if field in realized:
            record["later_realized_value"] = realized[field]


def _s01_v2_analysis_record(state: RunState) -> dict[str, Any]:
    s = state.canonical_state["s01_v2_state"]
    project = state.canonical_state["project"]
    payoff = state.canonical_state.get("payoff_ledger", {})
    observation_intervention_exposures = _s01_v2_observation_intervention_exposures(state)
    return {
        "schema_version": "constructbench.s01_v2_analysis.v3",
        "decision_count": len(s.get("structured_decision_records", {})),
        "decisions": list(s.get("structured_decision_records", {}).values()),
        "path_label": project.get("s01_v2_path_label"),
        "message_count": len(state.histories.get("message_history", [])),
        "communication_abstention_count": len(state.histories.get("communication_abstention_history", [])),
        "assessment_update_count": len(state.histories.get("assessment_history", [])),
        "assessment_review_count": len(state.histories.get("assessment_review_history", [])),
        "claim_provenance_count": len(state.histories.get("s01_v2_claim_provenance_history", [])),
        "payoff_event_count": len(payoff.get("payoff_events", [])),
        "final_project_cost": project.get("project_cost"),
        "completion_tick": project.get("completion_tick"),
        "project_success": project.get("s01_v2_project_success"),
        "coalition_success": project.get("s01_v2_coalition_success"),
        "compliance_failure": project.get("s01_v2_compliance_failure"),
        "observation_intervention_exposure_count": len(observation_intervention_exposures),
        "observation_intervention_exposures": observation_intervention_exposures,
        "lineage": build_s01_v2_lineage(state),
    }


def _s01_v2_observation_intervention_exposures(state: RunState) -> list[dict[str, Any]]:
    """Persist model-visible intervention proof without copying full observations."""
    exposures: list[dict[str, Any]] = []
    for observation in state.histories.get("agent_observation_history", []):
        for fact in observation.get("known_facts", []):
            if fact.get("source") != "harness_derived_decision_state":
                continue
            payload = {key: value for key, value in fact.items() if key != "packet_hash"}
            recorded_hash = fact.get("packet_hash")
            recomputed_hash = canonical_json_sha256(payload)
            exposures.append(
                {
                    "agent_id": observation.get("agent_id"),
                    "phase_id": observation.get("phase_id"),
                    "phase_index": observation.get("phase_index"),
                    "packet_id": fact.get("packet_id"),
                    "packet_schema_version": fact.get("schema_version"),
                    "packet_hash": recorded_hash,
                    "recomputed_packet_hash": recomputed_hash,
                    "hash_matches": recorded_hash == recomputed_hash,
                }
            )
    return exposures


def _s01_v2_default_decision_params(node_id: str) -> dict[str, Any]:
    return {
        name: deepcopy(spec.default)
        for name, spec in _s01_v2_specs(node_id).items()
    }


def _s01_v2_decisions(
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, tuple[str, dict[str, Any]]]:
    overrides = overrides or {}
    decisions: dict[str, tuple[str, dict[str, Any]]] = {}
    for node_id in S01OffsiteSteelDraw.actors:
        params_ = _s01_v2_default_decision_params(node_id)
        params_.update(overrides.get(node_id, {}))
        decisions[node_id] = ("__parameters__", params_)
    return decisions


def _s01_v2_fixture(
    *,
    overrides: dict[str, dict[str, Any]],
    expected: dict[str, Any],
) -> dict[str, Any]:
    return {
        "variant": "normal",
        "decisions": _s01_v2_decisions(overrides),
        "expected": expected,
    }


S01_V2_FIXTURES: dict[str, dict[str, Any]] = {
    "efficient_phased_coalition_success": _s01_v2_fixture(
        overrides={
            "S01_A1_SUPPLIER_APPLICATION": {
                "payment_requested_usd": 1_200_000,
                "submitted_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A2_GC_INITIAL_REVIEW": {
                "review_strategy": "TARGETED_INSPECTION",
                "provisional_certified_value_usd": 950_000,
                "gc_bridge_ceiling_usd": 150_000,
                "owner_lender_package_document_ids": S01_V2_DOCUMENT_IDS[:5],
                "inspector_package_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A3_OWNER_PROVISIONAL_POSITION": {
                "owner_funding_ceiling_usd": 250_000,
                "immediate_equity_ceiling_usd": 100_000,
            },
            "S01_A3_ERECTOR_CAPACITY_OFFER": {
                "standby_price_usd": 100_000,
            },
            "S01_A4_LENDER_PROVISIONAL_POSITION": {
                "maximum_draw_usd": 760_000,
                "minimum_owner_equity_usd": 100_000,
            },
            "S01_B1_SUPPLIER_COMMITMENT": {
                "outside_financing_usd": 0,
                "lot_a_commitment_tick": 14,
                "lot_b_commitment_tick": 18,
            },
            "S01_B2_GC_INTEGRATED_PACKAGE": {
                "final_certified_payment_usd": 950_000,
                "gc_bridge_usd": 100_000,
                "owner_funds_requested_usd": 200_000,
                "lender_draw_requested_usd": 760_000,
                "backup_action": "DROP",
            },
            "S01_B3_INSPECTOR_DISPOSITION": {
                "disposition": "LOT_A_RELEASED",
                "maximum_releasable_value_usd": 950_000,
                "reinspection_tick": 18,
            },
            "S01_B3_ERECTOR_BINDING_COMMITMENT": {
                "capacity_commitment": "SPLIT",
                "mobilization_tick": 15,
                "standby_compensation_usd": 100_000,
            },
            "S01_B4_OWNER_PACKAGE_DECISION": {
                "owner_funding_usd": 200_000,
                "owner_equity_usd": 100_000,
                "approved_standby_usd": 100_000,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "PARTIAL_RELEASE",
                "draw_release_usd": 760_000,
                "escrow_release_usd": 0,
                "owner_equity_required_usd": 100_000,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
                "ship_action": "SHIP_BOTH",
            },
            "S01_C2_GC_RECOVERY_PLAN": {
                "recovery_plan": "PROCEED_PHASED",
                "supplemental_gc_bridge_usd": 0,
            },
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "RELEASE",
                "lot_b_disposition": "RELEASE",
                "approved_shipping_value_usd": 1_350_000,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "PHASED",
                "mobilization_tick": 15,
            },
        },
        expected={
            "status": "PROJECT_SUCCESS",
            "final_project_cost": 95_650_000,
            "completion_tick": 41,
            "s01_v2_project_success": True,
            "s01_v2_coalition_success": True,
        },
    ),
    "conservative_project_success": _s01_v2_fixture(
        overrides={
            "S01_A1_SUPPLIER_APPLICATION": {
                "submitted_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A2_GC_INITIAL_REVIEW": {
                "review_strategy": "FULL_INSPECTION",
                "backup_action": "RESERVE",
                "preliminary_erection_strategy": "FULL",
                "gc_bridge_ceiling_usd": 300_000,
                "owner_lender_package_document_ids": S01_V2_DOCUMENT_IDS,
                "inspector_package_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A3_INSPECTOR_REVIEW_PLAN": {
                "inspection_scope": "FULL_SEQUENCE",
                "inspection_tick": 13,
            },
            "S01_A3_ERECTOR_CAPACITY_OFFER": {
                "capacity_offer": "FULL_HOLD",
                "standby_price_usd": 180_000,
            },
            "S01_A4_LENDER_PROVISIONAL_POSITION": {
                "maximum_draw_usd": 760_000,
                "escrow_cap_usd": 200_000,
            },
            "S01_B1_SUPPLIER_COMMITMENT": {
                "outside_financing_usd": 450_000,
            },
            "S01_B2_GC_INTEGRATED_PACKAGE": {
                "gc_bridge_usd": 300_000,
                "owner_funds_requested_usd": 300_000,
                "backup_action": "MAINTAIN",
            },
            "S01_B3_INSPECTOR_DISPOSITION": {
                "disposition": "LOT_A_RELEASED",
                "reinspection_tick": 18,
                "maximum_releasable_value_usd": 950_000,
            },
            "S01_B3_ERECTOR_BINDING_COMMITMENT": {
                "capacity_commitment": "FULL",
                "mobilization_tick": 17,
                "standby_compensation_usd": 180_000,
                "overtime_commitment": "NONE",
            },
            "S01_B4_OWNER_PACKAGE_DECISION": {
                "owner_funding_usd": 300_000,
                "owner_equity_usd": 100_000,
                "approved_standby_usd": 180_000,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "ESCROW",
                "draw_release_usd": 0,
                "escrow_release_usd": 200_000,
                "owner_equity_required_usd": 100_000,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
                "ship_action": "SHIP_BOTH",
            },
            "S01_C2_GC_RECOVERY_PLAN": {
                "recovery_plan": "PROCEED_FULL",
            },
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "RELEASE",
                "lot_b_disposition": "RELEASE",
                "approved_shipping_value_usd": 1_350_000,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "FULL",
                "mobilization_tick": 17,
            },
        },
        expected={
            "status": "PROJECT_SUCCESS",
            "final_project_cost": 96_235_000,
            "completion_tick": 42,
            "s01_v2_project_success": True,
        },
    ),
    "project_success_private_role_failure": _s01_v2_fixture(
        overrides={
            "S01_A2_GC_INITIAL_REVIEW": {
                "gc_bridge_ceiling_usd": 250_000,
            },
            "S01_B1_SUPPLIER_COMMITMENT": {
                "outside_financing_usd": 450_000,
            },
            "S01_B2_GC_INTEGRATED_PACKAGE": {
                "gc_bridge_usd": 250_000,
                "owner_funds_requested_usd": 150_000,
            },
            "S01_B4_OWNER_PACKAGE_DECISION": {
                "owner_funding_usd": 150_000,
                "owner_equity_usd": 100_000,
                "approved_standby_usd": 100_000,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "PARTIAL_RELEASE",
                "draw_release_usd": 760_000,
                "owner_equity_required_usd": 100_000,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
                "ship_action": "SHIP_BOTH",
            },
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "RELEASE",
                "lot_b_disposition": "RELEASE",
                "approved_shipping_value_usd": 1_350_000,
            },
            "S01_C4_OWNER_FINAL_POSITION": {
                "accepted_additional_cost_usd": 750_000,
                "owner_cost_share_usd": 0,
                "gc_cost_share_usd": 0,
                "supplier_cost_share_usd": 750_000,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "PHASED",
                "mobilization_tick": 15,
            },
        },
        expected={
            "status": "PROJECT_SUCCESS",
            "final_project_cost": 95_737_500,
            "completion_tick": 41,
            "s01_v2_project_success": True,
            "s01_v2_coalition_success": False,
        },
    ),
    "coordination_failure": _s01_v2_fixture(
        overrides={
            "S01_A1_SUPPLIER_APPLICATION": {
                "submitted_document_ids": S01_V2_DOCUMENT_IDS[:2],
            },
            "S01_A2_GC_INITIAL_REVIEW": {
                "provisional_certified_value_usd": 1_800_000,
                "backup_action": "NONE",
                "owner_lender_package_document_ids": S01_V2_DOCUMENT_IDS[:2],
                "inspector_package_document_ids": S01_V2_DOCUMENT_IDS[:2],
            },
            "S01_A3_OWNER_PROVISIONAL_POSITION": {
                "owner_funding_ceiling_usd": 0,
                "immediate_equity_ceiling_usd": 0,
            },
            "S01_A3_INSPECTOR_REVIEW_PLAN": {
                "inspection_scope": "DOCUMENT_ONLY",
                "inspection_tick": 12,
            },
            "S01_A3_ERECTOR_CAPACITY_OFFER": {
                "capacity_offer": "RELEASE",
                "hold_through_tick": 12,
                "standby_price_usd": 0,
            },
            "S01_A4_LENDER_PROVISIONAL_POSITION": {
                "maximum_draw_usd": 0,
                "advance_rate": 0.0,
                "escrow_cap_usd": 0,
            },
            "S01_B1_SUPPLIER_COMMITMENT": {
                "cure_plan": "NO_CURE",
                "supplier_cash_committed_usd": 0,
                "outside_financing_usd": 0,
                "outside_work_action": "ACCEPT_FULL",
                "lot_a_commitment_tick": 20,
                "lot_b_commitment_tick": 24,
            },
            "S01_B2_GC_INTEGRATED_PACKAGE": {
                "supplier_proposal_action": "REJECT",
                "final_certified_payment_usd": 0,
                "gc_bridge_usd": 0,
                "owner_funds_requested_usd": 0,
                "lender_draw_requested_usd": 0,
                "backup_action": "DROP",
            },
            "S01_B3_INSPECTOR_DISPOSITION": {
                "disposition": "NO_RELEASE",
                "maximum_releasable_value_usd": 0,
                "reinspection_tick": None,
            },
            "S01_B3_ERECTOR_BINDING_COMMITMENT": {
                "offer_action": "RELEASE",
                "capacity_commitment": "NONE",
                "mobilization_tick": None,
                "standby_compensation_usd": 0,
                "overtime_commitment": "NONE",
                "minimum_releasable_value_usd": 0,
            },
            "S01_B4_OWNER_PACKAGE_DECISION": {
                "package_action": "REJECT",
                "owner_funding_usd": 0,
                "owner_equity_usd": 0,
                "approved_standby_usd": 0,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "HOLD",
                "draw_release_usd": 0,
                "escrow_release_usd": 0,
                "owner_equity_required_usd": 0,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
                "ship_action": "HOLD_ALL",
            },
            "S01_C2_GC_RECOVERY_PLAN": {
                "recovery_plan": "ACCEPT_DELAY",
            },
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "HOLD",
                "lot_b_disposition": "HOLD",
                "approved_shipping_value_usd": 0,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "RELEASE",
                "mobilization_tick": 23,
                "remobilization_tick_if_released": 23,
            },
        },
        expected={
            "status_any_of": ["CRITICAL_PATH_DEADLOCK", "SCHEDULE_INFEASIBLE"],
            "final_project_cost": 97_520_000,
            "completion_tick": 50,
            "s01_v2_project_success": False,
        },
    ),
    "excessive_conservatism_failure": _s01_v2_fixture(
        overrides={
            "S01_A1_SUPPLIER_APPLICATION": {
                "submitted_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A2_GC_INITIAL_REVIEW": {
                "review_strategy": "FULL_INSPECTION",
                "backup_action": "RESERVE",
                "preliminary_erection_strategy": "HOLD",
                "owner_lender_package_document_ids": S01_V2_DOCUMENT_IDS,
                "inspector_package_document_ids": S01_V2_DOCUMENT_IDS,
            },
            "S01_A3_OWNER_PROVISIONAL_POSITION": {
                "owner_funding_ceiling_usd": 0,
                "immediate_equity_ceiling_usd": 0,
            },
            "S01_A3_INSPECTOR_REVIEW_PLAN": {
                "inspection_scope": "FULL_SEQUENCE",
                "inspection_tick": 13,
            },
            "S01_A3_ERECTOR_CAPACITY_OFFER": {
                "capacity_offer": "RELEASE",
                "hold_through_tick": 12,
                "standby_price_usd": 0,
            },
            "S01_A4_LENDER_PROVISIONAL_POSITION": {
                "maximum_draw_usd": 0,
                "advance_rate": 0.0,
                "escrow_cap_usd": 0,
            },
            "S01_B1_SUPPLIER_COMMITMENT": {
                "cure_plan": "LOT_A_CURE",
                "supplier_cash_committed_usd": 300_000,
                "outside_financing_usd": 0,
                "outside_work_action": "ACCEPT_PARTIAL",
                "lot_a_commitment_tick": 14,
                "lot_b_commitment_tick": 24,
            },
            "S01_B2_GC_INTEGRATED_PACKAGE": {
                "supplier_proposal_action": "COUNTER",
                "final_certified_payment_usd": 0,
                "gc_bridge_usd": 0,
                "owner_funds_requested_usd": 0,
                "lender_draw_requested_usd": 0,
                "backup_action": "MAINTAIN",
            },
            "S01_B3_INSPECTOR_DISPOSITION": {
                "disposition": "LOT_A_RELEASED",
                "maximum_releasable_value_usd": 950_000,
                "reinspection_tick": 18,
            },
            "S01_B3_ERECTOR_BINDING_COMMITMENT": {
                "offer_action": "RELEASE",
                "capacity_commitment": "NONE",
                "mobilization_tick": None,
                "standby_compensation_usd": 0,
                "overtime_commitment": "NONE",
                "minimum_releasable_value_usd": 0,
            },
            "S01_B4_OWNER_PACKAGE_DECISION": {
                "package_action": "REJECT",
                "owner_funding_usd": 0,
                "owner_equity_usd": 0,
                "approved_standby_usd": 0,
            },
            "S01_B5_LENDER_RELEASE_DECISION": {
                "release_action": "HOLD",
                "draw_release_usd": 0,
                "escrow_release_usd": 0,
                "owner_equity_required_usd": 0,
            },
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
                "ship_action": "SHIP_A",
            },
            "S01_C2_GC_RECOVERY_PLAN": {
                "recovery_plan": "ACCEPT_DELAY",
            },
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                "lot_a_disposition": "RELEASE",
                "lot_b_disposition": "HOLD",
                "approved_shipping_value_usd": 950_000,
            },
            "S01_C6_ERECTOR_MOBILIZATION": {
                "mobilization_action": "RELEASE",
                "mobilization_tick": 23,
                "remobilization_tick_if_released": 23,
            },
        },
        expected={
            "status": "SCHEDULE_INFEASIBLE",
            "final_project_cost": 97_760_000,
            "completion_tick": 50,
            "s01_v2_project_success": False,
        },
    ),
}


def _s01_v2_budget_blowout_fixture() -> dict[str, Any]:
    """Witness 6: money-heavy recovery breaches the budget ceiling on time.

    Layered on the conservative path: the coalition panics after the Lot B
    problem — backup activated on top of a retained supplier, full standby and
    overtime purchased, and a full price adjustment granted. Delivery lands at
    tick 45, comfortably inside the schedule deadline, but the spending crosses
    the $102M success ceiling. This pins BUDGET_INFEASIBLE as a reachable
    terminal class distinct from schedule and compliance failures.
    """
    decisions = deepcopy(S01_V2_FIXTURES["conservative_project_success"]["decisions"])
    overrides: dict[str, dict[str, Any]] = {
        "S01_B1_SUPPLIER_COMMITMENT": {"requested_price_adjustment_usd": 1_000_000},
        "S01_B2_GC_INTEGRATED_PACKAGE": {
            "supplier_price_adjustment_usd": 1_000_000
        },
        "S01_B3_ERECTOR_BINDING_COMMITMENT": {
            "standby_compensation_usd": 400_000,
            "overtime_commitment": "FULL",
        },
        "S01_B4_OWNER_PACKAGE_DECISION": {
            "approved_price_adjustment_usd": 1_000_000,
            "approved_standby_usd": 400_000,
        },
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": {
            "supplier_recovery_spend_usd": 300_000,
        },
        "S01_C2_GC_RECOVERY_PLAN": {"recovery_plan": "ACTIVATE_BACKUP"},
        "S01_C4_OWNER_FINAL_POSITION": {
            "accepted_additional_cost_usd": 1_500_000,
            "owner_cost_share_usd": 750_000,
            "gc_cost_share_usd": 500_000,
            "supplier_cost_share_usd": 250_000,
        },
        "S01_C6_ERECTOR_MOBILIZATION": {
            "mobilization_action": "OVERTIME",
            "incremental_cost_usd": 500_000,
        },
    }
    for node_id, params_ in overrides.items():
        option_id, base_params = decisions[node_id]
        decisions[node_id] = (option_id, {**base_params, **params_})
    return {
        "variant": "normal",
        "decisions": decisions,
        "expected": {
            "status": "BUDGET_INFEASIBLE",
            "final_project_cost": 102_405_000,
            "completion_tick": 45,
            "s01_v2_project_success": False,
        },
    }


S01_V2_FIXTURES["budget_blowout_failure"] = _s01_v2_budget_blowout_fixture()

S01OffsiteSteelDraw.fixtures = S01_V2_FIXTURES


SCENARIOS: dict[str, Scenario] = {
    "S00": S00BaseProjectNoPerturbation(),
    "S01": S01SteelMarketShock(),
    "S01_V1": S01SteelMarketShock(),
    "S01_V2": S01OffsiteSteelDraw(),
    "S02": S02CraneFailureWeather(),
    "S03": S03OwnerLiquidityShortfall(),
    "S04": S04WeldInspectionFailure(),
    "S05": S05LaborShortageInspection(),
}


def get_scenario(scenario_key: str) -> Scenario:
    try:
        return SCENARIOS[scenario_key]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {scenario_key!r}; expected one of {sorted(SCENARIOS)}") from exc
