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
    parser.add_argument("--contexts-per-node", type=int, default=0)
    parser.add_argument("--branch-limit", type=int, default=0)
    parser.add_argument("--max-parameters-per-request", type=int, default=0)
    parser.add_argument("--max-values-per-parameter", type=int, default=0)
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
            if variant not in scenario.starts:
                continue
            limits = audit_limits(
                scenario,
                contexts_per_node=args.contexts_per_node,
                branch_limit=args.branch_limit,
                max_parameters=args.max_parameters_per_request,
                max_values=args.max_values_per_parameter,
            )
            contexts_by_node, steps = collect_contexts(
                scenario,
                scenario_key,
                variant,
                contexts_per_node=limits["contexts_per_node"],
                branch_limit=limits["branch_limit"],
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
                result_by_atom = audit_request(
                    scenario,
                    contexts,
                    request,
                    max_parameters=limits["max_parameters"],
                    max_values=limits["max_values"],
                )
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
        "sampling": {
            "contexts_per_node": args.contexts_per_node or "auto",
            "branch_limit": args.branch_limit or "auto",
            "max_parameters_per_request": args.max_parameters_per_request or "auto",
            "max_values_per_parameter": args.max_values_per_parameter or "auto",
        },
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


def audit_limits(
    scenario: Scenario,
    *,
    contexts_per_node: int,
    branch_limit: int,
    max_parameters: int,
    max_values: int,
) -> dict[str, int]:
    bounded_scenario = scenario.scenario_id == "S01_V2_OFFSITE_STEEL_DRAW"
    return {
        "contexts_per_node": contexts_per_node or (1 if bounded_scenario else 20),
        "branch_limit": branch_limit or (6 if bounded_scenario else 1_000_000),
        "max_parameters": max_parameters or (4 if bounded_scenario else 1_000_000),
        "max_values": max_values or (3 if bounded_scenario else 1_000_000),
    }


def collect_contexts(
    scenario: Scenario,
    scenario_key: str,
    variant: str,
    *,
    contexts_per_node: int,
    branch_limit: int,
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
        children = []
        for selections in representative_phase_selections(requests)[:branch_limit]:
            child = state.model_copy(deep=True)
            apply_phase(
                scenario,
                child,
                phase,
                {selection.node_id: selection for selection in selections},
            )
            children.append(child)
        queue = children + queue
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
    if request.parameter_specs:
        defaults = {
            name: default_parameter_value(spec)
            for name, spec in request.parameter_specs.items()
        }
        selections = [
            DecisionSelection(
                node_id=request.node_id,
                option_id="__parameters__",
                parameters=dict(defaults),
            )
        ]
        for parameter, spec in request.parameter_specs.items():
            for value in representative_parameter_values(spec):
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
    *,
    max_parameters: int,
    max_values: int,
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
    parameter_values = (
        {
            name: representative_parameter_values(spec)
            for name, spec in request.parameter_specs.items()
        }
        if request.parameter_specs
        else request.parameters
    )
    for parameter, values in list(parameter_values.items())[:max_parameters]:
        values = values[:max_values]
        passed = {repr(value): False for value in values}
        for base_state, phase, _ in contexts:
            for supporting_overrides in same_phase_supporting_overrides(phase, request.node_id):
                signatures = {}
                for value in values:
                    parameters = default_parameters(request)
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
    if request.parameter_specs or len(request.parameters) > 3:
        return representative_request_selections(request)
    if request.parameter_specs:
        names = list(request.parameter_specs)
        value_sets = [
            representative_parameter_values(request.parameter_specs[name])
            for name in names
        ]
        return [
            DecisionSelection(
                node_id=request.node_id,
                option_id="__parameters__",
                parameters=dict(zip(names, values, strict=True)),
            )
            for values in product(*value_sets)
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
        parameters=default_parameters(request),
    )


def default_parameters(request: DecisionRequest) -> dict[str, Any]:
    if request.parameter_specs:
        return {
            name: default_parameter_value(spec)
            for name, spec in request.parameter_specs.items()
        }
    return {name: values[0] for name, values in request.parameters.items()}


def default_parameter_value(spec) -> Any:
    if spec.default is not None:
        return spec.default
    if spec.nullable:
        return None
    if spec.allowed_values:
        return [] if spec.value_type in {"list", "set", "reference"} else spec.allowed_values[0]
    if spec.value_type in {"list", "set", "reference"}:
        return []
    if spec.value_type == "boolean":
        return False
    if spec.min_value is not None:
        return int(spec.min_value) if spec.value_type == "integer" else float(spec.min_value)
    return None


def representative_parameter_values(spec) -> list[Any]:
    values: list[Any] = []
    for value in spec.audit_values:
        if value not in values:
            values.append(value)
    default = default_parameter_value(spec)
    if default not in values:
        values.insert(0, default)
    if spec.value_type in {"integer", "decimal"}:
        if spec.min_value is not None and spec.min_value not in values:
            values.append(spec.min_value)
        if spec.max_value is not None and spec.max_value not in values:
            values.append(spec.max_value)
        if spec.min_value is not None and spec.max_value is not None:
            midpoint = (spec.min_value + spec.max_value) / 2
            if spec.value_type == "integer":
                midpoint = int(midpoint)
            if midpoint not in values:
                values.append(midpoint)
    elif spec.value_type == "boolean":
        values = [False, True]
    elif spec.value_type == "enum":
        for value in spec.allowed_values:
            if value not in values:
                values.append(value)
    elif spec.value_type in {"list", "set", "reference"}:
        candidates = [[], spec.allowed_values[:1], spec.allowed_values]
        for value in candidates:
            if value not in values:
                values.append(value)
    return values


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
        elif phase.phase_type == "consequence_phase":
            scenario.apply_consequence_phase(state, phase)
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
        elif phase.phase_type == "consequence_phase":
            scenario.apply_consequence_phase(state, phase)
            mark_phase_done(state, phase)
        else:
            apply_phase(scenario, state, phase)
    if state.terminal_status == "IN_PROGRESS":
        scenario.finalize(state)
    return json.dumps(_consequence_signature(state), sort_keys=True, default=str)


def _consequence_signature(state: RunState) -> dict[str, Any]:
    scenario_state = {
        key: value
        for key, value in state.canonical_state.items()
        if key.endswith("_state")
    }
    return {
        "terminal_status": state.terminal_status,
        "terminal_reason": state.terminal_reason,
        "project": state.canonical_state.get("project", {}),
        "organizations": state.canonical_state.get("organizations", {}),
        "terminal_values": state.canonical_state.get("terminal_values", {}),
        "payoff_ledger": state.canonical_state.get("payoff_ledger", {}),
        "scenario_state": scenario_state,
    }


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
