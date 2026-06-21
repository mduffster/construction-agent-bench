from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

from constructbench.models import DEFAULT_OLLAMA_MODEL, make_ollama_policies
from constructbench.runner import _apply_event_phase, _build_observation, _validate_submission
from constructbench.scenarios import get_scenario
from constructbench.state import default_behavior_profiles

SMOKES = {
    "S01_supplier_action": ("S01", "normal", "supplier_source_and_commercial", "steel_supplier"),
    "S02_gc_recovery": ("S02", "normal", "gc_recovery_plan", "gc"),
    "S04_gc_correction": ("S04", "normal", "gc_initial_corrective_strategy", "gc"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run isolated live-agent action smokes.")
    parser.add_argument("--case", choices=sorted(SMOKES), action="append")
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--randomize-option-order", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--debug-model-io", action="store_true")
    parser.add_argument(
        "--behavior-profile",
        choices=["collaborative", "selfish", "passive"],
        default="collaborative",
    )
    args = parser.parse_args()

    cases = args.case or list(SMOKES)
    policies = make_ollama_policies(args.model)
    behavior_profiles = default_behavior_profiles(args.behavior_profile)
    rng = random.Random(args.seed)
    output_dir = args.output_dir or Path("outputs") / f"smoke_ollama_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    model_io_records = []
    failed = False
    for case in cases:
        scenario_key, variant, phase_id, agent_id = SMOKES[case]
        scenario = get_scenario(scenario_key)
        state = scenario.create_state(
            run_id=f"smoke_{case}",
            variant=variant,  # type: ignore[arg-type]
            model_settings={
                "policy": "llm_smoke",
                "model": args.model,
                "behavior_profile": args.behavior_profile,
            },
            behavior_profile_by_agent=behavior_profiles,
        )
        for policy_agent_id, policy in policies.items():
            if hasattr(policy, "initialize"):
                policy.initialize(state.briefings_by_agent[policy_agent_id])  # type: ignore[attr-defined]
        events = []
        while True:
            phase = scenario.next_phase(state)
            if phase is None:
                raise SystemExit(f"{case}: target phase {phase_id} was not reached")
            state.phase_index += 1
            if phase.phase_type == "event_phase":
                _apply_event_phase(state, events, phase)
                continue
            if phase.phase_id != phase_id:
                raise SystemExit(f"{case}: reached {phase.phase_id}, expected {phase_id}")
            turn = next(turn for turn in phase.turns if turn.agent_id == agent_id)
            observation = _build_observation(state, phase, turn)
            if args.randomize_option_order:
                observation = observation.model_copy(deep=True)
                for request in observation.required_decisions:
                    rng.shuffle(request.options)
            policy = policies[agent_id]
            submission = policy.decide(observation)
            if args.debug_model_io and hasattr(policy, "drain_model_io"):
                model_io_records.extend(policy.drain_model_io())  # type: ignore[attr-defined]
            errors = _validate_submission(observation, submission)
            if errors and hasattr(policy, "repair"):
                submission = policy.repair(observation, errors)  # type: ignore[attr-defined]
                if args.debug_model_io and hasattr(policy, "drain_model_io"):
                    model_io_records.extend(policy.drain_model_io())  # type: ignore[attr-defined]
                errors = _validate_submission(observation, submission)
            option_order_by_node = {
                request.node_id: [option.option_id for option in request.options]
                for request in observation.required_decisions
            }
            record = {
                "case": case,
                "scenario": scenario_key,
                "variant": variant,
                "phase_id": phase_id,
                "agent_id": agent_id,
                "randomized_option_order": args.randomize_option_order,
                "option_order_by_node": option_order_by_node,
                "valid": not errors,
                "errors": errors,
                "submission": submission.model_dump(mode="json"),
            }
            results.append(record)
            if errors:
                failed = True
                print(f"{case}: INVALID {errors}")
            else:
                decisions = [
                    f"{decision.node_id}={decision.option_id or '__parameters__'}"
                    for decision in submission.decisions
                ]
                print(f"{case}: VALID order={option_order_by_node} decisions={decisions}")
            break
    with (output_dir / "smoke_results.jsonl").open("w") as handle:
        for record in results:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    if model_io_records:
        with (output_dir / "raw_model_io.jsonl").open("w") as handle:
            for record in model_io_records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"wrote {output_dir}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
