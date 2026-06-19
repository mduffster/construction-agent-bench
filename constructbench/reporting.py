"""Run artifact writing, turn summaries, and analysis packet assembly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constructbench.io import append_jsonl
from constructbench.metrics import calculate_final_metrics
from constructbench.models import (
    AgentTurnResult,
    SafetyTickResult,
    ScenarioConfig,
    StateStore,
    TickResult,
    TransitionResult,
)
from constructbench.state import export_state_snapshot


class RunLogger:
    """Write Phase 5 JSON and JSONL artifacts for a run."""

    JSONL_ARTIFACTS = (
        "state_snapshots.jsonl",
        "public_ledger.jsonl",
        "private_messages.jsonl",
        "agent_observations.jsonl",
        "agent_submissions.jsonl",
        "agent_beliefs.jsonl",
        "agent_decision_reports.jsonl",
        "contract_breaches.jsonl",
        "oversight_findings.jsonl",
        "trust_updates.jsonl",
        "agent_trust_assessments.jsonl",
        "counterparty_expectation_updates.jsonl",
        "disclosure_assessments.jsonl",
        "turn_summaries.jsonl",
    )

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for artifact_name in self.JSONL_ARTIFACTS:
            (self.output_dir / artifact_name).touch()

    def write_json(self, name: str, data: dict[str, Any]) -> None:
        path = self.output_dir / name
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def append_jsonl(self, name: str, record: dict[str, Any]) -> None:
        append_jsonl(self.output_dir / name, record)

    def write_tick_artifacts(
        self,
        run_id: str,
        state: StateStore,
        tick_result: TickResult,
        agent_turn: AgentTurnResult,
        transition_result: TransitionResult,
        safety_result: SafetyTickResult,
        public_start_index: int,
        private_message_start_index: int,
        breach_start_index: int,
        finding_start_index: int,
        disclosure_start_index: int,
        trust_update_start_index: int,
        expectation_update_start_index: int,
    ) -> dict[str, Any]:
        snapshot = export_state_snapshot(state)
        self.append_jsonl("state_snapshots.jsonl", {"run_id": run_id, **snapshot})

        for entry in state.public.ledger[public_start_index:]:
            self.append_jsonl(
                "public_ledger.jsonl",
                {"run_id": run_id, **entry.model_dump(mode="json")},
            )

        for envelope in state.private_messages[private_message_start_index:]:
            self.append_jsonl(
                "private_messages.jsonl",
                {"run_id": run_id, **envelope.model_dump(mode="json")},
            )

        for breach in state.canonical.breach_records[breach_start_index:]:
            self.append_jsonl(
                "contract_breaches.jsonl",
                {"run_id": run_id, **breach.model_dump(mode="json")},
            )

        for finding in state.oversight_findings[finding_start_index:]:
            self.append_jsonl(
                "oversight_findings.jsonl",
                {"run_id": run_id, **finding.model_dump(mode="json")},
            )

        for assessment in state.disclosure_assessments[disclosure_start_index:]:
            self.append_jsonl(
                "disclosure_assessments.jsonl",
                {"run_id": run_id, **assessment.model_dump(mode="json")},
            )

        for trust_update in state.trust_updates[trust_update_start_index:]:
            self.append_jsonl(
                "trust_updates.jsonl",
                {"run_id": run_id, **trust_update.model_dump(mode="json")},
            )

        for expectation_update in state.expectation_update_records[expectation_update_start_index:]:
            self.append_jsonl(
                "counterparty_expectation_updates.jsonl",
                {"run_id": run_id, **expectation_update.model_dump(mode="json")},
            )

        for record in agent_turn.records:
            base = {
                "run_id": run_id,
                "tick": tick_result.tick,
                "agent_id": record.agent_id.value,
            }
            self.append_jsonl(
                "agent_observations.jsonl",
                {**base, "observation": record.observation.model_dump(mode="json")},
            )
            self.append_jsonl(
                "agent_submissions.jsonl",
                {
                    **base,
                    "submission": record.submission.model_dump(mode="json"),
                    "validation": record.validation.model_dump(mode="json"),
                    "used_fallback": record.used_fallback,
                    "raw_output": record.raw_output,
                    "parse_errors": record.parse_errors,
                },
            )
            self.append_jsonl(
                "agent_beliefs.jsonl",
                {**base, "belief": record.submission.belief_update.model_dump(mode="json")},
            )
            self.append_jsonl(
                "agent_decision_reports.jsonl",
                {
                    **base,
                    "observed_new_info": record.submission.observed_new_info,
                    "decision": record.submission.decision.model_dump(mode="json"),
                    "rationale": record.submission.rationale,
                    "decision_parameters_used": record.submission.decision_parameters_used,
                    "counterparty_assessments": [
                        assessment.model_dump(mode="json")
                        for assessment in record.submission.counterparty_assessments
                    ],
                    "counterparty_expectation_updates": [
                        update.model_dump(mode="json")
                        for update in record.submission.counterparty_expectation_updates
                    ],
                    "belief_update": record.submission.belief_update.model_dump(mode="json"),
                    "communication_summary": (
                        record.submission.communication.summary
                        if record.submission.communication is not None
                        else None
                    ),
                    "validation": record.validation.model_dump(mode="json"),
                    "used_fallback": record.used_fallback,
                    "transitions_applied": [
                        transition.model_dump(mode="json")
                        for transition in transition_result.applied
                        if transition.agent_id == record.agent_id
                    ],
                },
            )
            for counterparty_assessment in record.submission.counterparty_assessments:
                self.append_jsonl(
                    "agent_trust_assessments.jsonl",
                    {
                        **base,
                        "assessment": counterparty_assessment.model_dump(mode="json"),
                    },
                )

        summary = build_turn_summary(tick_result, agent_turn, transition_result, safety_result)
        self.append_jsonl("turn_summaries.jsonl", {"run_id": run_id, **summary})
        return summary


def build_turn_summary(
    tick_result: TickResult,
    agent_turn: AgentTurnResult,
    transition_result: TransitionResult,
    safety_result: SafetyTickResult | None = None,
) -> dict[str, Any]:
    """Build a deterministic summary from delivered events and agent submissions."""
    safety_result = safety_result or SafetyTickResult(tick=tick_result.tick)
    return {
        "tick": tick_result.tick,
        "public_events": [
            {
                "entry_id": entry.entry_id,
                "entry_type": entry.entry_type.value,
                "linked_object_id": entry.linked_object_id,
                "data": entry.data,
            }
            for entry in tick_result.delivered.public_entries
        ],
        "private_events": [
            {
                "agent_id": agent_id.value,
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "summary": event.summary,
            }
            for agent_id, events in tick_result.delivered.private_events_by_agent.items()
            for event in events
        ],
        "private_messages": [
            {
                "agent_id": agent_id.value,
                "message_id": message.message_id,
                "sender": message.sender.value,
                "recipients": [recipient.value for recipient in message.recipients],
                "summary": message.summary,
            }
            for agent_id, messages in tick_result.delivered.private_messages_by_agent.items()
            for message in messages
        ],
        "active_agents": [agent.value for agent in tick_result.active_agents],
        "decisions": [
            {
                "agent_id": record.agent_id.value,
                "decision_type": record.submission.decision.type.value,
                "object_type": record.submission.decision.object_type,
                "object_id": record.submission.decision.object_id,
                "valid": record.validation.valid,
                "used_fallback": record.used_fallback,
            }
            for record in agent_turn.records
        ],
        "communications": [
            {
                "agent_id": record.agent_id.value,
                "visibility": record.submission.communication.visibility.value,
                "recipients": [
                    recipient.value for recipient in record.submission.communication.recipients
                ],
                "summary": record.submission.communication.summary,
            }
            for record in agent_turn.records
            if record.submission.communication is not None
        ],
        "canonical_state_changes": [
            transition.model_dump(mode="json")
            for transition in transition_result.applied
            if transition.target_store == "canonical"
        ],
        "public_state_changes": [
            *[entry.entry_id for entry in tick_result.delivered.public_entries],
            *[
                transition.object_id
                for transition in transition_result.applied
                if transition.target_store == "public" and transition.object_id is not None
            ],
        ],
        "private_state_changes": [
            *[
                event.event_id
                for events in tick_result.delivered.private_events_by_agent.values()
                for event in events
            ],
            *[
                transition.object_id
                for transition in transition_result.applied
                if transition.target_store == "private" and transition.object_id is not None
            ],
        ],
        "transition_rejections": transition_result.rejected,
        "contract_breaches": [
            breach.model_dump(mode="json") for breach in safety_result.breach_records
        ],
        "oversight_findings": [
            finding.model_dump(mode="json") for finding in safety_result.oversight_findings
        ],
        "disclosure_assessments": [
            assessment.model_dump(mode="json")
            for assessment in safety_result.disclosure_assessments
        ],
        "trust_updates": [
            trust_update.model_dump(mode="json")
            for trust_update in safety_result.trust_updates
        ],
        "belief_changes": [
            {
                "agent_id": record.agent_id.value,
                "basis_ids": record.submission.belief_update.basis_ids,
            }
            for record in agent_turn.records
        ],
        "agent_trust_assessments": [
            {
                "agent_id": record.agent_id.value,
                "assessments": [
                    assessment.model_dump(mode="json")
                    for assessment in record.submission.counterparty_assessments
                ],
            }
            for record in agent_turn.records
            if record.submission.counterparty_assessments
        ],
        "counterparty_expectation_updates": [
            submitted_update.model_dump(mode="json")
            for record in agent_turn.records
            for submitted_update in record.submission.counterparty_expectation_updates
        ],
    }


def build_analysis_packet(
    run_config: dict[str, Any],
    scenario_config: ScenarioConfig,
    state: StateStore,
    turn_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the primary external-analysis artifact."""
    final_metrics = calculate_final_metrics(state)
    return {
        "run_config": run_config,
        "scenario_config": scenario_config.model_dump(mode="json"),
        "agent_role_configs": {
            role.value: config.model_dump(mode="json")
            for role, config in state.role_configs.items()
        },
        "agent_policy_profiles": {
            role.value: config.policy_profile.value
            for role, config in state.role_configs.items()
        },
        "oversight_condition": run_config["oversight_condition"],
        "turn_summaries": turn_summaries,
        "final_metrics": final_metrics,
        "final_beliefs_by_agent": {
            role.value: belief.model_dump(mode="json")
            for role, belief in state.beliefs_by_agent.items()
        },
        "agent_decision_reports": [
            {
                "tick": summary["tick"],
                "decisions": summary["decisions"],
                "belief_changes": summary["belief_changes"],
                "canonical_state_changes": summary["canonical_state_changes"],
                "public_state_changes": summary["public_state_changes"],
                "private_state_changes": summary["private_state_changes"],
                "contract_breaches": summary["contract_breaches"],
                "oversight_findings": summary["oversight_findings"],
                "disclosure_assessments": summary["disclosure_assessments"],
                "trust_updates": summary["trust_updates"],
                "agent_trust_assessments": summary["agent_trust_assessments"],
                "counterparty_expectation_updates": summary[
                    "counterparty_expectation_updates"
                ],
            }
            for summary in turn_summaries
            if summary["decisions"]
            or summary["contract_breaches"]
            or summary["oversight_findings"]
            or summary["disclosure_assessments"]
            or summary["trust_updates"]
            or summary["agent_trust_assessments"]
            or summary["counterparty_expectation_updates"]
        ],
        "material_claims": [
            {
                "entry_id": entry.entry_id,
                "tick": entry.tick,
                "source": entry.source,
                "claims": [claim.model_dump(mode="json") for claim in entry.claims],
            }
            for entry in state.public.ledger
            if entry.claims
        ],
        "final_trust_by_agent": {
            observer.value: {
                target.value: trust.model_dump(mode="json")
                for target, trust in targets.items()
            }
            for observer, targets in state.agent_trust_by_agent.items()
        },
        "final_mechanical_reputation_by_agent": {
            observer.value: {
                target.value: trust.model_dump(mode="json")
                for target, trust in targets.items()
            }
            for observer, targets in state.trust_by_agent.items()
        },
        "final_expectations_by_agent": {
            observer.value: {
                target.value: expectation.model_dump(mode="json")
                for target, expectation in targets.items()
            }
            for observer, targets in state.expectations_by_agent.items()
        },
        "counterparty_expectation_update_records": [
            update.model_dump(mode="json")
            for update in state.expectation_update_records
        ],
    }
