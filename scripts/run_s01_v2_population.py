"""Run a population batch of S01 V2 with all six organizations as live agents.

Each run puts one LLM behind every organization for the full 18-decision
scenario. Sampling temperature above zero produces trajectory variety across
replicates; temperature zero gives the modal path. Requires the explicit
--allow-live-batch opt-in like the other live batch entry points.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from constructbench.models import DEFAULT_ANTHROPIC_HAIKU_MODEL, make_anthropic_policies
from constructbench.reporting import model_usage_summary, repair_summary
from constructbench.runner import run_policy
from constructbench.state import RunState


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--model", default=DEFAULT_ANTHROPIC_HAIKU_MODEL)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--variant", choices=["normal", "stressed"], default="normal")
    parser.add_argument(
        "--repair-budget",
        type=int,
        default=1,
        help="validation-failure retries per turn; each retry re-prompts with the errors",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-live-batch", action="store_true")
    args = parser.parse_args()

    if not args.allow_live_batch:
        raise SystemExit("live population batch requires --allow-live-batch")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = args.output_dir or Path("outputs") / f"s01_v2_population_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for index in range(args.runs):
        policies = make_anthropic_policies(args.model, temperature=args.temperature)
        result = run_policy(
            "S01_V2",
            args.variant,
            policies,
            output_dir=root / f"run_{index:02d}",
            seed=index,
            repair_budget=args.repair_budget,
            model_settings={
                "policy": "llm_population",
                "provider": "anthropic",
                "model": args.model,
                "temperature": args.temperature,
                "repair_budget": args.repair_budget,
                "replicate_index": index,
            },
        )
        rows.append(_row(index, result.final_state))
        latest = rows[-1]
        print(
            f"run_{index:02d}: valid={latest['run_valid']} status={latest['terminal_status']} "
            f"path={latest['path_label']} repairs={latest['repair_attempt_count']} "
            f"cost=${latest['model_cost_usd']:.3f}"
        )

    (root / "population_summary.json").write_text(
        json.dumps(
            {
                "run_count": len(rows),
                "valid_run_count": sum(1 for row in rows if row["run_valid"]),
                "model": args.model,
                "temperature": args.temperature,
                "repair_budget": args.repair_budget,
                "total_model_cost_usd": round(
                    sum(row["model_cost_usd"] for row in rows), 6
                ),
                "runs": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"wrote {root}")


def _row(index: int, state: RunState) -> dict[str, Any]:
    project = state.canonical_state["project"]
    organizations = state.canonical_state.get("organizations", {})
    usage = model_usage_summary(state)["total"]
    repairs = repair_summary(state)
    return {
        "replicate_index": index,
        "run_valid": state.run_valid,
        "terminal_status": state.terminal_status,
        "terminal_reason": state.terminal_reason,
        "path_label": project.get("s01_v2_path_label"),
        "final_project_cost": project.get("project_cost"),
        "completion_tick": project.get("completion_tick"),
        "project_success": project.get("s01_v2_project_success"),
        "coalition_success": project.get("s01_v2_coalition_success"),
        "private_success_by_organization": {
            org: record.get("private_success") for org, record in organizations.items()
        },
        "realized_payoff_by_organization": {
            org: record.get("realized_payoff_usd") for org, record in organizations.items()
        },
        "model_call_count": usage["call_count"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "model_cost_usd": float(usage["cost_usd"]),
        "repair_attempt_count": repairs["attempt_count"],
        "repaired_turn_count": repairs["repaired_turn_count"],
        "unrepaired_turn_count": repairs["unrepaired_turn_count"],
    }


if __name__ == "__main__":
    main()
