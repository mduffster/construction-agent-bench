from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from constructbench.agents import EmptyPolicy
from constructbench.focal import S01_COMMERCIAL_NEUTRAL_POLICY_ID, build_focal_policies
from constructbench.models import (
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
    DEFAULT_OLLAMA_MODEL,
    AnthropicModelAdapter,
    LLMPolicy,
    OllamaModelAdapter,
    assert_ollama_model_available,
    make_anthropic_policies,
    make_ollama_policies,
)
from constructbench.runner import run_fixture, run_policy
from constructbench.scenarios import SCENARIOS
from constructbench.state import AGENT_IDS, default_behavior_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one ConstructBench scenario.")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument("--fixture", choices=["normal_success", "normal_failure", "stressed_success", "stressed_failure"])
    parser.add_argument("--policy", choices=["fixture", "llm", "focal", "no_decision"], default="fixture")
    parser.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    parser.add_argument("--model", default=None)
    parser.add_argument("--focal-agent", choices=AGENT_IDS, default="steel_supplier")
    parser.add_argument("--scenario-instance-id")
    parser.add_argument(
        "--behavior-profile",
        choices=["collaborative", "selfish", "passive"],
        default="collaborative",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--debug-model-io", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or Path("outputs") / f"{args.scenario}_{args.policy}_{stamp}"
    model = args.model or (
        DEFAULT_ANTHROPIC_HAIKU_MODEL
        if args.provider == "anthropic"
        else DEFAULT_OLLAMA_MODEL
    )
    behavior_profiles = default_behavior_profiles(args.behavior_profile)
    if args.policy == "fixture":
        fixture = args.fixture or f"{args.variant}_success"
        if fixture not in SCENARIOS[args.scenario].fixtures:
            raise SystemExit(f"unknown fixture {fixture} for {args.scenario}")
        result = run_fixture(
            args.scenario,
            fixture,
            output_dir=output_dir,
            scenario_instance_id=args.scenario_instance_id,
            behavior_profile_by_agent=behavior_profiles,
        )
    elif args.policy == "llm":
        if args.provider == "anthropic":
            policies = make_anthropic_policies(model)
        else:
            policies = make_ollama_policies(model)
        result = run_policy(
            args.scenario,
            args.variant,
            policies,
            output_dir=output_dir,
            model_settings={
                "policy": "llm",
                "provider": args.provider,
                "model": model,
                "behavior_profile": args.behavior_profile,
            },
            scenario_instance_id=args.scenario_instance_id,
            behavior_profile_by_agent=behavior_profiles,
            debug_model_io=args.debug_model_io,
        )
    elif args.policy == "focal":
        focal_policy = _single_llm_policy(args.provider, model, args.focal_agent)
        policies = build_focal_policies(
            args.scenario,
            args.focal_agent,
            focal_policy,
            counterparty_policy_id=S01_COMMERCIAL_NEUTRAL_POLICY_ID,
        )
        result = run_policy(
            args.scenario,
            args.variant,
            policies,
            output_dir=output_dir,
            model_settings={
                "policy": "focal",
                "provider": args.provider,
                "model": model,
                "focal_agent_id": args.focal_agent,
                "counterparty_policy_id": S01_COMMERCIAL_NEUTRAL_POLICY_ID,
                "behavior_profile": args.behavior_profile,
            },
            scenario_instance_id=args.scenario_instance_id,
            behavior_profile_by_agent=behavior_profiles,
            debug_model_io=args.debug_model_io,
        )
    else:
        result = run_policy(
            args.scenario,
            args.variant,
            {agent_id: EmptyPolicy() for agent_id in AGENT_IDS},
            output_dir=output_dir,
            model_settings={"policy": "no_decision", "behavior_profile": args.behavior_profile},
            scenario_instance_id=args.scenario_instance_id,
            behavior_profile_by_agent=behavior_profiles,
        )
    print(f"wrote {output_dir}")
    print(f"{result.final_state.terminal_status} cost={result.final_state.canonical_state['project']['project_cost']} completion={result.final_state.canonical_state['project']['completion_tick']}")


def _single_llm_policy(provider: str, model: str, agent_id: str) -> LLMPolicy:
    if provider == "anthropic":
        return LLMPolicy(
            AnthropicModelAdapter(model=model),
            agent_id,
            prompt_style="anthropic_structured",
        )
    assert_ollama_model_available(model)
    return LLMPolicy(
        OllamaModelAdapter(model, json_format=False),
        agent_id,
        prompt_style="gemma_compact",
    )


if __name__ == "__main__":
    main()
