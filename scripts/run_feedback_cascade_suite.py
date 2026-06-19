"""Run the current feedback-cascade agent suite from its manifest."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from constructbench.runs import run_single

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "configs" / "suites" / "feedback_cascade_suite.yaml"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-config", default=str(DEFAULT_SUITE))
    parser.add_argument("--policy-mode", choices=["ollama", "scripted"], default="ollama")
    parser.add_argument("--model-id", default="gemma4:e2b")
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--max-tick", type=int)
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    args = parser.parse_args()

    suite_path = Path(args.suite_config)
    suite = _read_suite(suite_path)
    suite_id = str(suite["suite_id"])
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suite_root = Path(args.output_root) / f"{suite_id}_{args.policy_mode}_{timestamp}"
    run_root = suite_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for run_spec in suite["runs"]:
        run_id = str(run_spec["run_id"])
        scenario_path = _resolve_path(suite_path, str(run_spec["scenario_config"]))
        output_dir = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=scenario_path,
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            random_seed=args.random_seed,
            run_id=f"{run_id}_{args.policy_mode}_{args.random_seed}",
            max_tick=args.max_tick or int(suite["default_max_tick"]),
        )
        rows.append(_summarize(run_spec, output_dir))

    _write_outputs(suite_root, suite, rows)
    print(suite_root)
    if any(not row["verification_passed"] for row in rows):
        raise SystemExit(1)


def _read_suite(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Suite config must be a mapping: {path}")
    runs = data.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"Suite config must define non-empty runs: {path}")
    return data


def _resolve_path(suite_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    root_relative = ROOT / path
    if root_relative.exists():
        return root_relative
    return suite_path.parent / path


def _summarize(run_spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    metrics = json.loads((output_dir / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output_dir / "run_config.json").read_text(encoding="utf-8"))
    selected_option_id = _selected_option_id(output_dir)
    row: dict[str, Any] = {
        "run_id": run_spec["run_id"],
        "scenario_config": run_spec["scenario_config"],
        "output_dir": str(output_dir),
        "selected_option_id": selected_option_id,
        "final_termination_reason": run_config["final_termination_reason"],
        "validation_failure_count": len(run_config["validation_failures"]),
        "fallback_action_count": len(run_config["fallback_actions"]),
        "transition_rejection_count": len(run_config["transition_rejections"]),
        "final_completion_tick": metrics["project"]["final_completion_tick"],
        "final_cost": metrics["project"]["final_cost"],
        "delay_ticks": metrics["project"]["delay_ticks"],
        "project_failed": metrics["project"]["project_failed"],
        "project_cancelled": metrics["project"]["project_cancelled"],
        "cascade_event_count": metrics["cascade"]["cascade_event_count"],
        "causal_trace_count": metrics["cascade"]["causal_trace_count"],
        "private_cause_count": metrics["cascade"]["private_cause_count"],
        "public_symptom_count": metrics["cascade"]["public_symptom_count"],
        "viability_gate_count": metrics["viability"]["viability_gate_count"],
        "public_update_count": metrics["information"]["public_update_count"],
        "private_message_count": metrics["information"]["private_message_count"],
    }
    failures = _verification_failures(row, run_spec.get("expected", {}))
    row["verification_passed"] = not failures
    row["verification_failures"] = failures
    return row


def _selected_option_id(output_dir: Path) -> str | None:
    path = output_dir / "agent_submissions.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        params = record["submission"]["decision"].get("parameters", {})
        option_id = params.get("option_id")
        if isinstance(option_id, str):
            return option_id
    return None


def _verification_failures(row: dict[str, Any], expected: Any) -> list[str]:
    if not isinstance(expected, dict):
        return ["expected_not_mapping"]
    failures: list[str] = []
    for key, expected_value in expected.items():
        if key == "min_public_update_count":
            if int(row["public_update_count"]) < int(expected_value):
                failures.append(
                    f"public_update_count<{expected_value}:actual={row['public_update_count']}",
                )
            continue
        actual = row.get(key)
        if actual != expected_value:
            failures.append(f"{key}:expected={expected_value}:actual={actual}")
    if row["validation_failure_count"] != 0:
        failures.append(f"validation_failure_count:actual={row['validation_failure_count']}")
    if row["fallback_action_count"] != 0:
        failures.append(f"fallback_action_count:actual={row['fallback_action_count']}")
    if row["transition_rejection_count"] != 0:
        failures.append(f"transition_rejection_count:actual={row['transition_rejection_count']}")
    return failures


def _write_outputs(
    suite_root: Path,
    suite: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    suite_root.mkdir(parents=True, exist_ok=True)
    (suite_root / "suite_config.json").write_text(
        json.dumps(suite, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (suite_root / "suite_summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (suite_root / "suite_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
