from __future__ import annotations

from typing import Any

from constructbench.state import DecisionSelection, RunState

PARAMETER_OPTION = "__parameters__"


class NodeDefinition:
    def __init__(
        self,
        node_id: str,
        actor_id: str,
        available_tick: int,
        option_ids: list[str] | None = None,
        parameters: dict[str, list[Any]] | None = None,
        deadline_tick: int | None = None,
    ) -> None:
        self.node_id = node_id
        self.actor_id = actor_id
        self.available_tick = available_tick
        self.option_ids = option_ids or [PARAMETER_OPTION]
        self.parameters = parameters or {}
        self.deadline_tick = deadline_tick


def validate_selection(state: RunState, spec: Any, actor_id: str, selection: DecisionSelection) -> str:
    node = state.decision_state.get(selection.node_id)
    if node is None:
        raise ValueError(f"unknown decision node {selection.node_id}")
    if node.status != "available":
        raise ValueError(f"decision node {selection.node_id} is {node.status}, not available")
    if node.actor_id != actor_id:
        raise ValueError(f"{actor_id} is not authorized for decision node {selection.node_id}")
    node_def = spec.node_defs[selection.node_id]
    option_id = selection.option_id or PARAMETER_OPTION
    if option_id not in node_def.option_ids:
        raise ValueError(f"invalid option {option_id} for {selection.node_id}")
    for name, allowed in node_def.parameters.items():
        if name not in selection.parameters:
            raise ValueError(f"missing required parameter {name} for {selection.node_id}")
        if selection.parameters[name] not in allowed:
            raise ValueError(
                f"parameter {name}={selection.parameters[name]!r} is not allowed for {selection.node_id}"
            )
    extra = set(selection.parameters) - set(node_def.parameters)
    if extra:
        raise ValueError(f"unexpected parameters for {selection.node_id}: {sorted(extra)}")
    spec.validate_selection(state, selection, option_id)
    return option_id


def mark_selected(state: RunState, actor_id: str, selection: DecisionSelection, option_id: str) -> str:
    node = state.decision_state[selection.node_id]
    node.status = "resolved"
    node.selected_option_id = option_id
    node.selected_parameters = dict(selection.parameters)
    node.selected_tick = state.tick
    record_id = f"decision_{len(state.histories['decision_history']) + 1:06d}"
    state.histories["decision_history"].append(
        {
            "decision_record_id": record_id,
            "tick": state.tick,
            "actor_id": actor_id,
            "node_id": selection.node_id,
            "option_id": option_id,
            "parameters": dict(selection.parameters),
        }
    )
    return record_id


def option_selected(state: RunState, node_id: str, option_id: str | None = None) -> bool:
    node = state.decision_state.get(node_id)
    if node is None or node.status != "resolved":
        return False
    return option_id is None or node.selected_option_id == option_id


def selected_option(state: RunState, node_id: str) -> str | None:
    node = state.decision_state.get(node_id)
    return node.selected_option_id if node and node.status == "resolved" else None


def selected_parameters(state: RunState, node_id: str) -> dict[str, Any]:
    node = state.decision_state.get(node_id)
    if node and node.status == "resolved":
        return dict(node.selected_parameters)
    return {}
