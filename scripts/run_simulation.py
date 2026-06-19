"""Run ConstructBench scenario artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from constructbench.runs import run_batch, run_single

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-mode", choices=["scripted", "ollama"], default="scripted")
    parser.add_argument("--model-id", default="scripted")
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--oversight-condition", default="normal_operations")
    parser.add_argument("--breach-profile", choices=["easy", "hard"], default="easy")
    parser.add_argument("--max-tick", type=int, default=None)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    parser.add_argument(
        "--scenario-config",
        default=str(ROOT / "configs" / "scenarios" / "steel_shock.yaml"),
    )
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--seeds", default="7")
    parser.add_argument("--oversight-conditions", default="normal_operations")
    parser.add_argument("--condition-level", choices=["comfortable", "normal", "strained"])
    parser.add_argument("--behavior-profile", choices=["collaborative", "selfish", "passive"])
    args = parser.parse_args()

    if args.batch:
        outputs = run_batch(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=args.scenario_config,
            output_root=args.output_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            seeds=[int(seed) for seed in args.seeds.split(",")],
            oversight_conditions=args.oversight_conditions.split(","),
            max_tick=args.max_tick,
            breach_profile=args.breach_profile,
            condition_overrides=_all_agent_overrides(args.condition_level),
            behavior_overrides=_all_agent_overrides(args.behavior_profile),
        )
        for output in outputs:
            print(output)
        return

    output = run_single(
        project_config_path=ROOT / "configs" / "project_baseline.yaml",
        agent_config_dir=ROOT / "configs" / "agents",
        scenario_config_path=args.scenario_config,
        output_root=args.output_root,
        policy_mode=args.policy_mode,
        model_id=args.model_id,
        random_seed=args.random_seed,
        oversight_condition=args.oversight_condition,
        breach_profile=args.breach_profile,
        condition_overrides=_all_agent_overrides(args.condition_level),
        behavior_overrides=_all_agent_overrides(args.behavior_profile),
        max_tick=args.max_tick,
    )
    print(output)


def _all_agent_overrides(value: str | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "owner_developer": value,
        "general_contractor": value,
        "steel_supplier": value,
        "labor_subcontractor": value,
        "lender": value,
        "inspector": value,
    }


if __name__ == "__main__":
    main()
