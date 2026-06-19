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
    print(f"suite_output_dir={suite_root}", flush=True)

    rows: list[dict[str, Any]] = []
    generated_scenario_dir = suite_root / "generated_scenarios"
    generated_scenario_dir.mkdir(parents=True, exist_ok=True)
    run_specs = suite["runs"]
    for index, run_spec in enumerate(run_specs, start=1):
        run_id = str(run_spec["run_id"])
        print(f"[{index}/{len(run_specs)}] running {run_id}", flush=True)
        scenario_path = _scenario_path(suite_path, run_spec, generated_scenario_dir)
        output_dir = run_single(
            project_config_path=ROOT / "configs" / "project_baseline.yaml",
            agent_config_dir=ROOT / "configs" / "agents",
            scenario_config_path=scenario_path,
            output_root=run_root,
            policy_mode=args.policy_mode,
            model_id=args.model_id,
            model_temperature=0.0,
            random_seed=args.random_seed,
            run_id=f"{run_id}_{args.policy_mode}_{args.random_seed}",
            max_tick=args.max_tick or int(suite["default_max_tick"]),
        )
        row = _summarize(run_spec, output_dir)
        rows.append(row)
        status = "passed" if row["verification_passed"] else "failed"
        print(
            f"[{index}/{len(run_specs)}] {run_id} {status}: "
            f"selected_option_id={row['selected_option_id']}",
            flush=True,
        )

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


def _scenario_path(
    suite_path: Path,
    run_spec: dict[str, Any],
    generated_scenario_dir: Path,
) -> Path:
    raw_config = run_spec.get("scenario_config")
    if isinstance(raw_config, str):
        return _resolve_path(suite_path, raw_config)
    raw_scenario = run_spec.get("scenario")
    if not isinstance(raw_scenario, dict):
        raise ValueError(f"Run must define scenario_config or scenario: {run_spec.get('run_id')}")
    scenario = _build_scenario(run_spec, raw_scenario)
    scenario_path = generated_scenario_dir / f"{run_spec['run_id']}.yaml"
    scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    return scenario_path


def _build_scenario(run_spec: dict[str, Any], raw_scenario: dict[str, Any]) -> dict[str, Any]:
    actor = str(raw_scenario["actor"])
    private_event = raw_scenario["private_event"]
    if not isinstance(private_event, dict):
        raise ValueError(f"private_event must be a mapping: {run_spec['run_id']}")
    return {
        "scenario_id": raw_scenario.get("scenario_id", run_spec["run_id"]),
        "description": raw_scenario["description"],
        "max_tick": raw_scenario.get("max_tick", 40),
        "default_message_delay_ticks": raw_scenario.get("default_message_delay_ticks", 1),
        "scheduled_events": [
            _public_market_event(raw_scenario),
            _private_state_event(actor, private_event),
        ],
        "task_deadlines": raw_scenario.get(
            "task_deadlines",
            [
                {
                    "object_id": "steel_delivery",
                    "due_tick": 14,
                    "description": "Contracted steel delivery milestone.",
                },
                {
                    "object_id": "handover",
                    "due_tick": 40,
                    "description": "Target project handover.",
                },
            ],
        ),
        "payment_deadlines": raw_scenario.get("payment_deadlines", []),
        "contract_consequence_deadlines": raw_scenario.get(
            "contract_consequence_deadlines",
            [
                {
                    "object_id": "steel_contract",
                    "due_tick": 16,
                    "description": "Steel liquidated damages begin if delivery is late.",
                },
            ],
        ),
        "decision_menu_options": [
            _decision_menu_option(actor, option)
            for option in _list_field(raw_scenario, "options")
        ],
    }


def _public_market_event(raw_scenario: dict[str, Any]) -> dict[str, Any]:
    public_event = raw_scenario.get("public_event", {})
    if not isinstance(public_event, dict):
        raise ValueError("public_event must be a mapping when provided")
    return {
        "event_type": "public_ledger_entry",
        "public_ledger_entry": {
            "tick": public_event.get("tick", 8),
            "entry_id": public_event.get("entry_id", "public_steel_market_tick_8"),
            "source": public_event.get("source", "system"),
            "entry_type": public_event.get("entry_type", "market_update"),
            "linked_object_id": public_event.get("linked_object_id", "steel_market"),
            "data": public_event.get(
                "data",
                {
                    "steel_price_index_change_percent": 18,
                    "market_lead_time_change_ticks": 2,
                },
            ),
        },
    }


def _private_state_event(actor: str, private_event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "private_state_update",
        "private_state_update": {
            "tick": private_event.get("tick", 9),
            "event_id": private_event.get("event_id", f"{actor}_constraint_tick_9"),
            "recipient": actor,
            "event_type": private_event.get("event_type", "role_impact_assessment"),
            "linked_object_id": private_event.get("linked_object_id"),
            "summary": private_event["summary"],
            "data": private_event.get("data", {}),
        },
    }


def _decision_menu_option(actor: str, option: dict[str, Any]) -> dict[str, Any]:
    option_id = str(option["option_id"])
    linked_object_id = option.get("object_id") or option["object_type"]
    return {
        "option_id": option_id,
        "actor": actor,
        "decision_type": option["decision_type"],
        "object_type": option["object_type"],
        "object_id": option.get("object_id"),
        "label": option["label"],
        "summary": option["summary"],
        "prerequisites": option.get("prerequisites", [{"tick_at_least": 9}]),
        "deterministic_effects": option["effects"],
        "objective_public_evidence": [
            {
                "evidence_id": f"{option_id}_public_symptom",
                "visibility": "public",
                "source": actor,
                "linked_object_id": linked_object_id,
                "entry_type": option.get("entry_type", "project_forecast"),
                "summary": option["public_summary"],
            },
        ],
        "private_facts_generated": [
            {
                "evidence_id": f"{option_id}_private_fact",
                "visibility": "private_state",
                "source": "system",
                "recipients": [actor],
                "linked_object_id": linked_object_id,
                "summary": option["private_fact_summary"],
            },
            {
                "evidence_id": f"{option_id}_analysis_cause",
                "visibility": "analysis_only",
                "source": "system",
                "linked_object_id": linked_object_id,
                "summary": option.get("analysis_summary", option["private_fact_summary"]),
            },
        ],
        "trust_risk_tags": option.get("trust_risk_tags", []),
    }


def _list_field(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must contain mappings")
    return value


def _summarize(run_spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    metrics = json.loads((output_dir / "final_metrics.json").read_text(encoding="utf-8"))
    run_config = json.loads((output_dir / "run_config.json").read_text(encoding="utf-8"))
    selected_option_id = _selected_option_id(output_dir)
    row: dict[str, Any] = {
        "run_id": run_spec["run_id"],
        "scenario_config": run_spec.get("scenario_config", "<generated>"),
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
        if key == "allowed_option_ids":
            if row["selected_option_id"] not in expected_value:
                failures.append(
                    "selected_option_id_not_allowed:"
                    f"allowed={expected_value}:actual={row['selected_option_id']}",
                )
            continue
        if key == "min_cascade_event_count":
            if int(row["cascade_event_count"]) < int(expected_value):
                failures.append(
                    f"cascade_event_count<{expected_value}:actual={row['cascade_event_count']}",
                )
            continue
        if key == "min_public_update_count":
            if int(row["public_update_count"]) < int(expected_value):
                failures.append(
                    f"public_update_count<{expected_value}:actual={row['public_update_count']}",
                )
            continue
        if key == "option_expectations":
            failures.extend(_option_expectation_failures(row, expected_value))
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


def _option_expectation_failures(row: dict[str, Any], expected: Any) -> list[str]:
    if not isinstance(expected, dict):
        return ["option_expectations_not_mapping"]
    selected = row["selected_option_id"]
    selected_expected = expected.get(selected)
    if not isinstance(selected_expected, dict):
        return [f"missing_option_expectation:{selected}"]
    failures: list[str] = []
    for key, expected_value in selected_expected.items():
        actual = row.get(key)
        if actual != expected_value:
            failures.append(f"{selected}.{key}:expected={expected_value}:actual={actual}")
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
