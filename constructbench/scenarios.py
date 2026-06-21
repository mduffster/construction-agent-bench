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
from constructbench.manifest import canonical_json_sha256
from constructbench.payoffs import build_s01_payoff_ledger
from constructbench.state import (
    AGENT_IDS,
    AgentBriefing,
    AssessmentEvidence,
    BehaviorProfileName,
    DecisionOption,
    DecisionRequest,
    DecisionSelection,
    GoalProfile,
    Phase,
    PhaseTurn,
    RunState,
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

    def create_state(
        self,
        *,
        run_id: str,
        variant: Variant,
        seed: int = 0,
        model_settings: dict[str, Any] | None = None,
        behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
    ) -> RunState:
        behavior_profiles = validate_behavior_profiles(behavior_profile_by_agent)
        goals = goal_profiles(behavior_profiles)
        start = deepcopy(self.starts[variant])
        baseline_plan = normal_project_plan(variant)
        baseline_impact = scenario_baseline_impact(self.scenario_key)
        baseline_budget = baseline_plan["budget_constraints"]
        baseline_schedule = baseline_plan["schedule_plan"]
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
            "scenario": {
                "scenario_id": self.scenario_id,
                "scenario_key": self.scenario_key,
                "scenario_class_name": self.__class__.__name__,
                "variant": variant,
                "success_budget_ceiling": self.success_budget_ceiling,
                "success_deadline_tick": self.success_deadline_tick,
                "baseline_impact": baseline_impact,
                "scenario_start_hash": canonical_json_sha256(start),
            },
        }
        private = {
            agent_id: {
                "agent_id": agent_id,
                "private_facts": deepcopy(start.get(agent_id, {})),
            }
            for agent_id in AGENT_IDS
        }
        state = RunState(
            run_id=run_id,
            scenario_id=self.scenario_id,
            variant=variant,
            seed=seed,
            model_settings=model_settings or {},
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
        start = self.starts[state.variant]
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
    actors = {
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
        if "S01_SUPPLIER_SOURCE_PLAN" not in state.decisions:
            return Phase(
                phase_id="supplier_source_and_commercial",
                phase_type="agent_execution_phase",
                summary="Steel supplier chooses its sourcing plan and any commercial request.",
                turns=[
                    PhaseTurn(
                        agent_id="steel_supplier",
                        context=(
                            "Choose the post-shock steel source and any commercial request. "
                            "Source choices affect your organization's cash and margin: expedite fees "
                            "and alternate deposits are supplier cash costs; approved advances improve "
                            "current cash but reduce future receivable by the same amount."
                        ),
                        required_decisions=[
                            single(
                                "S01_SUPPLIER_SOURCE_PLAN",
                                "steel_supplier",
                                "Choose the steel sourcing plan now.",
                                [
                                    option("current_expedited", "Pay expedite fee to preserve the baseline date."),
                                    option("current_standard", "Use current source on standard lead time."),
                                    option("approved_alternate", "Use an approved alternate source."),
                                    option("nonapproved_alternate", "Use a faster nonapproved alternate source."),
                                    option("declare_nonperformance", "Declare inability to perform."),
                                ],
                            ),
                            params(
                                "S01_SUPPLIER_COMMERCIAL_REQUEST",
                                "steel_supplier",
                                "Record requested commercial changes.",
                                {
                                    "price_amendment_request": [0, 600_000, 900_000, 1_400_000],
                                    "delivery_date_amendment_request": [None, 14, 15, 16, 17, 18, 19],
                                    "advance_payment_request": [0, 500_000, 600_000],
                                },
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

    def _supplier_plan_facts(self, state: RunState) -> list[dict[str, Any]]:
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        commercial = self.parameters(state, "S01_SUPPLIER_COMMERCIAL_REQUEST")
        if source is None:
            return []
        source_delivery = {
            "normal": {
                "current_expedited": 14,
                "current_standard": 18,
                "approved_alternate": 16,
                "nonapproved_alternate": 15,
                "declare_nonperformance": None,
            },
            "stressed": {
                "current_expedited": 15,
                "current_standard": 19,
                "approved_alternate": 17,
                "nonapproved_alternate": 16,
                "declare_nonperformance": None,
            },
        }
        return [
            {
                "source": "direct_effect",
                "event_id": "S01_SUPPLIER_PLAN_EFFECT",
                "summary": "Supplier source plan and resulting delivery effect are available for this response decision.",
                "supplier_source_plan": source,
                "expected_steel_delivery_tick": source_delivery[state.variant][source],
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
        start = self.starts[state.variant]
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
        supplier_terminal_margin = contract_receivable - production_cost

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
        components = self.base_components(state)
        source = self.selected(state, "S01_SUPPLIER_SOURCE_PLAN")
        review = self.selected(state, "S01_INSPECTOR_SOURCE_REVIEW")
        gc = self.selected(state, "S01_GC_PROCUREMENT_PLAN")
        labor = self.selected(state, "S01_LABOR_MOBILIZATION")
        missed_delivery_gc_response = self.selected(state, "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE")
        missed_delivery_labor_response = self.selected(state, "S01_LABOR_STEEL_DELAY_RESPONSE")
        emergency = self.selected(state, "S01_GC_EMERGENCY_PROCUREMENT")
        source_delivery = {
            "normal": {
                "current_expedited": 14,
                "current_standard": 18,
                "approved_alternate": 16,
                "nonapproved_alternate": 15,
            },
            "stressed": {
                "current_expedited": 15,
                "current_standard": 19,
                "approved_alternate": 17,
                "nonapproved_alternate": 16,
            },
        }
        delivery = 999
        deadlock = False
        tail = 26
        if source == "declare_nonperformance" or source is None:
            deadlock = True
        else:
            delivery = source_delivery[state.variant][source]
        if source == "nonapproved_alternate":
            if review == "approve_with_testing":
                components["source_testing"] = 200_000
                delivery += 1
            elif review == "reject":
                delivery = 999
                deadlock = True
        if gc == "resequence_around_delivery":
            components["resequencing"] = 300_000
            tail = 24
        elif gc == "split_package_with_secondary_supplier":
            components["secondary_supplier"] = 1_300_000
            delivery = 16 if state.variant == "normal" else 17
            tail = 25
            deadlock = False
        elif gc == "replace_supplier":
            components["replacement_supplier"] = 2_400_000
            delivery = 23 if state.variant == "normal" else 24
            tail = 26
            deadlock = False
        if emergency == "emergency_split_package":
            components["emergency_split_package"] = 1_800_000
            delivery = 21 if state.variant == "normal" else 22
            tail = 25
            deadlock = False
        elif emergency == "emergency_replace_supplier":
            components["emergency_replacement"] = 2_400_000
            delivery = 23 if state.variant == "normal" else 24
            tail = 26
            deadlock = False
        elif emergency == "abandon_steel_scope":
            deadlock = True
        if labor == "flexible_hold":
            components["labor_flexible_hold"] = 200_000
        elif labor == "mobilize_after_confirmed_delivery":
            tail += 1
        elif labor == "mobilize_tick_14" and delivery < 999 and delivery > 14:
            components["labor_idle"] = (delivery - 14) * 400_000
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
                components["missed_delivery_recovery_coordination"] = 150_000
                if delivery < 999:
                    delivery = max(contractual_delivery_due_tick + 1, delivery - 1)
            elif missed_delivery_gc_response == "activate_secondary_source_after_miss":
                components["secondary_source_after_miss"] = 1_100_000
                delivery = min(delivery, contractual_delivery_due_tick + 4)
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
        ) * self.project_delay_overhead_per_tick
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
            start=self.starts[state.variant],
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


SCENARIOS: dict[str, Scenario] = {
    "S00": S00BaseProjectNoPerturbation(),
    "S01": S01SteelMarketShock(),
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
