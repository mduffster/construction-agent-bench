"""Re-evaluate frozen packet-study submissions after the supplier-payoff fix.

This is a zero-model-call post hoc accounting replay. It preserves the original
archival runs, reloads their exact agent submissions, and writes separate normal
four-file runs plus a comparison record. Ordinary event replay is intentionally
not used because old events contain the already-computed payoff snapshots.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from constructbench.agents import ReplayPolicy, replay_submissions_for_agent
from constructbench.manifest import sha256_file
from constructbench.replay import replay_run
from constructbench.runner import run_policy
from constructbench.s01_v2_derived_state_packet import (
    DERIVED_STATE_PACKET_EXPERIMENT_ID,
    TREATMENT_CONDITION,
    DerivedStatePacketPolicy,
    aggregate_study_rows,
    study_run_row,
)
from constructbench.state import AGENT_IDS

EXPECTED_RUN_FILES = {
    "run_config.json",
    "events.jsonl",
    "turn_summaries.jsonl",
    "run_summary.json",
}
ACCOUNTING_CHANGE_ID = "s01_v2_supplier_recovery_spend_counted_once_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study_dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    study_dir = args.study_dir
    output_dir = args.output_dir or study_dir / "posthoc_supplier_payoff_accounting_replay"
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"accounting replay output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = _read_jsonl(study_dir / "study_rows.jsonl")
    if len(source_rows) != 6:
        raise RuntimeError("accounting replay requires the complete six-run source study")
    source_by_sequence = {int(row["sequence_index"]): row for row in source_rows}

    replay_rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    for source_run_dir in sorted((study_dir / "runs").iterdir()):
        if not source_run_dir.is_dir():
            continue
        source_config = _read_json(source_run_dir / "run_config.json")
        source_summary = _read_json(source_run_dir / "run_summary.json")
        settings = source_config.get("model_settings", {})
        if settings.get("experiment_id") != DERIVED_STATE_PACKET_EXPERIMENT_ID:
            raise RuntimeError(f"unexpected source experiment in {source_run_dir}")
        sequence_index = int(settings["sequence_index"])
        replicate_index = int(settings["replicate_index"])
        condition = str(settings["experiment_condition"])
        source_state = replay_run(source_run_dir)
        policies = {
            agent_id: ReplayPolicy(
                replay_submissions_for_agent(source_state, agent_id)
            )
            for agent_id in AGENT_IDS
        }
        if condition == TREATMENT_CONDITION:
            for agent_id in ("steel_supplier", "gc"):
                policies[agent_id] = DerivedStatePacketPolicy(policies[agent_id])

        replay_run_dir = output_dir / "runs" / source_run_dir.name
        replay_result = run_policy(
            "S01_V2",
            "normal",
            policies,
            output_dir=replay_run_dir,
            seed=int(source_config["seed"]),
            repair_budget=1,
            model_settings={
                "policy": "s01_v2_archived_submission_accounting_replay",
                "accounting_change_id": ACCOUNTING_CHANGE_ID,
                "source_experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
                "source_run_id": source_summary["run_id"],
                "source_code_commit": source_summary["run_manifest"]["code"][
                    "git_commit"
                ],
                "experiment_condition": condition,
                "replicate_index": replicate_index,
                "sequence_index": sequence_index,
                "provider": "replay",
                "model": "archived_submissions",
            },
        )
        replay_summary = _read_json(replay_run_dir / "run_summary.json")
        actual_files = {
            path.name for path in replay_run_dir.iterdir() if path.is_file()
        }
        if actual_files != EXPECTED_RUN_FILES:
            raise RuntimeError(f"replay output contract mismatch: {replay_run_dir}")
        if replay_result.final_state.histories.get("model_io"):
            raise RuntimeError(f"accounting replay made a model call: {replay_run_dir}")
        if replay_summary["decision_history"] != source_summary["decision_history"]:
            raise RuntimeError(f"decision mismatch in accounting replay: {replay_run_dir}")
        if (
            replay_summary["final_project_cost"] != source_summary["final_project_cost"]
            or replay_summary["completion_tick"] != source_summary["completion_tick"]
        ):
            raise RuntimeError(f"project outcome changed in accounting replay: {replay_run_dir}")

        replay_row = study_run_row(
            condition=condition,
            replicate_index=replicate_index,
            sequence_index=sequence_index,
            summary=replay_summary,
        )
        # Model usage belongs to the archived source run, not the zero-call replay.
        replay_row["source_model_cost_usd"] = source_by_sequence[sequence_index][
            "model_cost_usd"
        ]
        replay_rows.append(replay_row)
        comparisons.append(
            _comparison(
                source_run_dir=source_run_dir,
                source_summary=source_summary,
                source_row=source_by_sequence[sequence_index],
                replay_summary=replay_summary,
                replay_row=replay_row,
            )
        )

    replay_rows.sort(key=lambda row: int(row["sequence_index"]))
    comparisons.sort(key=lambda row: int(row["sequence_index"]))
    aggregate = aggregate_study_rows(replay_rows)
    _write_jsonl(output_dir / "accounting_replay_rows.jsonl", replay_rows)
    _write_json(
        output_dir / "accounting_replay_analysis.json",
        {
            "schema_version": "constructbench.s01_v2_packet_accounting_replay.v1",
            "accounting_change_id": ACCOUNTING_CHANGE_ID,
            "source_experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
            "source_study_dir": str(study_dir),
            "source_code_commit": comparisons[0]["source_code_commit"],
            "replay_code_commit": _current_commit(),
            "model_call_count": 0,
            "source_model_cost_usd": round(
                sum(float(row["model_cost_usd"]) for row in source_rows), 6
            ),
            "replay_model_cost_usd": 0.0,
            "all_decisions_identical": all(
                row["decisions_identical"] for row in comparisons
            ),
            "all_project_outcomes_identical": all(
                row["project_outcome_identical"] for row in comparisons
            ),
            "comparisons": comparisons,
            "aggregate": aggregate,
        },
    )
    print(
        f"wrote {output_dir}; replayed={len(replay_rows)} model_calls=0 "
        f"advance={aggregate['advance_to_broader_confirmation']}"
    )


def _comparison(
    *,
    source_run_dir: Path,
    source_summary: dict[str, Any],
    source_row: dict[str, Any],
    replay_summary: dict[str, Any],
    replay_row: dict[str, Any],
) -> dict[str, Any]:
    source_supplier = source_summary["organization_ledger"]["steel_supplier"]
    replay_supplier = replay_summary["organization_ledger"]["steel_supplier"]
    return {
        "sequence_index": replay_row["sequence_index"],
        "condition": replay_row["condition"],
        "replicate_index": replay_row["replicate_index"],
        "source_run_id": source_summary["run_id"],
        "source_code_commit": source_summary["run_manifest"]["code"]["git_commit"],
        "source_run_config_sha256": sha256_file(source_run_dir / "run_config.json"),
        "source_events_sha256": sha256_file(source_run_dir / "events.jsonl"),
        "source_run_summary_sha256": sha256_file(source_run_dir / "run_summary.json"),
        "decisions_identical": (
            source_summary["decision_history"] == replay_summary["decision_history"]
        ),
        "project_outcome_identical": (
            source_summary["final_project_cost"]
            == replay_summary["final_project_cost"]
            and source_summary["completion_tick"] == replay_summary["completion_tick"]
        ),
        "source_supplier_payoff_usd": source_supplier["realized_payoff_usd"],
        "replay_supplier_payoff_usd": replay_supplier["realized_payoff_usd"],
        "payoff_change_usd": (
            replay_supplier["realized_payoff_usd"]
            - source_supplier["realized_payoff_usd"]
        ),
        "source_coalition_success": source_row["coalition_success"],
        "replay_coalition_success": replay_row["coalition_success"],
        "source_joint_efficient_outcome": source_row["joint_efficient_outcome"],
        "replay_joint_efficient_outcome": replay_row["joint_efficient_outcome"],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _current_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


if __name__ == "__main__":
    main()
