from __future__ import annotations

from typing import Any

from constructbench.state import AGENT_IDS, Communication, RunState

CLAIM_TYPES: dict[str, type | tuple[type, ...]] = {
    "forecast_delivery_tick": int,
    "source_status": str,
    "requested_price_amendment": int,
    "requested_delivery_tick": (int, type(None)),
    "project_forecast_completion_tick": int,
    "project_forecast_final_cost": int,
    "crane_status": str,
    "crane_work_finish_tick": int,
    "provisional_crane_work_finish_tick": int,
    "weather_protection_status": str,
    "material_delivery_acceptance_status": str,
    "expected_full_payment_tick": int,
    "payment_status_tick_22": str,
    "payment_status": str,
    "initial_payment_amount": int,
    "remaining_payment_tick": int,
    "work_status": str,
    "expected_structural_release_tick": int,
    "expected_project_completion_tick": int,
    "corrective_strategy": str,
    "claimed_defect_count": int,
    "critical_task_finish_tick": int,
    "claimed_available_crew_count": int,
    "claimed_capacity_plan": str,
    "inspection_booking_status": str,
}


def validate_communication(state: RunState, actor_id: str, communication: Communication) -> None:
    if communication.communication_type == "private_message":
        if not communication.recipient_ids:
            raise ValueError("private_message requires at least one recipient")
        invalid = [recipient for recipient in communication.recipient_ids if recipient not in AGENT_IDS]
        if invalid:
            raise ValueError(f"unknown private message recipients: {invalid}")
    elif communication.communication_type == "public_message":
        if communication.recipient_ids:
            raise ValueError("public_message recipient_ids must be empty")
    elif communication.communication_type == "publish_decision":
        if not communication.decision_record_id:
            raise ValueError("publish_decision requires decision_record_id")
    for claim in communication.claims:
        expected_type = CLAIM_TYPES.get(claim.field)
        if expected_type is None:
            raise ValueError(f"claim field {claim.field!r} is not in the scenario claim registry")
        if not isinstance(claim.value, expected_type):
            raise ValueError(f"claim field {claim.field!r} has value with invalid type")


def queue_communication(state: RunState, actor_id: str, communication: Communication) -> dict[str, Any]:
    message_id = f"message_{len(state.histories['message_history']) + 1:06d}"
    deliver_tick = state.tick + 1
    record: dict[str, Any] = {
        "message_id": message_id,
        "tick": state.tick,
        "deliver_tick": deliver_tick,
        "sender_id": actor_id,
        "communication_type": communication.communication_type,
        "recipient_ids": list(communication.recipient_ids),
        "summary": communication.summary,
        "claims": [claim.model_dump(mode="json") for claim in communication.claims],
        "decision_record_id": communication.decision_record_id,
    }
    state.histories["message_history"].append(record)
    if communication.communication_type == "private_message":
        state.message_state["pending_private_messages"].append(record)
    else:
        state.message_state["pending_public_messages"].append(record)
    return record


def is_trust_evidence_message(message: dict[str, Any]) -> bool:
    return bool(message.get("claims")) or bool(message.get("decision_record_id"))


def deliver_due_messages(state: RunState) -> list[str]:
    delivered: list[str] = []
    remaining_private: list[dict[str, Any]] = []
    for message in state.message_state["pending_private_messages"]:
        if message["deliver_tick"] <= state.tick:
            for recipient in message["recipient_ids"]:
                state.private_state_by_agent[recipient]["messages"].append(message)
                if is_trust_evidence_message(message):
                    state.private_state_by_agent[recipient]["new_evidence_ids"].append(message["message_id"])
            delivered.append(message["message_id"])
        else:
            remaining_private.append(message)
    state.message_state["pending_private_messages"] = remaining_private

    remaining_public: list[dict[str, Any]] = []
    for message in state.message_state["pending_public_messages"]:
        if message["deliver_tick"] <= state.tick:
            state.public_state["ledger"].append(message)
            if is_trust_evidence_message(message):
                state.public_state["new_event_ids"].append(message["message_id"])
                for private_state in state.private_state_by_agent.values():
                    private_state["new_evidence_ids"].append(message["message_id"])
            delivered.append(message["message_id"])
        else:
            remaining_public.append(message)
    state.message_state["pending_public_messages"] = remaining_public
    return delivered
