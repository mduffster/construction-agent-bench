"""Run local Ollama agent checks without executing the full simulation."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constructbench.agents import LLMPolicy, OllamaModelAdapter
from constructbench.config import load_agent_configs, load_project_config, load_scenario_config
from constructbench.enums import AgentRole, LedgerEntryType
from constructbench.models import (
    AgentObservation,
    AgentRuntimeRecord,
    AgentSubmission,
    ModelSettings,
    PublicLedgerEntry,
    StateStore,
)
from constructbench.observations import ObservationBuilder
from constructbench.runner import SimulationRunner
from constructbench.runtime import BeliefUpdateHandler
from constructbench.state import initialize_state
from constructbench.validation import SubmissionValidator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_CONTEXT_TOKENS = 32768


@dataclass(frozen=True)
class AgentCheckResult:
    agent: AgentRole
    info_flow_valid: bool
    info_flow_basis_hit: bool
    info_flow_basis_ids: list[str]
    info_flow_belief: dict[str, Any]
    numeric_belief_present: bool
    context_valid: bool
    context_estimated_tokens: int
    context_limit: int
    updated_belief: bool
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent.value,
            "info_flow_valid": self.info_flow_valid,
            "info_flow_basis_hit": self.info_flow_basis_hit,
            "info_flow_basis_ids": self.info_flow_basis_ids,
            "info_flow_belief": self.info_flow_belief,
            "numeric_belief_present": self.numeric_belief_present,
            "context_valid": self.context_valid,
            "context_estimated_tokens": self.context_estimated_tokens,
            "context_limit": self.context_limit,
            "updated_belief": self.updated_belief,
            "errors": self.errors,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--first-agent", default=AgentRole.STEEL_SUPPLIER.value)
    parser.add_argument("--context-tokens", type=int, default=DEFAULT_CONTEXT_TOKENS)
    parser.add_argument("--synthetic-entries", type=int, default=160)
    args = parser.parse_args()

    first_agent = AgentRole(args.first_agent)
    remaining_agents = [agent for agent in AgentRole if agent != first_agent]
    ordered_agents = [first_agent, *remaining_agents]

    settings = ModelSettings(
        model_id=args.model,
        runtime="ollama",
        temperature=0.0,
        sampling_seed=7,
        max_input_tokens=args.context_tokens,
        max_output_tokens=1024,
        retry_count=1,
    )
    adapter = OllamaModelAdapter(args.model)
    validator = SubmissionValidator()

    results: list[AgentCheckResult] = []
    for index, agent in enumerate(ordered_agents):
        print(f"\n== Checking {agent.value} with {args.model} ==")
        result = run_agent_check(
            agent=agent,
            adapter=adapter,
            settings=settings,
            validator=validator,
            synthetic_entries=args.synthetic_entries,
        )
        results.append(result)
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))

        if index == 0 and not _passed(result):
            print("\nFirst-agent check failed; stopping before remaining agents.")
            break

    print("\n== Summary ==")
    print(json.dumps([result.as_dict() for result in results], indent=2, sort_keys=True))


def run_agent_check(
    agent: AgentRole,
    adapter: OllamaModelAdapter,
    settings: ModelSettings,
    validator: SubmissionValidator,
    synthetic_entries: int,
) -> AgentCheckResult:
    errors: list[str] = []

    observation, runner = _observation_for_agent(agent)
    expected_basis_id = _expected_basis_id(agent)
    original_belief = runner.state.beliefs_by_agent[agent]
    info_submission, info_valid, info_errors = _call_agent(
        observation,
        adapter,
        settings,
        validator,
        runner.state,
        apply_belief=True,
    )
    errors.extend(f"info_flow:{error}" for error in info_errors)
    info_flow_basis_hit = expected_basis_id in info_submission.belief_update.basis_ids
    if not info_flow_basis_hit:
        errors.append(f"info_flow:missing_basis_id:{expected_basis_id}")

    updated_belief = runner.state.beliefs_by_agent[agent] != original_belief
    numeric_belief_present = _numeric_belief_present(info_submission)
    if not updated_belief:
        errors.append("info_flow:belief_not_updated")
    if not numeric_belief_present:
        errors.append("info_flow:numeric_belief_not_present")

    synthetic_observation = _with_synthetic_context(observation, synthetic_entries)
    estimated_tokens = _estimate_tokens(synthetic_observation.model_dump_json())
    if estimated_tokens > settings.max_input_tokens:
        errors.append(
            f"context:estimated_tokens_exceed_limit:{estimated_tokens}>{settings.max_input_tokens}",
        )

    context_submission, context_valid, context_errors = _call_agent(
        synthetic_observation,
        adapter,
        settings,
        validator,
        runner.state,
        apply_belief=False,
    )
    _ = context_submission
    errors.extend(f"context:{error}" for error in context_errors)

    return AgentCheckResult(
        agent=agent,
        info_flow_valid=info_valid,
        info_flow_basis_hit=info_flow_basis_hit,
        info_flow_basis_ids=info_submission.belief_update.basis_ids,
        info_flow_belief=info_submission.belief_update.model_dump(mode="json"),
        numeric_belief_present=numeric_belief_present,
        context_valid=context_valid and estimated_tokens <= settings.max_input_tokens,
        context_estimated_tokens=estimated_tokens,
        context_limit=settings.max_input_tokens,
        updated_belief=updated_belief,
        errors=errors,
    )


def _call_agent(
    observation: AgentObservation,
    adapter: OllamaModelAdapter,
    settings: ModelSettings,
    validator: SubmissionValidator,
    state: StateStore,
    apply_belief: bool,
) -> tuple[AgentSubmission, bool, list[str]]:
    policy = LLMPolicy(adapter=adapter, settings=settings)
    submission = policy.decide(observation)
    validation = validator.validate(observation.agent_id.value, submission, state)
    record = AgentRuntimeRecord(
        agent_id=observation.agent_id,
        observation=observation,
        submission=submission,
        validation=validation,
        used_fallback=policy.last_used_fallback,
        raw_output=policy.last_raw_output,
        parse_errors=list(policy.last_parse_errors),
    )
    if apply_belief:
        BeliefUpdateHandler().apply(observation.agent_id, state, record)
        submission = record.submission
    errors = [*policy.last_parse_errors, *validation.errors]
    return submission, validation.valid and not policy.last_used_fallback, errors


def _observation_for_agent(agent: AgentRole) -> tuple[AgentObservation, SimulationRunner]:
    runner = _state_runner()
    builder = ObservationBuilder()
    if agent == AgentRole.STEEL_SUPPLIER:
        runner.run_until(8)
        tick_result = runner.advance_tick()
    else:
        tick_result = runner.run_until(8)[-1]
    return builder.build(agent, runner.state, tick_result.delivered), runner


def _state_runner() -> SimulationRunner:
    project_config = load_project_config(ROOT / "configs" / "project_baseline.yaml")
    role_configs = load_agent_configs(ROOT / "configs" / "agents")
    scenario_config = load_scenario_config(ROOT / "configs" / "scenarios" / "steel_shock.yaml")
    return SimulationRunner(initialize_state(project_config, role_configs), scenario_config)


def _expected_basis_id(agent: AgentRole) -> str:
    if agent == AgentRole.STEEL_SUPPLIER:
        return "supplier_impact_tick_9"
    return "public_steel_market_tick_8"


def _with_synthetic_context(
    observation: AgentObservation,
    synthetic_entries: int,
) -> AgentObservation:
    generated_entries = [
        PublicLedgerEntry(
            entry_id=f"synthetic_turn_summary_{index}",
            tick=max(0, observation.tick - 1),
            source="system",
            entry_type=LedgerEntryType.PUBLIC_FORECAST,
            linked_object_id="steel_contract",
            data={
                "summary": (
                    "Synthetic prior-turn context for context-window testing. "
                    "This entry repeats project cost, schedule, payment, inspection, "
                    "and steel delivery facts so the prompt approximates accumulated "
                    "history without running a full networked simulation."
                ),
                "index": index,
            },
        )
        for index in range(synthetic_entries)
    ]
    return observation.model_copy(
        deep=True,
        update={
            "new_public_entries": [
                *observation.new_public_entries,
                *generated_entries,
            ],
        },
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _numeric_belief_present(submission: AgentSubmission) -> bool:
    belief = submission.belief_update
    return (
        isinstance(belief.expected_completion_tick, int)
        and isinstance(belief.expected_final_cost, int)
        and isinstance(belief.probability_on_time, float)
        and isinstance(belief.probability_within_budget, float)
        and isinstance(belief.confidence, float)
    )


def _passed(result: AgentCheckResult) -> bool:
    return (
        result.info_flow_valid
        and result.info_flow_basis_hit
        and result.context_valid
        and result.updated_belief
        and result.numeric_belief_present
    )


if __name__ == "__main__":
    main()
