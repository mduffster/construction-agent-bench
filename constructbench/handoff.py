from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from constructbench.agents import AgentPolicy
from constructbench.analysis import analysis_row
from constructbench.focal import S01CommerciallyNeutralPolicy
from constructbench.runner import run_policy
from constructbench.scenario_instances import list_scenario_instances
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    DecisionRequest,
    DecisionSelection,
    RunState,
)

HANDOFF_EXPERIMENT_ID = "s01_distributed_threshold_handoff_v2_1"
HANDOFF_SCENARIO_ID = "S01_STEEL_MARKET_SHOCK"
HANDOFF_NODE_ID = "S01_GC_THRESHOLD_HANDOFF"
HandoffProtocol = Literal["structured_numeric", "rendered_prose"]
ScriptedHandoffMode = Literal["structured", "prose", "silent"]


def handoff_instances(*, protocol: HandoffProtocol | None = None) -> list[dict[str, Any]]:
    instances = [
        instance
        for instance in list_scenario_instances(HANDOFF_SCENARIO_ID)
        if instance.get("treatment", {}).get("experiment_id") == HANDOFF_EXPERIMENT_ID
    ]
    if protocol is not None:
        instances = [
            instance
            for instance in instances
            if instance["treatment"]["handoff_protocol"] == protocol
        ]
    return sorted(
        instances,
        key=lambda instance: (
            instance["treatment"]["response_curve_level"],
            instance["treatment"]["handoff_protocol"],
        ),
    )


def handoff_instance_ids(*, protocol: HandoffProtocol | None = None) -> list[str]:
    return [str(instance["instance_id"]) for instance in handoff_instances(protocol=protocol)]


def build_handoff_policies(
    *,
    gc_policy: AgentPolicy,
    supplier_policy: AgentPolicy,
) -> dict[str, AgentPolicy]:
    neutral = S01CommerciallyNeutralPolicy()
    policies: dict[str, AgentPolicy] = {agent_id: neutral for agent_id in AGENT_IDS}
    policies["gc"] = gc_policy
    policies["steel_supplier"] = supplier_policy
    return policies


@dataclass
class ScriptedGCHandoffPolicy:
    mode: ScriptedHandoffMode
    delegate: S01CommerciallyNeutralPolicy = field(default_factory=S01CommerciallyNeutralPolicy)

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        request = next(
            (
                request
                for request in observation.required_decisions
                if request.node_id == HANDOFF_NODE_ID
            ),
            None,
        )
        if request is None:
            return self.delegate.decide(observation)
        threshold = replacement_threshold_from_observation(observation)
        return AgentSubmission(
            decisions=[
                DecisionSelection(
                    node_id=HANDOFF_NODE_ID,
                    parameters={
                        "computed_threshold_usd": threshold,
                        "handoff_confidence": 1.0,
                        "share_with_supplier": self.mode != "silent",
                    },
                )
            ],
            private_notes=(f"scripted_gc_handoff={self.mode}; computed_threshold_usd={threshold}"),
        )


@dataclass
class HandoffOnlyGCPolicy:
    handoff_policy: AgentPolicy
    delegate: S01CommerciallyNeutralPolicy = field(default_factory=S01CommerciallyNeutralPolicy)

    def initialize(self, briefing: Any) -> None:
        if hasattr(self.handoff_policy, "initialize"):
            self.handoff_policy.initialize(briefing)  # type: ignore[attr-defined]

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        if any(request.node_id == HANDOFF_NODE_ID for request in observation.required_decisions):
            return self.handoff_policy.decide(observation)
        return self.delegate.decide(observation)

    def repair(self, observation: AgentObservation, errors: list[str]) -> AgentSubmission:
        if any(request.node_id == HANDOFF_NODE_ID for request in observation.required_decisions):
            if hasattr(self.handoff_policy, "repair"):
                return self.handoff_policy.repair(observation, errors)  # type: ignore[attr-defined]
            return self.handoff_policy.decide(observation)
        return self.delegate.decide(observation)

    def drain_model_io(self) -> list[dict[str, Any]]:
        if hasattr(self.handoff_policy, "drain_model_io"):
            return self.handoff_policy.drain_model_io()  # type: ignore[attr-defined]
        return []


@dataclass
class ThresholdResponsiveSupplierPolicy:
    fallback_request_usd: int = 800_000
    delegate: S01CommerciallyNeutralPolicy = field(default_factory=S01CommerciallyNeutralPolicy)

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        if observation.phase_id != "supplier_source_and_commercial":
            return self.delegate.decide(observation)
        threshold = transmitted_threshold_from_observation(observation)
        decisions: list[DecisionSelection] = []
        selected_request = self.fallback_request_usd
        for request in observation.required_decisions:
            if request.node_id == "S01_SUPPLIER_SOURCE_PLAN":
                decisions.append(
                    DecisionSelection(
                        node_id=request.node_id,
                        option_id="current_expedited",
                    )
                )
            elif request.node_id == "S01_SUPPLIER_COMMERCIAL_REQUEST":
                allowed = _allowed_values(request, "price_amendment_request")
                if threshold is not None:
                    safe = [value for value in allowed if int(value) <= threshold]
                    selected_request = max(safe) if safe else min(allowed)
                elif selected_request not in allowed:
                    selected_request = min(
                        allowed,
                        key=lambda value: abs(int(value) - self.fallback_request_usd),
                    )
                private = _private_facts(observation)
                decisions.append(
                    DecisionSelection(
                        node_id=request.node_id,
                        parameters={
                            "price_amendment_request": selected_request,
                            "delivery_date_amendment_request": None,
                            "advance_payment_request": 0,
                            "claimed_incremental_cost_usd": int(private["current_input_cost"])
                            - int(private["baseline_input_cost"]),
                            "claimed_liquidity_requirement_usd": int(
                                private.get("liquidity_gap", 0)
                            ),
                            "claimed_on_time_probability": 1.0,
                        },
                    )
                )
        return AgentSubmission(
            decisions=decisions,
            private_notes=(
                f"received_threshold_usd={threshold}; selected_request_usd={selected_request}"
            ),
        )


def replacement_threshold_from_observation(observation: AgentObservation) -> int:
    private = _private_facts(observation)
    context = private.get("scenario_treatment_context", {})
    economics = context.get("outside_option_economics", {})
    outside = context.get("outside_option", {})
    required = {
        "replacement_supplier_cost",
        "replacement_supplier_lead_time_ticks",
        "contract_delivery_tick",
        "project_delay_overhead_per_tick",
    }
    missing = sorted(required - set(economics))
    if missing:
        raise ValueError(f"GC replacement economics missing fields: {missing}")
    delivery_risk = float(economics.get("delivery_risk", outside.get("delivery_risk", 0.0)))
    termination_cost = int(economics.get("termination_cost", outside.get("termination_cost", 0)))
    contract_tick = int(economics["contract_delivery_tick"])
    replacement_tick = contract_tick + int(economics["replacement_supplier_lead_time_ticks"])
    delay = max(0, replacement_tick - contract_tick)
    overhead = int(economics["project_delay_overhead_per_tick"])
    return (
        int(economics["replacement_supplier_cost"])
        + termination_cost
        + (delay * overhead)
        + int(delivery_risk * 4 * overhead)
    )


def transmitted_threshold_from_observation(
    observation: AgentObservation,
) -> int | None:
    for fact in observation.known_facts:
        if fact.get("event_id") == "S01_GC_STRUCTURED_THRESHOLD_HANDOFF":
            value = fact.get("replacement_threshold_usd")
            if type(value) is int:
                return value
        if fact.get("event_id") == "S01_GC_PROSE_THRESHOLD_HANDOFF":
            return parse_threshold_prose(str(fact.get("summary", "")))
    return None


def parse_threshold_prose(summary: str) -> int | None:
    match = re.search(
        r"\breplacement threshold of\s+\$([0-9][0-9,]*)",
        summary,
        flags=re.IGNORECASE,
    )
    return int(match.group(1).replace(",", "")) if match is not None else None


def run_handoff_reference_grid(*, variant: str = "normal") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    conditions: list[tuple[HandoffProtocol, ScriptedHandoffMode]] = [
        ("structured_numeric", "structured"),
        ("rendered_prose", "prose"),
        ("rendered_prose", "silent"),
    ]
    for protocol, mode in conditions:
        for instance_id in handoff_instance_ids(protocol=protocol):
            result = run_policy(
                "S01",
                variant,
                build_handoff_policies(
                    gc_policy=ScriptedGCHandoffPolicy(mode),
                    supplier_policy=ThresholdResponsiveSupplierPolicy(),
                ),
                scenario_instance_id=instance_id,
                model_settings={
                    "policy": "handoff_deterministic_reference",
                    "handoff_condition": f"{protocol}:{mode}",
                    "focal_agent_id": "steel_supplier",
                },
            )
            rows.append(
                handoff_state_row(
                    result.final_state,
                    handoff_condition=f"{protocol}:{mode}",
                )
            )
    return rows


def handoff_state_row(
    state: RunState,
    *,
    handoff_condition: str,
) -> dict[str, Any]:
    treatment = state.canonical_state["scenario"]["scenario_instance"]["treatment"]
    true_threshold = _replacement_threshold_from_state(state)
    safe_request = _maximum_safe_request_from_state(state, true_threshold)
    computed = _decision_parameter_from_history(
        state.histories.get("decision_history", []),
        HANDOFF_NODE_ID,
        "computed_threshold_usd",
    )
    requested = _decision_parameter_from_history(
        state.histories.get("decision_history", []),
        "S01_SUPPLIER_COMMERCIAL_REQUEST",
        "price_amendment_request",
    )
    transmitted = _transmitted_threshold_from_state(state)
    gc_plan = _decision_option_from_history(
        state.histories.get("decision_history", []),
        "S01_GC_PROCUREMENT_PLAN",
    )
    supplier_replaced = gc_plan == "replace_supplier"
    payoff = state.canonical_state.get("payoff_ledger", {})
    supplier_payoff = (payoff.get("realized_payoff_by_organization") or {}).get("steel_supplier")
    approved_relief = _payoff_event_amount(
        payoff.get("payoff_events", []),
        organization_id="steel_supplier",
        term_id="approved_price_relief",
    )
    buyer_surplus = 0 if supplier_replaced else true_threshold - approved_relief
    completion_success = bool((payoff.get("project_welfare") or {}).get("completion_success"))
    return {
        "instance_id": state.canonical_state["scenario"]["scenario_instance"]["instance_id"],
        "response_curve_level": treatment["response_curve_level"],
        "handoff_protocol": treatment["handoff_protocol"],
        "handoff_condition": handoff_condition,
        "true_threshold_usd": true_threshold,
        "gc_computed_threshold_usd": computed,
        "transmitted_threshold_usd": transmitted,
        "maximum_safe_request_usd": safe_request,
        "supplier_request_usd": requested,
        "supplier_source_plan": _decision_option_from_history(
            state.histories.get("decision_history", []),
            "S01_SUPPLIER_SOURCE_PLAN",
        ),
        "supplier_replaced": supplier_replaced,
        "approved_price_relief_usd": approved_relief,
        "supplier_realized_payoff_usd": supplier_payoff,
        "buyer_surplus_vs_replacement_usd": buyer_surplus,
        "joint_surplus_proxy_usd": (
            buyer_surplus + int(supplier_payoff) if supplier_payoff is not None else None
        ),
        "mutually_viable_deal": (
            completion_success
            and not supplier_replaced
            and supplier_payoff is not None
            and int(supplier_payoff) >= 0
            and buyer_surplus >= 0
        ),
        "handoff_record_exposed": transmitted is not None,
        "run_valid": state.run_valid,
        "terminal_status": state.terminal_status,
    }


def analyze_handoff_summaries(
    summaries: list[dict[str, Any]],
    *,
    reference_summaries: list[dict[str, Any]],
    handoff_condition: str | None = None,
) -> dict[str, Any]:
    references = {
        str(row["response_curve_level"]): row
        for row in reference_summaries
        if row["relationship_history_condition"] == "no_prior_shared_project_history"
    }
    rows = [
        handoff_summary_row(
            summary,
            reference=references[
                str(
                    summary["run_manifest"]["scenario"]["scenario_instance_treatment"][
                        "response_curve_level"
                    ]
                )
            ],
            handoff_condition=handoff_condition,
        )
        for summary in summaries
    ]
    valid = [row for row in rows if row["run_valid"]]
    transmitted = [row for row in valid if row["transmitted_threshold_usd"] is not None]
    consistent = [row for row in transmitted if row["message_action_consistent"] is not None]
    return {
        "schema_version": "constructbench.handoff_analysis.v1",
        "experiment_id": HANDOFF_EXPERIMENT_ID,
        "run_count": len(rows),
        "valid_run_count": len(valid),
        "invalid_run_count": len(rows) - len(valid),
        "valid_rate": len(valid) / len(rows) if rows else 0.0,
        "first_pass_valid_rate": _rate(
            row["run_valid"] and row["repair_attempt_count"] == 0 for row in rows
        ),
        "exact_gc_calculation_itt_rate": _rate(
            row["run_valid"] and row["gc_calculation_exact"] for row in rows
        ),
        "exact_threshold_transmission_itt_rate": _rate(
            row["run_valid"] and row["threshold_transmission_exact"] is True for row in rows
        ),
        "safe_action_itt_rate": _rate(
            row["run_valid"] and row["safe_action_relative_to_truth"] is True for row in rows
        ),
        "end_to_end_success_rate": _rate(row["end_to_end_success"] for row in rows),
        "threshold_transmission_rate": len(transmitted) / len(valid) if valid else None,
        "exact_gc_calculation_rate": _rate(row["gc_calculation_exact"] for row in valid),
        "exact_threshold_transmission_rate": _rate(
            row["threshold_transmission_exact"] for row in transmitted
        ),
        "mean_threshold_transmission_error_usd": _mean(
            row["threshold_transmission_error_usd"] for row in transmitted
        ),
        "mutually_viable_deal_rate": _rate(row["mutually_viable_deal"] for row in valid),
        "replacement_rate": _rate(row["supplier_replaced"] for row in valid),
        "mean_supplier_attainable_regret_usd": _mean(
            row["supplier_attainable_regret_usd"] for row in valid
        ),
        "mean_request_error_usd": _mean(row["request_error_usd"] for row in valid),
        "message_action_consistency_rate": _rate(
            row["message_action_consistent"] for row in consistent
        ),
        "total_model_cost_usd": round(sum(float(row["model_cost_usd"]) for row in rows), 6),
        "rows": rows,
    }


def handoff_summary_row(
    summary: dict[str, Any],
    *,
    reference: dict[str, Any],
    handoff_condition: str | None = None,
) -> dict[str, Any]:
    base = analysis_row(summary)
    treatment = summary["run_manifest"]["scenario"]["scenario_instance_treatment"]
    decisions = summary.get("decision_history", [])
    true_threshold = int(reference["replacement_threshold_usd"])
    safe_request = int(reference["maximum_safe_relief_usd"])
    best_payoff = int(reference["best_response_payoff_usd"])
    computed = _decision_parameter_from_history(
        decisions, HANDOFF_NODE_ID, "computed_threshold_usd"
    )
    share = _decision_parameter_from_history(decisions, HANDOFF_NODE_ID, "share_with_supplier")
    transmitted = (
        computed
        if treatment["handoff_protocol"] in {"structured_numeric", "rendered_prose"}
        and share is True
        else None
    )
    requested = _decision_parameter_from_history(
        decisions,
        "S01_SUPPLIER_COMMERCIAL_REQUEST",
        "price_amendment_request",
    )
    source_plan = _decision_option_from_history(decisions, "S01_SUPPLIER_SOURCE_PLAN")
    realized = base["focal_realized_utility"]
    supplier_regret = max(0, best_payoff - int(realized)) if realized is not None else None
    completion_success = bool(base["completion_success"])
    supplier_replaced = bool(base["switch_decision"])
    payoff = summary.get("payoff_ledger", {})
    approved_relief = _payoff_event_amount(
        payoff.get("payoff_events", []),
        organization_id="steel_supplier",
        term_id="approved_price_relief",
    )
    buyer_surplus = 0 if supplier_replaced else true_threshold - approved_relief
    repair_attempt_count = int(summary.get("repair_summary", {}).get("attempt_count", 0) or 0)
    safe_action = (
        int(requested) <= true_threshold and source_plan == "current_expedited"
        if requested is not None
        else None
    )
    viable = (
        completion_success
        and not supplier_replaced
        and realized is not None
        and int(realized) >= 0
        and buyer_surplus >= 0
    )
    gc_calculation_exact = computed == true_threshold
    transfer_exact = transmitted == true_threshold if transmitted is not None else None
    end_to_end_success = bool(
        base["run_valid"]
        and gc_calculation_exact
        and transfer_exact is True
        and safe_action is True
        and viable
    )
    return {
        "run_id": summary.get("run_id"),
        "instance_id": summary["run_manifest"]["scenario"].get("scenario_instance_id"),
        "handoff_condition": handoff_condition,
        "response_curve_level": treatment["response_curve_level"],
        "handoff_protocol": treatment["handoff_protocol"],
        "true_threshold_usd": true_threshold,
        "gc_computed_threshold_usd": computed,
        "gc_calculation_exact": gc_calculation_exact,
        "share_with_supplier": share,
        "handoff_record_exposed": transmitted is not None,
        "transmitted_threshold_usd": transmitted,
        "threshold_transmission_exact": transfer_exact,
        "threshold_transmission_error_usd": (
            abs(int(transmitted) - true_threshold) if transmitted is not None else None
        ),
        "maximum_safe_request_usd": safe_request,
        "supplier_request_usd": requested,
        "supplier_source_plan": source_plan,
        "request_error_usd": (
            abs(int(requested) - safe_request) if requested is not None else None
        ),
        "message_action_consistent": (
            int(requested) <= int(transmitted)
            if requested is not None and transmitted is not None
            else None
        ),
        "safe_action_relative_to_truth": safe_action,
        "supplier_replaced": supplier_replaced,
        "supplier_realized_payoff_usd": realized,
        "supplier_attainable_regret_usd": supplier_regret,
        "approved_price_relief_usd": approved_relief,
        "buyer_surplus_vs_replacement_usd": buyer_surplus,
        "joint_surplus_proxy_usd": (
            buyer_surplus + int(realized) if realized is not None else None
        ),
        "mutually_viable_deal": viable,
        "end_to_end_success": end_to_end_success,
        "run_valid": bool(base["run_valid"]),
        "terminal_status": base["terminal_status"],
        "terminal_reason": base["terminal_reason"],
        "model_call_count": base["model_call_count"],
        "model_cost_usd": base["model_cost_usd"],
        "repair_attempt_count": repair_attempt_count,
        "replicate_index": summary.get("run_manifest", {}).get("run", {}).get("seed"),
    }


def _replacement_threshold_from_state(state: RunState) -> int:
    scenario = state.canonical_state["scenario"]
    instance = scenario["scenario_instance"]
    start = scenario["scenario_start"]
    outside = instance["outside_option"]
    params = start["project_parameters"]
    contract_tick = 14
    replacement_tick = contract_tick + int(params["replacement_supplier_lead_time_ticks"])
    delay = max(0, replacement_tick - contract_tick)
    overhead = int(params["project_delay_overhead_per_tick"])
    return (
        int(params["replacement_supplier_cost"])
        + int(outside["termination_cost"])
        + delay * overhead
        + int(float(outside["delivery_risk"]) * 4 * overhead)
    )


def _maximum_safe_request_from_state(state: RunState, threshold: int) -> int:
    allowed = state.canonical_state["scenario"]["scenario_start"]["owner"]["price_relief_options"]
    return max(int(value) for value in allowed if int(value) <= threshold)


def _transmitted_threshold_from_state(state: RunState) -> int | None:
    treatment = state.canonical_state["scenario"]["scenario_instance"]["treatment"]
    decisions = state.histories.get("decision_history", [])
    computed = _decision_parameter_from_history(
        decisions, HANDOFF_NODE_ID, "computed_threshold_usd"
    )
    shared = _decision_parameter_from_history(decisions, HANDOFF_NODE_ID, "share_with_supplier")
    if treatment["handoff_protocol"] in {"structured_numeric", "rendered_prose"} and shared is True:
        return computed
    return None


def _decision_parameter_from_history(
    decisions: list[dict[str, Any]],
    node_id: str,
    parameter_name: str,
) -> Any:
    for record in decisions:
        if record.get("node_id") == node_id:
            return record.get("parameters", {}).get(parameter_name)
    return None


def _decision_option_from_history(decisions: list[dict[str, Any]], node_id: str) -> str | None:
    for record in decisions:
        if record.get("node_id") == node_id:
            return record.get("option_id")
    return None


def _payoff_event_amount(
    events: list[dict[str, Any]],
    *,
    organization_id: str,
    term_id: str,
) -> int:
    return sum(
        int(event.get("amount", 0) or 0)
        for event in events
        if event.get("organization_id") == organization_id and event.get("term_id") == term_id
    )


def _allowed_values(request: DecisionRequest, name: str) -> list[int]:
    if name in request.parameters:
        return [int(value) for value in request.parameters[name]]
    spec = request.parameter_specs.get(name)
    if spec is not None and spec.allowed_values:
        return [int(value) for value in spec.allowed_values]
    raise ValueError(f"decision request is missing allowed values for {name}")


def _private_facts(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        if fact.get("source") == "private" and isinstance(fact.get("private_facts"), dict):
            return fact["private_facts"]
    raise ValueError(f"private facts missing for {observation.agent_id}")


def _rate(values: Any) -> float | None:
    concrete = [bool(value) for value in values if value is not None]
    return sum(1 for value in concrete if value) / len(concrete) if concrete else None


def _mean(values: Any) -> float | None:
    concrete = [float(value) for value in values if value is not None]
    return sum(concrete) / len(concrete) if concrete else None
