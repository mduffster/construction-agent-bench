from __future__ import annotations

from typing import Any

from constructbench.state import RunState


def evidence_packet_for_id(state: RunState, agent_id: str, evidence_id: str) -> dict[str, Any]:
    for fact in state.public_state.get("facts", []):
        if fact.get("event_id") == evidence_id:
            return {
                "evidence_id": evidence_id,
                "evidence_type": fact.get("evidence_kind", "public_fact"),
                "summary": fact.get("summary", _summarize_fact(fact)),
                "source_actor_id": fact.get("source_actor_id", "system"),
                "possible_counterparty_ids": list(fact.get("possible_counterparty_ids", [])),
                "attribution_hint": fact.get("attribution_hint", ""),
                "claims": [],
                "diagnosticity": fact.get("diagnosticity"),
                "related_message_id": fact.get("related_message_id"),
                "related_claim": fact.get("related_claim"),
                "realized_value": fact.get("realized_value"),
            }

    for message in state.private_state_by_agent[agent_id].get("messages", []):
        if message.get("message_id") == evidence_id:
            return _message_packet(message, "private_message")

    for message in state.public_state.get("ledger", []):
        if message.get("message_id") == evidence_id:
            return _message_packet(message, message.get("communication_type", "public_message"))

    return {
        "evidence_id": evidence_id,
        "evidence_type": "private_or_system_effect",
        "summary": evidence_id,
        "source_actor_id": "system",
        "possible_counterparty_ids": [],
        "attribution_hint": "No counterparty attribution is implied by this evidence alone.",
        "claims": [],
    }


def _message_packet(message: dict[str, Any], evidence_type: str) -> dict[str, Any]:
    sender_id = message["sender_id"]
    return {
        "evidence_id": message["message_id"],
        "evidence_type": evidence_type,
        "summary": message.get("summary", ""),
        "source_actor_id": sender_id,
        "possible_counterparty_ids": [sender_id],
        "attribution_hint": "This is an agent-authored communication; assess the sender if it changes your view.",
        "claims": list(message.get("claims", [])),
    }


def _summarize_fact(fact: dict[str, Any]) -> str:
    event_id = fact.get("event_id", "public fact")
    fields = {
        key: value
        for key, value in fact.items()
        if key
        not in {
            "event_id",
            "summary",
            "source_actor_id",
            "possible_counterparty_ids",
            "attribution_hint",
        }
    }
    return f"{event_id}: {fields}"
