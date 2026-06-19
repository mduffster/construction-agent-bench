"""Single-run and batch-run orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from constructbench.agents import LLMPolicy, OllamaModelAdapter
from constructbench.config import load_agent_configs, load_project_config, load_scenario_config
from constructbench.enums import (
    AgentRole,
    AssessmentUpdateMode,
    BehaviorProfile,
    BreachProfile,
    ResourceConditionLevel,
)
from constructbench.metrics import calculate_final_metrics
from constructbench.models import ModelSettings
from constructbench.observations import ObservationBuilder
from constructbench.reporting import RunLogger, build_analysis_packet
from constructbench.runner import SimulationRunner
from constructbench.runtime import AgentManager, default_scripted_policies
from constructbench.safety import SafetyEngine
from constructbench.state import initialize_state
from constructbench.transitions import TransitionResolver

PolicyMode = Literal["scripted", "ollama"]


def run_single(
    *,
    project_config_path: str | Path,
    agent_config_dir: str | Path,
    scenario_config_path: str | Path,
    output_root: str | Path,
    policy_mode: PolicyMode = "scripted",
    model_id: str = "scripted",
    random_seed: int = 7,
    oversight_condition: str = "normal_operations",
    breach_profile: str | BreachProfile = BreachProfile.EASY,
    assessment_update_mode: str | AssessmentUpdateMode = AssessmentUpdateMode.SCALAR_BASELINE,
    condition_overrides: dict[str | AgentRole, str | ResourceConditionLevel] | None = None,
    behavior_overrides: dict[str | AgentRole, str | BehaviorProfile] | None = None,
    run_id: str | None = None,
    max_tick: int | None = None,
) -> Path:
    """Run one scenario and write Phase 5 artifacts."""
    project_config = load_project_config(project_config_path)
    role_configs = load_agent_configs(agent_config_dir)
    scenario_config = load_scenario_config(scenario_config_path)
    resolved_breach_profile = (
        breach_profile
        if isinstance(breach_profile, BreachProfile)
        else BreachProfile(breach_profile)
    )
    resolved_assessment_update_mode = (
        assessment_update_mode
        if isinstance(assessment_update_mode, AssessmentUpdateMode)
        else AssessmentUpdateMode(assessment_update_mode)
    )
    state = initialize_state(
        project_config,
        role_configs,
        condition_overrides=condition_overrides,
        behavior_overrides=behavior_overrides,
    )
    runner = SimulationRunner(state, scenario_config)

    resolved_run_id = run_id or _default_run_id(
        scenario_config.scenario_id,
        policy_mode,
        random_seed,
    )
    output_dir = Path(output_root) / resolved_run_id
    logger = RunLogger(output_dir)
    final_tick = max_tick if max_tick is not None else scenario_config.max_tick

    run_config: dict[str, Any] = {
        "run_id": resolved_run_id,
        "scenario_id": scenario_config.scenario_id,
        "random_seed": random_seed,
        "model_id": model_id,
        "policy_mode": policy_mode,
        "policy_profile_by_agent": {
            role.value: config.policy_profile.value for role, config in state.role_configs.items()
        },
        "resource_condition_by_agent": {
            role.value: private.resource_condition_level.value
            for role, private in state.private_by_agent.items()
        },
        "behavior_profile_by_agent": {
            role.value: private.behavior_profile.value
            for role, private in state.private_by_agent.items()
        },
        "oversight_condition": oversight_condition,
        "breach_profile": resolved_breach_profile.value,
        "assessment_update_mode": resolved_assessment_update_mode.value,
        "max_tick": final_tick,
        "agent_activation_history": [],
        "validation_failures": [],
        "fallback_actions": [],
        "transition_rejections": [],
        "final_termination_reason": "max_tick_reached",
    }
    logger.write_json("run_config.json", run_config)

    policies = _policies(policy_mode, model_id, random_seed)
    agent_manager = AgentManager(
        policies,
        observation_builder=ObservationBuilder(
            assessment_update_mode=resolved_assessment_update_mode,
        ),
    )
    transition_resolver = TransitionResolver()
    safety_engine = SafetyEngine(
        scenario_config,
        breach_profile=resolved_breach_profile,
        oversight_condition=oversight_condition,
    )
    turn_summaries: list[dict[str, Any]] = []

    logger.append_jsonl("state_snapshots.jsonl", {"run_id": resolved_run_id, **state.to_snapshot()})
    while state.canonical.tick < final_tick:
        public_start_index = len(state.public.ledger)
        private_message_start_index = len(state.private_messages)
        breach_start_index = len(state.canonical.breach_records)
        finding_start_index = len(state.oversight_findings)
        disclosure_start_index = len(state.disclosure_assessments)
        trust_update_start_index = len(state.trust_updates)
        expectation_update_start_index = len(state.expectation_update_records)
        tick_result = runner.advance_tick()
        agent_turn = agent_manager.process_tick(tick_result, state)
        transition_result = transition_resolver.apply(
            agent_turn,
            state,
            scenario_config.default_message_delay_ticks,
        )
        safety_result = safety_engine.evaluate(state)
        turn_summary = logger.write_tick_artifacts(
            resolved_run_id,
            state,
            tick_result,
            agent_turn,
            transition_result,
            safety_result,
            public_start_index,
            private_message_start_index,
            breach_start_index,
            finding_start_index,
            disclosure_start_index,
            trust_update_start_index,
            expectation_update_start_index,
        )
        turn_summaries.append(turn_summary)

        activation_history = run_config["agent_activation_history"]
        if not isinstance(activation_history, list):
            raise TypeError("agent_activation_history must be a list")
        activation_history.append(
            {
                "tick": tick_result.tick,
                "active_agents": [agent.value for agent in tick_result.active_agents],
            },
        )
        for record in agent_turn.records:
            if not record.validation.valid:
                validation_failures = run_config["validation_failures"]
                if not isinstance(validation_failures, list):
                    raise TypeError("validation_failures must be a list")
                validation_failures.append(
                    {
                        "tick": tick_result.tick,
                        "agent_id": record.agent_id.value,
                        "errors": record.validation.errors,
                    },
                )
            if record.used_fallback:
                fallback_actions = run_config["fallback_actions"]
                if not isinstance(fallback_actions, list):
                    raise TypeError("fallback_actions must be a list")
                fallback_actions.append(
                    {"tick": tick_result.tick, "agent_id": record.agent_id.value},
                )
        if transition_result.rejected:
            transition_rejections = run_config["transition_rejections"]
            if not isinstance(transition_rejections, list):
                raise TypeError("transition_rejections must be a list")
            transition_rejections.extend(transition_result.rejected)

    final_metrics = calculate_final_metrics(state)
    analysis_packet = build_analysis_packet(
        run_config,
        scenario_config,
        state,
        turn_summaries,
    )
    logger.write_json("run_config.json", run_config)
    logger.write_json("final_metrics.json", final_metrics)
    logger.write_json("analysis_packet.json", analysis_packet)
    return output_dir


def run_batch(
    *,
    project_config_path: str | Path,
    agent_config_dir: str | Path,
    scenario_config_path: str | Path,
    output_root: str | Path,
    policy_mode: PolicyMode,
    model_id: str,
    seeds: list[int],
    oversight_conditions: list[str],
    max_tick: int | None = None,
    breach_profile: str | BreachProfile = BreachProfile.EASY,
    assessment_update_mode: str | AssessmentUpdateMode = AssessmentUpdateMode.SCALAR_BASELINE,
    condition_overrides: dict[str | AgentRole, str | ResourceConditionLevel] | None = None,
    behavior_overrides: dict[str | AgentRole, str | BehaviorProfile] | None = None,
) -> list[Path]:
    """Run a small batch over seeds and oversight labels."""
    outputs: list[Path] = []
    for seed in seeds:
        for oversight_condition in oversight_conditions:
            run_id = (
                f"{_default_run_id(Path(scenario_config_path).stem, policy_mode, seed)}"
                f"_{oversight_condition}"
            )
            outputs.append(
                run_single(
                    project_config_path=project_config_path,
                    agent_config_dir=agent_config_dir,
                    scenario_config_path=scenario_config_path,
                    output_root=output_root,
                    policy_mode=policy_mode,
                    model_id=model_id,
                    random_seed=seed,
                    oversight_condition=oversight_condition,
                    breach_profile=breach_profile,
                    assessment_update_mode=assessment_update_mode,
                    condition_overrides=condition_overrides,
                    behavior_overrides=behavior_overrides,
                    run_id=run_id,
                    max_tick=max_tick,
                ),
            )
    return outputs


def _policies(
    policy_mode: PolicyMode,
    model_id: str,
    random_seed: int,
) -> dict[AgentRole, Any]:
    if policy_mode == "scripted":
        return default_scripted_policies()

    settings = ModelSettings(
        model_id=model_id,
        runtime="ollama",
        temperature=0.0,
        sampling_seed=random_seed,
        max_input_tokens=32768,
        max_output_tokens=1024,
        retry_count=1,
    )
    adapter = OllamaModelAdapter(model_id)
    return {role: LLMPolicy(adapter=adapter, settings=settings) for role in AgentRole}


def _default_run_id(scenario_id: str, policy_mode: str, random_seed: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"run_{scenario_id}_{policy_mode}_{random_seed}_{timestamp}"
