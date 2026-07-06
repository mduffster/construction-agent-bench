from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constructbench.manifest import build_run_manifest, output_hashes
from constructbench.state import Event, RunState, TrustAssessment


def run_config_payload(
    initial_state: RunState,
    final_state: RunState,
    *,
    debug_model_io: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": initial_state.run_id,
        "scenario_id": initial_state.scenario_id,
        "variant": initial_state.variant,
        "seed": initial_state.seed,
        "model_settings": initial_state.model_settings,
        "behavior_profile_by_agent": initial_state.behavior_profile_by_agent,
        "goal_profile_by_agent": {
            agent_id: profile.model_dump(mode="json")
            for agent_id, profile in initial_state.goal_profile_by_agent.items()
        },
        "run_manifest": build_run_manifest(
            initial_state=initial_state,
            final_state=final_state,
            debug_model_io=debug_model_io,
        ),
        "initial_state": initial_state.model_dump(mode="json"),
    }


def run_summary_payload(
    final_state: RunState,
    *,
    initial_state: RunState | None = None,
    debug_model_io: bool = False,
    manifest_output_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    project = final_state.canonical_state["project"]
    initial_state = initial_state or final_state
    return {
        "run_id": final_state.run_id,
        "scenario_id": final_state.scenario_id,
        "variant": final_state.variant,
        "run_valid": final_state.run_valid,
        "terminal_status": final_state.terminal_status,
        "terminal_reason": final_state.terminal_reason,
        "final_project_cost": project["project_cost"],
        "completion_tick": project["completion_tick"],
        "scenario_metrics": {
            key: value
            for key, value in project.items()
            if key not in {"base_project_cost", "project_cost", "completion_tick", "cost_components"}
        },
        "organization_ledger": final_state.canonical_state.get("organizations", {}),
        "terminal_values": final_state.canonical_state.get("terminal_values", {}),
        "payoff_ledger": final_state.canonical_state.get("payoff_ledger", {}),
        "s01_v2_state": final_state.canonical_state.get("s01_v2_state", {}),
        "s01_v2_analysis": final_state.canonical_state.get("s01_v2_state", {}).get(
            "analysis",
            {},
        ),
        "s01_v2_claim_provenance_history": final_state.histories.get(
            "s01_v2_claim_provenance_history",
            [],
        ),
        "cost_components": project["cost_components"],
        "decision_history": final_state.histories.get("decision_history", []),
        "message_history": final_state.histories.get("message_history", []),
        "claim_evaluation_history": final_state.histories.get("claim_evaluation_history", []),
        "communication_abstention_history": final_state.histories.get(
            "communication_abstention_history",
            [],
        ),
        "assessment_history": final_state.histories.get("assessment_history", []),
        "assessment_review_history": final_state.histories.get("assessment_review_history", []),
        "agent_activation_history": final_state.histories.get("agent_activation_history", []),
        "validation_results": final_state.histories.get("validation_results", []),
        "invalid_outputs": final_state.histories.get("invalid_outputs", []),
        "model_usage_summary": model_usage_summary(final_state),
        "run_manifest": build_run_manifest(
            initial_state=initial_state,
            final_state=final_state,
            debug_model_io=debug_model_io,
            output_hashes=manifest_output_hashes,
        ),
        "final_trust_matrix": {
            assessor: {
                counterparty: assessment.model_dump(mode="json")
                for counterparty, assessment in row.items()
            }
            for assessor, row in final_state.trust_state.items()
        },
        "mean_pairwise_assessment": mean_pairwise_assessment(final_state.trust_state),
        "narrative": deterministic_narrative(final_state),
    }


def model_usage_summary(final_state: RunState) -> dict[str, Any]:
    records = final_state.histories.get("model_io", [])
    by_model: dict[str, dict[str, Any]] = {}
    totals: dict[str, Any] = {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
    }
    for record in records:
        model = record.get("model", "unknown")
        usage = record.get("usage") or {}
        row = by_model.setdefault(
            model,
            {
                "call_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        row["call_count"] += 1
        totals["call_count"] += 1
        for field in [
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ]:
            value = int(usage.get(field, 0) or 0)
            row[field] += value
            totals[field] += value
        cost = float(record.get("cost_usd") or 0.0)
        row["cost_usd"] += cost
        totals["cost_usd"] += cost
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    for row in by_model.values():
        row["cost_usd"] = round(row["cost_usd"], 6)
    return {"total": totals, "by_model": by_model}


def mean_pairwise_assessment(trust_state: dict[str, dict[str, TrustAssessment]]) -> float:
    values: list[float] = []
    for row in trust_state.values():
        for assessment in row.values():
            values.extend(
                [
                    assessment.performance_reliability,
                    assessment.information_reliability,
                    assessment.contractual_reliability,
                ]
            )
    return sum(values) / len(values) if values else 0.0


def deterministic_narrative(final_state: RunState) -> str:
    decisions = ", ".join(
        f"{record['actor_id']}:{record['node_id']}={record['option_id']}"
        for record in final_state.histories.get("decision_history", [])
    )
    project = final_state.canonical_state["project"]
    return (
        f"{final_state.scenario_id} {final_state.variant} ended as "
        f"{final_state.terminal_status} with cost {project['project_cost']} and "
        f"completion tick {project['completion_tick']}. Decisions: {decisions}."
    )


def write_run_outputs(
    output_dir: Path,
    initial_state: RunState,
    final_state: RunState,
    events: list[Event],
    turn_summaries: list[dict[str, Any]],
    *,
    debug_model_io: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    config_payload = run_config_payload(
        initial_state,
        final_state,
        debug_model_io=debug_model_io,
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n"
    )
    _write_jsonl(
        output_dir / "events.jsonl",
        [event.model_dump(mode="json") for event in events],
    )
    _write_jsonl(output_dir / "turn_summaries.jsonl", turn_summaries)
    summary_payload = run_summary_payload(
        final_state,
        initial_state=initial_state,
        debug_model_io=debug_model_io,
        manifest_output_hashes=output_hashes(output_dir),
    )
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n"
    )
    if debug_model_io:
        _write_debug_jsonl(output_dir / "raw_model_io.jsonl", final_state.histories.get("model_io", []))
        _write_debug_jsonl(
            output_dir / "parsed_submissions.jsonl",
            final_state.histories.get("agent_submission_history", []),
        )
        _write_debug_jsonl(
            output_dir / "repair_attempts.jsonl",
            final_state.histories.get("repair_attempts", []),
        )
        _write_debug_jsonl(
            output_dir / "validation_results.jsonl",
            final_state.histories.get("validation_results", []),
        )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_debug_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if records:
        _write_jsonl(path, records)
