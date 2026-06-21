from __future__ import annotations

from copy import deepcopy
from typing import Any

from constructbench.evidence import evidence_packet_for_id
from constructbench.state import AgentObservation, RunState


def build_observation(state: RunState, spec: Any, agent_id: str) -> AgentObservation:
    available_nodes: list[dict[str, Any]] = []
    for node in state.decision_state.values():
        if node.actor_id == agent_id and node.status == "available":
            node_def = spec.node_defs[node.node_id]
            available_nodes.append(
                {
                    "node_id": node.node_id,
                    "selection_mode": node.selection_mode,
                    "available_tick": node.available_tick,
                    "deadline_tick": node.deadline_tick,
                    "available_option_ids": list(node.option_ids),
                    "parameters": deepcopy(node_def.parameters),
                }
            )
    own_decisions = [
        deepcopy(record)
        for record in state.histories["decision_history"]
        if record["actor_id"] == agent_id
    ]
    private_state = deepcopy(state.private_state_by_agent[agent_id])
    messages = list(private_state.get("messages", []))
    evidence_ids = list(private_state.get("new_evidence_ids", []))
    trust_evidence = [
        packet
        for packet in [
            evidence_packet_for_id(state, agent_id, evidence_id)
            for evidence_id in evidence_ids
        ]
        if _requires_counterparty_review(agent_id, packet)
    ]
    return AgentObservation(
        run_id=state.run_id,
        tick=state.tick,
        agent_id=agent_id,
        goal_profile=state.goal_profile_by_agent[agent_id],
        public_state=deepcopy(state.public_state),
        private_state=private_state,
        new_public_event_ids=list(state.public_state.get("new_event_ids", [])),
        new_private_effect_ids=evidence_ids,
        messages_delivered=messages,
        available_decision_nodes=available_nodes,
        own_resolved_decisions=own_decisions,
        trust_prior_by_counterparty=deepcopy(state.trust_state[agent_id]),
        new_trust_evidence=trust_evidence,
    )


def active_agents(state: RunState) -> list[str]:
    agents = {
        node.actor_id
        for node in state.decision_state.values()
        if node.status == "available"
    }
    for agent_id, private_state in state.private_state_by_agent.items():
        if private_state.get("new_evidence_ids"):
            agents.add(agent_id)
    return sorted(agents)


def _requires_counterparty_review(agent_id: str, packet: dict[str, Any]) -> bool:
    counterparties = packet.get("possible_counterparty_ids", [])
    return any(counterparty != agent_id for counterparty in counterparties)
