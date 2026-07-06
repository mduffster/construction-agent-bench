"""Export S01 V2 population-batch outcomes for the public results page.

Reads population_summary.json files produced by run_s01_v2_population.py and
writes a compact JSON the web app imports statically. Every number on the
results page comes from run records; nothing is hand-typed.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

POPULATION_EXPORT_SCHEMA_VERSION = "constructbench.web_population.s01_v2.v1"
DEFAULT_OUTPUT = Path("web/src/game-data/s01_v2_population.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "batches",
        nargs="+",
        type=Path,
        help="Population batch directories containing population_summary.json.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    runs: list[dict[str, Any]] = []
    models: set[str] = set()
    for batch_dir in args.batches:
        summary = json.loads((batch_dir / "population_summary.json").read_text())
        models.add(str(summary.get("model")))
        temperature = summary.get("temperature")
        for row in summary.get("runs", []):
            runs.append(
                {
                    "batch": batch_dir.name,
                    "temperature": temperature,
                    "replicate_index": row.get("replicate_index"),
                    "run_valid": row.get("run_valid"),
                    "terminal_status": row.get("terminal_status"),
                    "path_label": row.get("path_label"),
                    "final_project_cost": row.get("final_project_cost"),
                    "completion_tick": row.get("completion_tick"),
                    "project_success": row.get("project_success"),
                    "coalition_success": row.get("coalition_success"),
                    "firms_meeting_private_target": _firm_target_count(row),
                    "private_success_by_organization": row.get(
                        "private_success_by_organization", {}
                    ),
                }
            )

    valid_runs = [run for run in runs if run["run_valid"]]
    successes = [run for run in valid_runs if run["project_success"]]
    costs = [run["final_project_cost"] for run in valid_runs if run["final_project_cost"]]
    ticks = [run["completion_tick"] for run in valid_runs if run["completion_tick"]]
    payload = {
        "schema_version": POPULATION_EXPORT_SCHEMA_VERSION,
        "generated_at": date.today().isoformat(),
        "model": sorted(models)[0] if len(models) == 1 else sorted(models),
        "run_count": len(runs),
        "valid_run_count": len(valid_runs),
        "project_success_count": len(successes),
        "coalition_success_count": sum(
            1 for run in valid_runs if run["coalition_success"]
        ),
        "cost_min": min(costs) if costs else None,
        "cost_max": max(costs) if costs else None,
        "tick_min": min(ticks) if ticks else None,
        "tick_max": max(ticks) if ticks else None,
        "runs": sorted(
            runs,
            key=lambda run: (str(run["batch"]), int(run["replicate_index"] or 0)),
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")
    print(
        f"runs={payload['run_count']} valid={payload['valid_run_count']} "
        f"project_success={payload['project_success_count']}"
    )


def _firm_target_count(row: dict[str, Any]) -> int | None:
    private = row.get("private_success_by_organization") or {}
    if not private:
        return None
    return sum(1 for met in private.values() if met)


if __name__ == "__main__":
    main()
