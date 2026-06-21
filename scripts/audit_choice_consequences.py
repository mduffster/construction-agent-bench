from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path
from typing import Any

from constructbench.runner import _apply_event_phase
from constructbench.scenarios import SCENARIOS, Scenario
from constructbench.state import DecisionRequest, DecisionSelection, Phase, RunState


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit that each reachable scenario choice has a deterministic consequence."
    )
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), action="append")
    parser.add_argument("--variant", choices=["normal", "stressed"], action="append")
    parser.add_argument("--contexts-per-node", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    scenarios = args.scenario or sorted(SCENARIOS)
    variants = args.variant or ["normal", "stressed"]
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for scenario_key in scenarios:
        for variant in variants:
            scenario = SCENARIOS[scenario_key]
            contexts_by_node, steps = collect_contexts(
                scenario,
                scenario_key,
                variant,
                contexts_per_node=args.contexts_per_node,
                max_steps=args.max_steps,
            )
            for node_id, contexts in contexts_by_node.items():
                if not contexts:
                    failure = {
                        "scenario": scenario_key,
                        "variant": variant,
                        "node_id": node_id,
                        "choice_atom": "UNREACHED",
                    }
                    rows.append({**failure, "passed": False, "contexts": 0, "steps": steps})
                    failures.append(failure)
                    continue
                request = contexts[0][2]
                result_by_atom = audit_request(scenario, contexts, request)
                for atom, passed in result_by_atom.items():
                    row = {
                        "scenario": scenario_key,
                        "variant": variant,
                        "node_id": node_id,
                        "choice_atom": atom,
                        "passed": passed,
                        "contexts": len(contexts),
                        "steps": steps,
                    }
                    rows.append(row)
                    if not passed:
                        failures.append(row)

    payload = {
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "rows": rows,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": payload["passed"], "failure_count": len(failures)}, indent=2))
    if failures:
        for failure in failures:
            print(
                f"{failure['scenario']} {failure['variant']} {failure['node_id']} "
                f"{failure['choice_atom']}"
            )
        raise SystemExit(1)


def collect_contexts(
    scenario: Scenario,
    scenario_key: str,
    variant: str,
    *,
    contexts_per_node: int,
    max_steps: int,
) -> tuple[dict[str, list[tuple[RunState, Phase, DecisionRequest]]], int]:
    contexts_by_node: dict[str, list[tuple[RunState, Phase, DecisionRequest]]] = {
        node_id: [] for node_id in scenario.actors
    }
    root = scenario.create_state(run_id=f"audit_{scenario_key}_{variant}", variant=variant)  # type: ignore[arg-type]
    queue = [root]
    seen: set[str] = set()
    steps = 0
    while queue and steps < max_steps:
        steps += 1
        state = queue.pop(0)
        key = json.dumps(
            {
                "decisions": state.decisions,
                "phase_history": state.histories["phase_history"],
                "terminal_status": state.terminal_status,
            },
            sort_keys=True,
            default=str,
        )
        if key in seen:
            continue
        seen.add(key)
        phase = next_agent_phase(scenario, state)
        if phase is None:
            continue
        requests = [request for turn in phase.turns for request in turn.required_decisions]
        for request in requests:
            contexts = contexts_by_node.setdefault(request.node_id, [])
            if len(contexts) < contexts_per_node:
                contexts.append((state.model_copy(deep=True), phase, request))
        if all(len(contexts) >= contexts_per_node for contexts in contexts_by_node.values()):
            break
        for selections in representative_phase_selections(requests):
            child = state.model_copy(deep=True)
            apply_phase(
                scenario,
                child,
                phase,
                {selection.node_id: selection for selection in selections},
            )
            queue.append(child)
    return contexts_by_node, steps


def representative_phase_selections(
    requests: list[DecisionRequest],
) -> list[tuple[DecisionSelection, ...]]:
    if not requests:
        return []
    defaults = {request.node_id: default_selection(request) for request in requests}
    represented: list[tuple[DecisionSelection, ...]] = [
        tuple(defaults[request.node_id] for request in requests)
    ]
    seen = {
        tuple(
            json.dumps(selection.model_dump(mode="json"), sort_keys=True)
            for selection in represented[0]
        )
    }
    for request in requests:
        for selection in representative_request_selections(request):
            overrides = dict(defaults)
            overrides[request.node_id] = selection
            combo = tuple(overrides[item.node_id] for item in requests)
            key = tuple(
                json.dumps(item.model_dump(mode="json"), sort_keys=True)
                for item in combo
            )
            if key not in seen:
                seen.add(key)
                represented.append(combo)
    return represented


def representative_request_selections(request: DecisionRequest) -> list[DecisionSelection]:
    if request.selection_mode == "single":
        return [
            DecisionSelection(node_id=request.node_id, option_id=option.option_id, parameters={})
            for option in request.options
        ]
    defaults = {name: values[0] for name, values in request.parameters.items()}
    selections = [
        DecisionSelection(
            node_id=request.node_id,
            option_id="__parameters__",
            parameters=dict(defaults),
        )
    ]
    for parameter, values in request.parameters.items():
        for value in values:
            parameters = dict(defaults)
            parameters[parameter] = value
            selections.append(
                DecisionSelection(
                    node_id=request.node_id,
                    option_id="__parameters__",
                    parameters=parameters,
                )
            )
    return selections


def audit_request(
    scenario: Scenario,
    contexts: list[tuple[RunState, Phase, DecisionRequest]],
    request: DecisionRequest,
) -> dict[str, bool]:
    if request.selection_mode == "single":
        option_ids = [option.option_id for option in request.options]
        passed = {f"option:{option_id}": False for option_id in option_ids}
        for base_state, phase, _ in contexts:
            for supporting_overrides in same_phase_supporting_overrides(phase, request.node_id):
                signatures = {
                    option_id: complete_with_defaults(
                        scenario,
                        apply_and_copy(
                            scenario,
                            base_state,
                            phase,
                            DecisionSelection(
                                node_id=request.node_id,
                                option_id=option_id,
                                parameters={},
                            ),
                            supporting_overrides,
                        ),
                    )
                    for option_id in option_ids
                }
                for option_id, signature in signatures.items():
                    if any(
                        signature != other_signature
                        for other_option_id, other_signature in signatures.items()
                        if other_option_id != option_id
                    ):
                        passed[f"option:{option_id}"] = True
        return passed

    results: dict[str, bool] = {}
    for parameter, values in request.parameters.items():
        passed = {repr(value): False for value in values}
        for base_state, phase, _ in contexts:
            for supporting_overrides in same_phase_supporting_overrides(phase, request.node_id):
                signatures = {}
                for value in values:
                    parameters = {
                        name: allowed_values[0]
                        for name, allowed_values in request.parameters.items()
                    }
                    parameters[parameter] = value
                    signatures[repr(value)] = complete_with_defaults(
                        scenario,
                        apply_and_copy(
                            scenario,
                            base_state,
                            phase,
                            DecisionSelection(
                                node_id=request.node_id,
                                option_id="__parameters__",
                                parameters=parameters,
                            ),
                            supporting_overrides,
                        ),
                    )
                for value_repr, signature in signatures.items():
                    if any(
                        signature != other_signature
                        for other_value_repr, other_signature in signatures.items()
                        if other_value_repr != value_repr
                    ):
                        passed[value_repr] = True
        results.update(
            {f"param:{parameter}={value_repr}": value_passed for value_repr, value_passed in passed.items()}
        )
    return results


def same_phase_supporting_overrides(
    phase: Phase,
    target_node_id: str,
) -> list[dict[str, DecisionSelection]]:
    other_requests = [
        request
        for turn in phase.turns
        for request in turn.required_decisions
        if request.node_id != target_node_id
    ]
    if not other_requests:
        return [{}]
    overrides: list[dict[str, DecisionSelection]] = []
    for selections in product(*(all_selections(request) for request in other_requests)):
        overrides.append({selection.node_id: selection for selection in selections})
    return overrides


def apply_and_copy(
    scenario: Scenario,
    state: RunState,
    phase: Phase,
    selection: DecisionSelection,
    supporting_overrides: dict[str, DecisionSelection] | None = None,
) -> RunState:
    copied = state.model_copy(deep=True)
    overrides = dict(supporting_overrides or {})
    overrides[selection.node_id] = selection
    apply_phase(scenario, copied, phase, overrides)
    return copied


def all_selections(request: DecisionRequest) -> list[DecisionSelection]:
    if request.selection_mode == "single":
        return [
            DecisionSelection(node_id=request.node_id, option_id=option.option_id, parameters={})
            for option in request.options
        ]
    names = list(request.parameters)
    return [
        DecisionSelection(
            node_id=request.node_id,
            option_id="__parameters__",
            parameters=dict(zip(names, values, strict=True)),
        )
        for values in product(*(request.parameters[name] for name in names))
    ]


def default_selection(request: DecisionRequest) -> DecisionSelection:
    if request.selection_mode == "single":
        return DecisionSelection(
            node_id=request.node_id,
            option_id=request.options[0].option_id,
            parameters={},
        )
    return DecisionSelection(
        node_id=request.node_id,
        option_id="__parameters__",
        parameters={name: values[0] for name, values in request.parameters.items()},
    )


def apply_phase(
    scenario: Scenario,
    state: RunState,
    phase: Phase,
    overrides: dict[str, DecisionSelection] | None = None,
) -> None:
    overrides = overrides or {}
    for turn in phase.turns:
        for request in turn.required_decisions:
            scenario.apply_decision(state, overrides.get(request.node_id) or default_selection(request))
    mark_phase_done(state, phase)


def next_agent_phase(scenario: Scenario, state: RunState) -> Phase | None:
    while True:
        phase = scenario.next_phase(state)
        if phase is None:
            return None
        state.phase_index += 1
        if phase.phase_type == "event_phase":
            _apply_event_phase(state, [], phase)
        elif phase.phase_type == "assessment_phase":
            mark_phase_done(state, phase)
        else:
            return phase


def complete_with_defaults(scenario: Scenario, state: RunState) -> str:
    for _ in range(60):
        phase = scenario.next_phase(state)
        if phase is None:
            break
        state.phase_index += 1
        if phase.phase_type == "event_phase":
            _apply_event_phase(state, [], phase)
        elif phase.phase_type == "assessment_phase":
            mark_phase_done(state, phase)
        else:
            apply_phase(scenario, state, phase)
    if state.terminal_status == "IN_PROGRESS":
        scenario.finalize(state)
    return json.dumps(
        {
            "terminal_status": state.terminal_status,
            "terminal_reason": state.terminal_reason,
            "canonical_state": state.canonical_state,
        },
        sort_keys=True,
        default=str,
    )


def mark_phase_done(state: RunState, phase: Phase) -> None:
    state.histories["phase_history"].append(
        {
            "phase_index": state.phase_index,
            "phase_id": phase.phase_id,
            "phase_type": phase.phase_type,
            "summary": phase.summary,
        }
    )


if __name__ == "__main__":
    main()
