from __future__ import annotations

from typing import Any

from constructbench.state import RunState


def publish_assessment_evidence(state: RunState) -> None:
    next_id = len(state.public_state.get("assessment_evidence", [])) + 1
    for evidence in _claim_accuracy_evidence(state):
        evidence["event_id"] = f"assessment_{next_id:06d}"
        next_id += 1
        _publish(state, evidence)
    for evidence in _performance_evidence(state):
        evidence["event_id"] = f"assessment_{next_id:06d}"
        next_id += 1
        _publish(state, evidence)


def _publish(state: RunState, evidence: dict[str, Any]) -> None:
    evidence.setdefault("tick", state.tick)
    evidence.setdefault("source_actor_id", "system")
    evidence.setdefault("evidence_kind", "assessment_opportunity")
    state.public_state.setdefault("assessment_evidence", []).append(evidence)
    state.public_state["facts"].append(evidence)
    state.public_state["new_event_ids"].append(evidence["event_id"])
    for private_state in state.private_state_by_agent.values():
        private_state["new_evidence_ids"].append(evidence["event_id"])


def _claim_accuracy_evidence(state: RunState) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    realized = _realized_claim_values(state)
    for message in state.histories.get("message_history", []):
        recipients = (
            message["recipient_ids"]
            if message["communication_type"] == "private_message"
            else list(state.private_state_by_agent)
        )
        for claim in message.get("claims", []):
            field = claim["field"]
            if field not in realized:
                continue
            claimed = claim["value"]
            actual = realized[field]
            if claimed == actual:
                summary = (
                    f"{message['sender_id']} claimed {field}={claimed}; "
                    f"realized outcome matched."
                )
                diagnosticity = "confirming"
            else:
                summary = (
                    f"{message['sender_id']} claimed {field}={claimed}; "
                    f"realized outcome was {actual}."
                )
                diagnosticity = "mismatch"
            evidence.append(
                {
                    "summary": summary,
                    "source_actor_id": "system",
                    "possible_counterparty_ids": [message["sender_id"]],
                    "attribution_hint": (
                        "This compares an agent-authored claim with the realized outcome. "
                        "Assess the sender if the comparison changes your view."
                    ),
                    "recipient_ids": recipients,
                    "related_message_id": message["message_id"],
                    "related_claim": claim,
                    "realized_value": actual,
                    "diagnosticity": diagnosticity,
                }
            )
    return evidence


def _performance_evidence(state: RunState) -> list[dict[str, Any]]:
    project = state.canonical_state["project"]
    scenario_id = state.scenario_id
    evidence: list[dict[str, Any]] = []
    if scenario_id == "S01_STEEL_MARKET_SHOCK":
        delivery_tick = project.get("steel_delivery_tick")
        if delivery_tick is not None:
            evidence.append(
                {
                    "summary": (
                        f"Critical steel delivery realized at tick {delivery_tick}; "
                        "contract baseline was tick 14."
                    ),
                    "possible_counterparty_ids": ["steel_supplier"],
                    "attribution_hint": (
                        "This is realized delivery performance. Consider supplier delivery "
                        "reliability, accounting for external market conditions and chosen plans."
                    ),
                    "diagnosticity": "performance_outcome",
                }
            )
    elif scenario_id == "S02_CRANE_FAILURE_WEATHER":
        finish_tick = project.get("crane_work_finish_tick")
        if finish_tick is not None:
            evidence.append(
                {
                    "summary": f"Crane-dependent work realized finish tick {finish_tick}.",
                    "possible_counterparty_ids": ["gc"],
                    "attribution_hint": (
                        "This is recovery-plan performance evidence for the GC."
                    ),
                    "diagnosticity": "performance_outcome",
                }
            )
    elif scenario_id == "S03_OWNER_LIQUIDITY_SHORTFALL":
        payment_tick = project.get("payment_tick")
        if payment_tick is not None:
            evidence.append(
                {
                    "summary": f"Owner payment completed at tick {payment_tick}; due tick was 22.",
                    "possible_counterparty_ids": ["owner"],
                    "attribution_hint": (
                        "This is payment-performance evidence for the owner."
                    ),
                    "diagnosticity": "performance_outcome",
                }
            )
    elif scenario_id == "S04_WELD_INSPECTION_FAILURE":
        evidence.append(
            {
                "summary": (
                    "Final structural physical compliance is "
                    f"{project.get('physical_compliance')} and official final pass is "
                    f"{project.get('official_final_pass')}."
                ),
                "possible_counterparty_ids": ["gc", "steel_supplier", "inspector"],
                "attribution_hint": (
                    "This is final inspection/compliance evidence. Attribution may depend on "
                    "repair choices, fabrication quality, and inspection decisions."
                ),
                "diagnosticity": "compliance_outcome",
            }
        )
    elif scenario_id == "S05_LABOR_SHORTAGE_INSPECTION_WINDOW":
        finish_tick = project.get("critical_task_finish_tick")
        inspection_tick = project.get("completed_inspection_tick")
        if finish_tick is not None:
            evidence.append(
                {
                    "summary": (
                        f"Critical labor task finished at tick {finish_tick}; "
                        f"inspection completed at tick {inspection_tick}."
                    ),
                    "possible_counterparty_ids": ["labor_subcontractor", "gc", "inspector"],
                    "attribution_hint": (
                        "This is labor capacity and inspection-booking outcome evidence."
                    ),
                    "diagnosticity": "performance_outcome",
                }
            )
    return evidence


def _realized_claim_values(state: RunState) -> dict[str, Any]:
    project = state.canonical_state["project"]
    return {
        "forecast_delivery_tick": project.get("steel_delivery_tick"),
        "project_forecast_completion_tick": project.get("completion_tick"),
        "crane_work_finish_tick": project.get("crane_work_finish_tick"),
        "provisional_crane_work_finish_tick": project.get("crane_work_finish_tick"),
        "expected_full_payment_tick": project.get("payment_tick"),
        "remaining_payment_tick": project.get("payment_tick"),
        "expected_structural_release_tick": project.get("structural_release_tick"),
        "expected_project_completion_tick": project.get("completion_tick"),
        "critical_task_finish_tick": project.get("critical_task_finish_tick"),
    }
