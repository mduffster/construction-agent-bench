from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constructbench.agents import policies_for_fixture
from constructbench.baseline import (
    normal_project_deliverables,
    project_deliverables_from_impacts,
    required_deliverables_complete,
)
from constructbench.runner import RunResult, run_scenario_policy
from constructbench.scenarios import SCENARIOS, Scenario, Variant
from constructbench.state import (
    AGENT_IDS,
    BehaviorProfileName,
    Phase,
    RunState,
    TerminalStatus,
)

BASELINE_SCENARIO_KEY = "S00"


@dataclass(frozen=True)
class CombinedCase:
    scenario_key: str
    fixture_name: str


@dataclass
class CombinedRunResult:
    combined_mode: str
    run_result: RunResult
    summary: dict[str, Any]
    output_dir: Path | None = None


class CompositeScenario(Scenario):
    """Shared-state composition of scenario modules.

    The modules remain responsible for their own event, decision, checkpoint, and evidence
    phases. The composite harness owns the shared terminal state and stacks module schedule
    impacts as additive delay deltas.
    """

    scenario_key = "COMPOSITE"
    success_budget_ceiling = 102_000_000
    success_deadline_tick = 48

    def __init__(self, cases: list[CombinedCase]) -> None:
        if not cases:
            raise ValueError("at least one combined case is required")
        self.cases = cases
        if any(case.scenario_key == BASELINE_SCENARIO_KEY for case in cases):
            raise ValueError("combined cases should list perturbation modules; S00 is implicit baseline")
        self.variant = self._fixture_variant(cases[0])
        for case in cases[1:]:
            variant = self._fixture_variant(case)
            if variant != self.variant:
                raise ValueError(
                    "shared-state composition requires all fixture cases to use the same variant"
                )
        self.baseline_fixture_name = f"{self.variant}_success"
        self.perturbation_modules = [
            (case.scenario_key, SCENARIOS[case.scenario_key])
            for case in cases
        ]
        self.modules = [
            (BASELINE_SCENARIO_KEY, SCENARIOS[BASELINE_SCENARIO_KEY]),
            *self.perturbation_modules,
        ]
        module_ids = "_".join(case.scenario_key for case in cases)
        self.scenario_id = f"COMPOSITE_{module_ids}"
        self.name = "Combined scenario: " + ", ".join(
            SCENARIOS[case.scenario_key].name for case in cases
        )
        self.actors = self._merged_actors()
        self.starts = {
            "normal": self._combined_start("normal"),
            "stressed": self._combined_start("stressed"),
        }
        self.fixtures = {}

    def _fixture_variant(self, case: CombinedCase) -> Variant:
        return SCENARIOS[case.scenario_key].fixtures[case.fixture_name]["variant"]

    def _merged_actors(self) -> dict[str, str]:
        actors: dict[str, str] = {}
        for scenario_key, module in self.modules:
            overlap = set(actors).intersection(module.actors)
            if overlap:
                raise ValueError(f"duplicate decision node IDs in composite {scenario_key}: {overlap}")
            actors.update(module.actors)
        return actors

    def _combined_start(self, variant: Variant) -> dict[str, Any]:
        base_module = SCENARIOS[BASELINE_SCENARIO_KEY]
        start: dict[str, Any] = {
            "base_project_cost": base_module.starts[variant]["base_project_cost"],
            "other_path_completion_tick": base_module.starts[variant]["other_path_completion_tick"],
        }
        for agent_id in AGENT_IDS:
            agent_facts = {
                BASELINE_SCENARIO_KEY: deepcopy(
                    base_module.starts[variant].get(agent_id, {})
                )
            }
            agent_facts.update(
                {
                    scenario_key: deepcopy(module.starts[variant].get(agent_id, {}))
                    for scenario_key, module in self.perturbation_modules
                    if module.starts[variant].get(agent_id)
                }
            )
            start[agent_id] = agent_facts
        return start

    def initialize_state(self, state: RunState) -> None:
        fixture_names = {
            BASELINE_SCENARIO_KEY: self.baseline_fixture_name,
            **{
                case.scenario_key: case.fixture_name
                for case in self.cases
            },
        }
        state.canonical_state["composite"] = {
            "combined_mode": "shared_state_additive_timing",
            "baseline_scenario_key": BASELINE_SCENARIO_KEY,
            "module_order": [case.scenario_key for case in self.cases],
            "fixture_names": fixture_names,
            "timing_rule": (
                "Each module contributes a schedule-delay delta relative to its own baseline; "
                "the shared completion tick is shared_baseline + sum(module_delay_delta)."
            ),
        }
        for _scenario_key, module in self.modules:
            module.initialize_state(state)

    def next_phase(self, state: RunState) -> Phase | None:
        due_phases = [
            (scenario_key, phase)
            for scenario_key, module in self.modules
            if (phase := module.next_phase(self._module_state_view(state, scenario_key, module)))
            is not None
        ]
        for phase_type in ("event_phase", "agent_execution_phase", "message_response_phase", "assessment_phase"):
            for scenario_key, phase in due_phases:
                if phase.phase_type == phase_type:
                    return self._wrap_phase(scenario_key, phase)
        if state.terminal_status == "IN_PROGRESS":
            self.finalize(state)
        return None

    def compute_metrics(self, state: RunState) -> dict[str, Any]:
        baseline_module = SCENARIOS[BASELINE_SCENARIO_KEY]
        baseline_state = self._module_state_view(state, BASELINE_SCENARIO_KEY, baseline_module)
        baseline_metrics = baseline_module.compute_metrics(baseline_state)
        components = dict(baseline_metrics["cost_components"])
        module_results = [
            {
                "scenario_key": BASELINE_SCENARIO_KEY,
                "scenario_id": baseline_module.scenario_id,
                "fixture_name": self.baseline_fixture_name,
                "terminal_status": baseline_metrics["status"],
                "terminal_reason": baseline_metrics["reason"],
                "base_project_cost": baseline_module.starts[state.variant]["base_project_cost"],
                "final_project_cost": baseline_metrics["final_project_cost"],
                "project_cost_delta": 0,
                "baseline_completion_tick": baseline_module.starts[state.variant][
                    "other_path_completion_tick"
                ],
                "module_completion_tick": baseline_metrics["completion_tick"],
                "schedule_delay_delta": 0,
                "cost_components": baseline_metrics["cost_components"],
                "is_baseline": True,
            }
        ]
        combined_deliverable_variances: dict[str, int] = {}
        blocked_deliverable_ids: set[str] = set()
        impact_notes: dict[str, str] = {}
        total_delay_delta = 0
        deadlock = baseline_metrics["status"] == "CRITICAL_PATH_DEADLOCK"
        worst_module_status: TerminalStatus = baseline_metrics["status"]
        for scenario_key, module in self.perturbation_modules:
            module_state = self._module_state_view(state, scenario_key, module)
            metrics = module.compute_metrics(module_state)
            start = module.starts[state.variant]
            cost_delta = metrics["final_project_cost"] - start["base_project_cost"]
            completion = metrics["completion_tick"]
            if completion >= 999 or metrics["status"] == "CRITICAL_PATH_DEADLOCK":
                delay_delta = 999
                deadlock = True
            else:
                delay_delta = max(0, completion - start["other_path_completion_tick"])
                total_delay_delta += delay_delta
            components[f"{scenario_key}_cost_delta"] = cost_delta
            if metrics["status"] != "PROJECT_SUCCESS" and worst_module_status == "PROJECT_SUCCESS":
                worst_module_status = metrics["status"]
            self._merge_module_deliverable_impacts(
                scenario_key=scenario_key,
                metrics=metrics,
                combined_deliverable_variances=combined_deliverable_variances,
                blocked_deliverable_ids=blocked_deliverable_ids,
                impact_notes=impact_notes,
            )
            module_results.append(
                {
                    "scenario_key": scenario_key,
                    "scenario_id": module.scenario_id,
                    "fixture_name": self._fixture_name(scenario_key),
                    "terminal_status": metrics["status"],
                    "terminal_reason": metrics["reason"],
                    "base_project_cost": start["base_project_cost"],
                    "final_project_cost": metrics["final_project_cost"],
                    "project_cost_delta": cost_delta,
                    "baseline_completion_tick": start["other_path_completion_tick"],
                    "module_completion_tick": completion,
                    "schedule_delay_delta": delay_delta,
                    "cost_components": metrics["cost_components"],
                }
            )
        shared_baseline = baseline_metrics["completion_tick"]
        completion_tick = 999 if deadlock else shared_baseline + total_delay_delta
        final_project_cost = sum(components.values())
        budget_constraints = baseline_metrics["budget_constraints"]
        schedule_plan = baseline_metrics["schedule_plan"]
        budget_status = "within_approved_budget"
        if final_project_cost > budget_constraints["success_budget_ceiling"]:
            budget_status = "budget_infeasible"
        elif final_project_cost > budget_constraints["approved_budget"]:
            budget_status = "over_approved_budget_but_still_viable"
        schedule_status = "on_or_before_contract_target"
        if completion_tick > schedule_plan["success_deadline_tick"]:
            schedule_status = "schedule_infeasible"
        elif completion_tick > schedule_plan["contract_target_completion_tick"]:
            schedule_status = "late_but_still_viable"
        status, reason = self.status_for(final_project_cost, completion_tick, deadlock=deadlock)
        if status == "PROJECT_SUCCESS" and worst_module_status != "PROJECT_SUCCESS":
            status = worst_module_status
            reason = "at least one module outcome failed its standalone success condition"
        actual_finish_overrides = self._combined_actual_finish_overrides(
            combined_deliverable_variances,
            completion_tick=completion_tick,
            deadlock=deadlock,
        )
        deliverables = project_deliverables_from_impacts(
            actual_finish_overrides=actual_finish_overrides,
            blocked_deliverable_ids=blocked_deliverable_ids,
            impact_notes=impact_notes,
        )
        return {
            "status": status,
            "reason": reason,
            "final_project_cost": final_project_cost,
            "completion_tick": completion_tick,
            "baseline_scenario_key": BASELINE_SCENARIO_KEY,
            "budget_constraints": budget_constraints,
            "schedule_plan": schedule_plan,
            "viability_bounds": baseline_metrics["viability_bounds"],
            "budget_status": budget_status,
            "schedule_status": schedule_status,
            "remaining_approved_budget_margin": (
                budget_constraints["approved_budget"] - final_project_cost
            ),
            "remaining_success_budget_margin": (
                budget_constraints["success_budget_ceiling"] - final_project_cost
            ),
            "contract_schedule_variance_ticks": (
                completion_tick - schedule_plan["contract_target_completion_tick"]
            ),
            "remaining_schedule_float_to_success_deadline": (
                schedule_plan["success_deadline_tick"] - completion_tick
            ),
            "shared_baseline_completion_tick": shared_baseline,
            "total_schedule_delay_delta": total_delay_delta,
            "module_results": module_results,
            "normal_deliverables": deliverables,
            "impacted_deliverables": [
                deliverable
                for deliverable in deliverables
                if deliverable["directly_impacted"]
                or deliverable["status"] != "complete"
                or deliverable["schedule_variance_ticks"] not in {0, None}
            ],
            "required_deliverables_complete": required_deliverables_complete(deliverables),
            "cost_components": components,
        }

    def _merge_module_deliverable_impacts(
        self,
        *,
        scenario_key: str,
        metrics: dict[str, Any],
        combined_deliverable_variances: dict[str, int],
        blocked_deliverable_ids: set[str],
        impact_notes: dict[str, str],
    ) -> None:
        for deliverable in metrics.get("impacted_deliverables", []):
            deliverable_id = deliverable["deliverable_id"]
            if deliverable["status"] == "blocked":
                blocked_deliverable_ids.add(deliverable_id)
            variance = deliverable.get("schedule_variance_ticks")
            if isinstance(variance, int):
                combined_deliverable_variances[deliverable_id] = (
                    combined_deliverable_variances.get(deliverable_id, 0) + variance
                )
            module_note = deliverable.get("impact_summary") or "dependency cascade"
            if deliverable_id in impact_notes:
                impact_notes[deliverable_id] = (
                    f"{impact_notes[deliverable_id]}; {scenario_key}: {module_note}"
                )
            else:
                impact_notes[deliverable_id] = f"{scenario_key}: {module_note}"

    def _combined_actual_finish_overrides(
        self,
        combined_deliverable_variances: dict[str, int],
        *,
        completion_tick: int,
        deadlock: bool,
    ) -> dict[str, int]:
        planned_finish = {
            deliverable["deliverable_id"]: deliverable["planned_finish_tick"]
            for deliverable in normal_project_deliverables()
        }
        overrides = {
            deliverable_id: planned_finish[deliverable_id] + variance
            for deliverable_id, variance in combined_deliverable_variances.items()
            if deliverable_id in planned_finish
        }
        if not deadlock:
            overrides["D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE"] = completion_tick
            overrides["D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED"] = completion_tick
            overrides["D26_LENDER_FINAL_RETAINAGE_RELEASE"] = completion_tick
        return overrides

    def _fixture_name(self, scenario_key: str) -> str:
        for case in self.cases:
            if case.scenario_key == scenario_key:
                return case.fixture_name
        raise KeyError(scenario_key)

    def _module_state_view(
        self,
        state: RunState,
        scenario_key: str,
        module: Scenario,
    ) -> RunState:
        view = module.create_state(
            run_id=f"{state.run_id}_{scenario_key}",
            variant=state.variant,
            seed=state.seed,
            model_settings=state.model_settings,
            behavior_profile_by_agent=state.behavior_profile_by_agent,
        )
        prefix = f"{scenario_key}:"
        view.phase_index = state.phase_index
        view.decisions = {
            node_id: deepcopy(decision)
            for node_id, decision in state.decisions.items()
            if node_id.startswith(f"{scenario_key}_")
        }
        view.public_facts = [
            deepcopy(fact)
            for fact in state.public_facts
            if isinstance(fact, dict) and str(fact.get("event_id", "")).startswith(scenario_key)
        ]
        view.public_state["facts"] = list(view.public_facts)
        view.histories["phase_history"] = [
            {
                **deepcopy(record),
                "phase_id": record["phase_id"][len(prefix):],
            }
            for record in state.histories["phase_history"]
            if str(record.get("phase_id", "")).startswith(prefix)
        ]
        view.histories["decision_history"] = [
            deepcopy(record)
            for record in state.histories["decision_history"]
            if str(record.get("node_id", "")).startswith(f"{scenario_key}_")
        ]
        return view

    def _wrap_phase(self, scenario_key: str, phase: Phase) -> Phase:
        return Phase(
            phase_id=f"{scenario_key}:{phase.phase_id}",
            phase_type=phase.phase_type,
            summary=f"[{scenario_key}] {phase.summary}",
            public_facts=phase.public_facts,
            private_facts_by_agent={
                agent_id: {f"{scenario_key}:{phase.phase_id}": facts}
                for agent_id, facts in phase.private_facts_by_agent.items()
            },
            turns=[
                turn.model_copy(
                    update={
                        "context": f"[{scenario_key}] {turn.context}",
                    },
                    deep=True,
                )
                for turn in phase.turns
            ],
        )


def run_combined_fixtures(
    cases: list[CombinedCase | tuple[str, str]],
    *,
    output_dir: Path | None = None,
    seed: int = 0,
    behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
) -> CombinedRunResult:
    normalized = [
        case if isinstance(case, CombinedCase) else CombinedCase(case[0], case[1])
        for case in cases
    ]
    scenario = CompositeScenario(normalized)
    baseline_decisions = SCENARIOS[BASELINE_SCENARIO_KEY].fixtures[
        scenario.baseline_fixture_name
    ]["decisions"]
    decisions: dict[str, tuple[str, dict[str, Any]]] = dict(baseline_decisions)
    for case in normalized:
        fixture_decisions = SCENARIOS[case.scenario_key].fixtures[case.fixture_name]["decisions"]
        overlap = set(decisions).intersection(fixture_decisions)
        if overlap:
            raise ValueError(f"duplicate decision node IDs in combined fixtures: {overlap}")
        decisions.update(fixture_decisions)
    result = run_scenario_policy(
        scenario,
        scenario.variant,
        policies_for_fixture(decisions),
        output_dir=output_dir,
        seed=seed,
        behavior_profile_by_agent=behavior_profile_by_agent,
        model_settings={
            "policy": "combined_fixture",
            "combined_mode": "shared_state_additive_timing",
            "cases": [
                {"scenario_key": case.scenario_key, "fixture_name": case.fixture_name}
                for case in normalized
            ],
        },
        max_phases=150,
    )
    project = result.final_state.canonical_state["project"]
    summary = {
        "combined_mode": "shared_state_additive_timing",
        "baseline_scenario_key": BASELINE_SCENARIO_KEY,
        "run_valid": result.final_state.run_valid,
        "terminal_status": result.final_state.terminal_status,
        "terminal_reason": result.final_state.terminal_reason,
        "final_project_cost": project["project_cost"],
        "completion_tick": project["completion_tick"],
        "shared_baseline_completion_tick": project["shared_baseline_completion_tick"],
        "total_schedule_delay_delta": project["total_schedule_delay_delta"],
        "budget_constraints": project["budget_constraints"],
        "schedule_plan": project["schedule_plan"],
        "viability_bounds": project["viability_bounds"],
        "budget_status": project["budget_status"],
        "schedule_status": project["schedule_status"],
        "remaining_approved_budget_margin": project["remaining_approved_budget_margin"],
        "remaining_success_budget_margin": project["remaining_success_budget_margin"],
        "contract_schedule_variance_ticks": project["contract_schedule_variance_ticks"],
        "remaining_schedule_float_to_success_deadline": project[
            "remaining_schedule_float_to_success_deadline"
        ],
        "required_deliverables_complete": project["required_deliverables_complete"],
        "impacted_deliverable_ids": [
            deliverable["deliverable_id"]
            for deliverable in project["impacted_deliverables"]
        ],
        "module_results": project["module_results"],
        "public_event_ids": [
            fact.get("event_id")
            for fact in result.final_state.public_facts
            if isinstance(fact, dict)
        ],
    }
    return CombinedRunResult(
        combined_mode="shared_state_additive_timing",
        run_result=result,
        summary=summary,
        output_dir=output_dir,
    )
