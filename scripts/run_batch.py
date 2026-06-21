from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.models import (
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
    DEFAULT_OLLAMA_MODEL,
    make_anthropic_policies,
    make_ollama_policies,
)
from constructbench.reporting import model_usage_summary
from constructbench.runner import run_fixture, run_policy
from constructbench.scenarios import SCENARIOS
from constructbench.state import RunState, default_behavior_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ConstructBench scenario batch.")
    parser.add_argument("--policy", choices=["fixture", "llm"], default="fixture")
    parser.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--behavior-profile",
        choices=["collaborative", "selfish", "passive"],
        default="collaborative",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-batch", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"batch_{args.policy}_{stamp}"
    model = args.model or (
        DEFAULT_ANTHROPIC_HAIKU_MODEL
        if args.provider == "anthropic"
        else DEFAULT_OLLAMA_MODEL
    )
    behavior_profiles = default_behavior_profiles(args.behavior_profile)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.policy == "fixture":
        for scenario in sorted(SCENARIOS):
            for fixture_name in SCENARIOS[scenario].fixtures:
                result = run_fixture(
                    scenario,
                    fixture_name,
                    output_dir=root / f"{scenario}_{fixture_name}",
                    behavior_profile_by_agent=behavior_profiles,
                )
                rows.append(_row(scenario, fixture_name, result.final_state))
    else:
        if not args.allow_live_batch:
            raise SystemExit("live LLM batch requires --allow-live-batch after smoke tests pass")
        for scenario in ["S01", "S02", "S03", "S04", "S05"]:
            for variant in ["normal", "stressed"]:
                if args.provider == "anthropic":
                    policies = make_anthropic_policies(model)
                else:
                    policies = make_ollama_policies(model)
                result = run_policy(
                    scenario,
                    variant,
                    policies,
                    output_dir=root / f"{scenario}_{variant}_llm",
                    model_settings={
                        "policy": "llm",
                        "provider": args.provider,
                        "model": model,
                        "behavior_profile": args.behavior_profile,
                    },
                    behavior_profile_by_agent=behavior_profiles,
                )
                rows.append(_row(scenario, variant, result.final_state))
    with (root / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "case",
                "run_valid",
                "status",
                "final_project_cost",
                "completion_tick",
                "model_call_count",
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "model_cost_usd",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    (root / "batch_summary.json").write_text(
        json.dumps(
            {
                "run_count": len(rows),
                "valid_run_count": sum(1 for row in rows if row["run_valid"]),
                "model_usage_total": _aggregate_usage(rows),
                "runs": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"wrote {root}")


def _row(scenario: str, case: str, state: RunState) -> dict[str, Any]:
    usage = model_usage_summary(state)["total"]
    return {
        "scenario": scenario,
        "case": case,
        "run_valid": state.run_valid,
        "status": state.terminal_status,
        "final_project_cost": state.canonical_state["project"]["project_cost"],
        "completion_tick": state.canonical_state["project"]["completion_tick"],
        "model_call_count": usage["call_count"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
        "model_cost_usd": usage["cost_usd"],
    }


def _aggregate_usage(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    total = {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
    }
    for row in rows:
        total["call_count"] += int(row["model_call_count"])
        total["input_tokens"] += int(row["input_tokens"])
        total["output_tokens"] += int(row["output_tokens"])
        total["cache_creation_input_tokens"] += int(row["cache_creation_input_tokens"])
        total["cache_read_input_tokens"] += int(row["cache_read_input_tokens"])
        total["cost_usd"] += float(row["model_cost_usd"])
    total["cost_usd"] = round(float(total["cost_usd"]), 6)
    return total


if __name__ == "__main__":
    main()
