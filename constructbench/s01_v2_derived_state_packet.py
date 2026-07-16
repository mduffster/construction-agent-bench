from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from math import floor
from typing import Any, Literal

from constructbench.agents import AgentPolicy
from constructbench.manifest import canonical_json_sha256
from constructbench.s01_v2_ladder import (
    LineageCorePolicy,
    default_live_policy_factory,
    deterministic_background_policies,
    efficient_background_policy,
)
from constructbench.scenarios import SCENARIOS
from constructbench.state import AGENT_IDS, AgentObservation, AgentSubmission

DERIVED_STATE_PACKET_EXPERIMENT_ID = "s01_v2_supplier_gc_derived_state_packet_v1"
DERIVED_STATE_PACKET_SCHEMA_VERSION = "constructbench.s01_v2_derived_state_packet.v1"
CONTROL_CONDITION = "current_observation"
TREATMENT_CONDITION = "derived_state_packet"
PACKET_SOURCE = "harness_derived_decision_state"
B1_NODE_ID = "S01_B1_SUPPLIER_COMMITMENT"
B2_NODE_ID = "S01_B2_GC_INTEGRATED_PACKAGE"
PACKET_NODES_BY_AGENT = {
    "steel_supplier": B1_NODE_ID,
    "gc": B2_NODE_ID,
}
StudyCondition = Literal["current_observation", "derived_state_packet"]

_MISSING = object()
_RELEASE_FIELDS = (
    "lender_draw_released_usd",
    "owner_funds_usd",
    "owner_equity_usd",
    "gc_bridge_usd",
    "escrow_usd",
)
_FORBIDDEN_PACKET_TERMS = (
    "recommended",
    "optimal",
    "should",
    "safe choice",
    "fixture",
)

PACKET_CONTRACT = {
    "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
    "schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
    "source": PACKET_SOURCE,
    "recipient_nodes": PACKET_NODES_BY_AGENT,
    "authorized_input_only": True,
    "action_recommendation": False,
    "forbidden_terms": list(_FORBIDDEN_PACKET_TERMS),
}
DERIVED_STATE_PACKET_CONTRACT_HASH = canonical_json_sha256(PACKET_CONTRACT)


@dataclass
class DerivedStatePacketPolicy:
    """Attach the treatment fact before a delegated policy sees the observation.

    The original observation object is enriched deliberately. The runner records it
    after the policy call, making actual exposure auditable. Attachment is idempotent
    so a repair sees the identical packet once.
    """

    delegate: AgentPolicy

    def initialize(self, briefing: Any) -> None:
        if hasattr(self.delegate, "initialize"):
            self.delegate.initialize(briefing)  # type: ignore[attr-defined]

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        attach_derived_state_packet(observation)
        return self.delegate.decide(observation)

    def repair(
        self,
        observation: AgentObservation,
        errors: list[str],
    ) -> AgentSubmission:
        attach_derived_state_packet(observation)
        if hasattr(self.delegate, "repair"):
            return self.delegate.repair(observation, errors)  # type: ignore[attr-defined]
        return self.delegate.decide(observation)

    def drain_model_io(self) -> list[dict[str, Any]]:
        if hasattr(self.delegate, "drain_model_io"):
            return self.delegate.drain_model_io()  # type: ignore[attr-defined]
        return []


def build_derived_state_packet(
    observation: AgentObservation,
) -> dict[str, Any] | None:
    expected_node = PACKET_NODES_BY_AGENT.get(observation.agent_id)
    node_ids = {request.node_id for request in observation.required_decisions}
    if expected_node is None or expected_node not in node_ids:
        return None
    if expected_node == B1_NODE_ID:
        payload = _supplier_b1_packet(observation)
    else:
        payload = _gc_b2_packet(observation)
    payload["packet_hash"] = canonical_json_sha256(payload)
    return payload


def attach_derived_state_packet(
    observation: AgentObservation,
) -> dict[str, Any] | None:
    packet = build_derived_state_packet(observation)
    if packet is None:
        return None
    existing = [fact for fact in observation.known_facts if fact.get("source") == PACKET_SOURCE]
    if existing:
        if len(existing) != 1 or existing[0] != packet:
            raise RuntimeError("derived-state packet attachment is not idempotent")
        return existing[0]
    observation.known_facts.append(packet)
    return packet


def build_study_policies(
    condition: str,
    factory: Callable[[str], AgentPolicy] | None = None,
) -> dict[str, AgentPolicy]:
    _validate_condition(condition)
    packet_agents = PACKET_NODES_BY_AGENT if condition == TREATMENT_CONDITION else ()
    return build_packet_assignment_policies(packet_agents, factory)


def build_packet_assignment_policies(
    packet_agents: Collection[str],
    factory: Callable[[str], AgentPolicy] | None = None,
) -> dict[str, AgentPolicy]:
    """Build the supplier-GC study with packets assigned to declared recipients."""

    selected = set(packet_agents)
    unknown = selected - set(PACKET_NODES_BY_AGENT)
    if unknown:
        raise ValueError(f"unknown packet recipients: {sorted(unknown)}")
    live_factory = factory or default_live_policy_factory()
    policies: dict[str, AgentPolicy] = {}
    for agent_id in AGENT_IDS:
        if agent_id not in {"steel_supplier", "gc"}:
            policies[agent_id] = efficient_background_policy()
            continue
        live: AgentPolicy = LineageCorePolicy(live_factory(agent_id))
        policies[agent_id] = DerivedStatePacketPolicy(live) if agent_id in selected else live
    return policies


def packetized_deterministic_policies(
    packet_agents: Collection[str] = PACKET_NODES_BY_AGENT,
) -> dict[str, AgentPolicy]:
    selected = set(packet_agents)
    unknown = selected - set(PACKET_NODES_BY_AGENT)
    if unknown:
        raise ValueError(f"unknown packet recipients: {sorted(unknown)}")
    policies = deterministic_background_policies()
    for agent_id in selected:
        policies[agent_id] = DerivedStatePacketPolicy(policies[agent_id])
    return policies


def study_run_row(
    *,
    condition: str,
    replicate_index: int,
    sequence_index: int,
    summary: Mapping[str, Any],
    exposure_agents: Collection[str] | None = None,
) -> dict[str, Any]:
    if exposure_agents is None:
        _validate_condition(condition)
        selected_exposure_agents = (
            set(PACKET_NODES_BY_AGENT) if condition == TREATMENT_CONDITION else set()
        )
    else:
        selected_exposure_agents = set(exposure_agents)
        unknown = selected_exposure_agents - set(PACKET_NODES_BY_AGENT)
        if unknown:
            raise ValueError(f"unknown packet recipients: {sorted(unknown)}")
    decisions = {
        str(record.get("node_id")): dict(record.get("parameters", {}))
        for record in summary.get("decision_history", [])
    }
    transitions = {
        str(record.get("phase_id")): record
        for record in summary.get("s01_v2_lineage_transition_history", [])
    }
    analysis = summary.get("s01_v2_analysis", {})
    lineage = analysis.get("lineage", {}) if isinstance(analysis, Mapping) else {}
    b1 = decisions.get(B1_NODE_ID, {})
    b2 = decisions.get(B2_NODE_ID, {})
    c1 = decisions.get("S01_C1_SUPPLIER_STATUS_AND_RECOVERY", {})
    c2 = decisions.get("S01_C2_GC_RECOVERY_PLAN", {})
    r1 = transitions.get("S01_R1_VERIFY_AND_PUBLISH", {})
    r2 = transitions.get("S01_R2_COMMIT_AND_PRODUCE", {})
    gc_state = (
        summary.get("s01_v2_state", {}).get("gc_controls", {})
        if isinstance(summary.get("s01_v2_state", {}), Mapping)
        else {}
    )
    backup_activated = (
        gc_state.get("backup_status") == "ACTIVATED" or c2.get("recovery_plan") == "ACTIVATE_BACKUP"
    )
    coalition_success = analysis.get("coalition_success") is True
    exposures = list(analysis.get("observation_intervention_exposures", []) or [])
    expected_exposure_count = len(selected_exposure_agents)
    expected_exposure_sites = {
        (agent_id, PACKET_NODES_BY_AGENT[agent_id])
        for agent_id in selected_exposure_agents
    }
    actual_exposure_sites = {
        (str(record.get("agent_id")), str(record.get("phase_id"))) for record in exposures
    }
    packet_exposure_audit_passed = (
        len(exposures) == expected_exposure_count
        and (
            actual_exposure_sites == expected_exposure_sites
            if selected_exposure_agents
            else not actual_exposure_sites
        )
        and all(record.get("hash_matches") is True for record in exposures)
    )
    eligible = _int_or_none(r1.get("eligible_stored_value_usd"))
    certified = _int_or_none(b2.get("final_certified_payment_usd"))
    document_supported_certification = (
        eligible is not None and certified is not None and 0 <= certified <= eligible
    )
    model_totals = summary.get("model_usage_summary", {}).get("total", {})
    return {
        "condition": condition,
        "replicate_index": replicate_index,
        "sequence_index": sequence_index,
        "run_id": summary.get("run_id"),
        "run_valid": summary.get("run_valid") is True,
        "terminal_status": summary.get("terminal_status"),
        "project_success": analysis.get("project_success") is True,
        "coalition_success": coalition_success,
        "backup_activated": backup_activated,
        "joint_efficient_outcome": coalition_success and not backup_activated,
        "target_decision_pair": (
            b1.get("cure_plan") == "FULL_SEQUENCE_CURE" and b2.get("backup_action") == "DROP"
        ),
        "a1_payment_requested_usd": decisions.get("S01_A1_SUPPLIER_APPLICATION", {}).get(
            "payment_requested_usd"
        ),
        "a2_provisional_certified_value_usd": decisions.get("S01_A2_GC_INITIAL_REVIEW", {}).get(
            "provisional_certified_value_usd"
        ),
        "r1_eligible_stored_value_usd": eligible,
        "document_supported_certification": document_supported_certification,
        "b1_cure_plan": b1.get("cure_plan"),
        "b1_supplier_cash_committed_usd": b1.get("supplier_cash_committed_usd"),
        "b1_outside_financing_usd": b1.get("outside_financing_usd"),
        "b1_outside_work_action": b1.get("outside_work_action"),
        "b2_final_certified_payment_usd": certified,
        "b2_lender_draw_requested_usd": b2.get("lender_draw_requested_usd"),
        "b2_owner_funds_requested_usd": b2.get("owner_funds_requested_usd"),
        "b2_gc_bridge_usd": b2.get("gc_bridge_usd"),
        "b2_backup_action": b2.get("backup_action"),
        "r2_available_execution_funds_usd": r2.get("available_execution_funds_usd"),
        "r2_actual_lot_b_ready_tick": r2.get("actual_lot_b_ready_tick"),
        "r2_full_sequence_ready": r2.get("actual_lot_b_ready_tick") is not None,
        "c1_ship_action": c1.get("ship_action"),
        "c2_recovery_plan": c2.get("recovery_plan"),
        "final_project_cost": summary.get("final_project_cost"),
        "completion_tick": summary.get("completion_tick"),
        "cost_regret_usd": _difference(summary.get("final_project_cost"), 95_650_000),
        "completion_tick_regret": _difference(summary.get("completion_tick"), 41),
        "repair_attempt_count": int(summary.get("repair_summary", {}).get("attempt_count", 0) or 0),
        "lineage_complete": lineage.get("lineage_complete") is True,
        "lineage_viability_preserving": (lineage.get("viability_preserving_chain") is True),
        "lineage_exposure_rate": lineage.get("expected_exposure", {}).get("rate"),
        "lineage_action_realization_rate": lineage.get("action_realization", {}).get("rate"),
        "lineage_clip_count": lineage.get("clip_count"),
        "lineage_silent_clip_count": lineage.get("silent_clip_count"),
        "packet_exposure_count": len(exposures),
        "packet_exposure_audit_passed": packet_exposure_audit_passed,
        "packet_hashes": [record.get("packet_hash") for record in exposures],
        "earliest_reference_divergence": _earliest_reference_divergence(decisions),
        "model_call_count": int(model_totals.get("call_count", 0) or 0),
        "input_tokens": int(model_totals.get("input_tokens", 0) or 0),
        "output_tokens": int(model_totals.get("output_tokens", 0) or 0),
        "model_cost_usd": float(model_totals.get("cost_usd", 0.0) or 0.0),
    }


def aggregate_study_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, dict[str, Any]] = {}
    for condition in (CONTROL_CONDITION, TREATMENT_CONDITION):
        group = [row for row in rows if row.get("condition") == condition]
        n = len(group)
        by_condition[condition] = {
            "assigned_count": n,
            "valid_count": _count_true(group, "run_valid"),
            "valid_rate": _rate(group, "run_valid"),
            "project_success_count": _count_true(group, "project_success"),
            "coalition_success_count": _count_true(group, "coalition_success"),
            "coalition_success_rate": _rate(group, "coalition_success"),
            "backup_activation_count": _count_true(group, "backup_activated"),
            "backup_activation_rate": _rate(group, "backup_activated"),
            "joint_efficient_outcome_count": _count_true(group, "joint_efficient_outcome"),
            "joint_efficient_outcome_rate": _rate(group, "joint_efficient_outcome"),
            "target_decision_pair_count": _count_true(group, "target_decision_pair"),
            "full_sequence_cure_count": sum(
                row.get("b1_cure_plan") == "FULL_SEQUENCE_CURE" for row in group
            ),
            "backup_drop_count": sum(row.get("b2_backup_action") == "DROP" for row in group),
            "lot_b_ready_count": _count_true(group, "r2_full_sequence_ready"),
            "ship_both_count": sum(row.get("c1_ship_action") == "SHIP_BOTH" for row in group),
            "lineage_complete_count": _count_true(group, "lineage_complete"),
            "lineage_complete_rate": _rate(group, "lineage_complete"),
            "packet_exposure_audit_pass_count": _count_true(group, "packet_exposure_audit_passed"),
            "repair_attempt_count": sum(
                int(row.get("repair_attempt_count", 0) or 0) for row in group
            ),
            "mean_final_project_cost": _mean(group, "final_project_cost"),
            "mean_completion_tick": _mean(group, "completion_tick"),
            "model_cost_usd": round(
                sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in group),
                6,
            ),
        }
    control = by_condition[CONTROL_CONDITION]
    treatment = by_condition[TREATMENT_CONDITION]
    complete = len(rows) == 6 and all(
        by_condition[condition]["assigned_count"] == 3
        for condition in (CONTROL_CONDITION, TREATMENT_CONDITION)
    )
    advancement_checks = {
        "complete_three_per_arm": complete,
        "treatment_joint_outcome_strictly_higher": (
            treatment["joint_efficient_outcome_count"] > control["joint_efficient_outcome_count"]
        ),
        "treatment_valid_rate_not_lower": (
            treatment["valid_rate"] is not None
            and control["valid_rate"] is not None
            and treatment["valid_rate"] >= control["valid_rate"]
        ),
        "treatment_lineage_rate_not_lower": (
            treatment["lineage_complete_rate"] is not None
            and control["lineage_complete_rate"] is not None
            and treatment["lineage_complete_rate"] >= control["lineage_complete_rate"]
        ),
        "packet_exposure_audit_passed": all(
            row.get("packet_exposure_audit_passed") is True for row in rows
        ),
    }
    paired_periods = []
    for replicate_index in range(3):
        pair = [row for row in rows if row.get("replicate_index") == replicate_index]
        paired_periods.append(
            {
                "replicate_index": replicate_index,
                "sequence_indices": sorted(int(row["sequence_index"]) for row in pair),
                "control_joint_efficient_outcome": next(
                    (
                        row.get("joint_efficient_outcome")
                        for row in pair
                        if row.get("condition") == CONTROL_CONDITION
                    ),
                    None,
                ),
                "treatment_joint_efficient_outcome": next(
                    (
                        row.get("joint_efficient_outcome")
                        for row in pair
                        if row.get("condition") == TREATMENT_CONDITION
                    ),
                    None,
                ),
            }
        )
    return {
        "schema_version": "constructbench.s01_v2_derived_state_packet_analysis.v1",
        "experiment_id": DERIVED_STATE_PACKET_EXPERIMENT_ID,
        "claim_scope": "descriptive_scenario_specific_mechanism_result",
        "by_condition": by_condition,
        "paired_periods": paired_periods,
        "advancement_checks": advancement_checks,
        "advance_to_broader_confirmation": all(advancement_checks.values()),
    }


def _supplier_b1_packet(observation: AgentObservation) -> dict[str, Any]:
    phase = _phase_fact(observation, B1_NODE_ID)
    private = _private_facts(observation)
    baseline = _public_baseline(observation)
    a2 = _visible_decision(phase, "S01_A2_GC_INITIAL_REVIEW")
    owner = _offer(phase, "OWNER_PROVISIONAL_SUPPORT")
    lender = _offer(phase, "LENDER_PROVISIONAL_DRAW")
    payment = phase.get("payment", {})

    eligible = _path(payment, "eligible_stored_value_usd")
    requested = _path(payment, "requested_usd")
    provisional = _path(payment, "provisional_certified_usd")
    contract_cap = _path(baseline, "first_steel_sequence_contract_value_usd")
    lot_a_threshold = _path(private, "cash_required_to_ready_lot_a_usd")
    full_threshold = _path(private, "cash_required_to_ready_full_sequence_usd")
    cash = _path(private, "unrestricted_cash_usd")
    outside = _path(private, "maximum_outside_financing_usd")
    bridge = _path(a2, "gc_bridge_ceiling_usd")
    owner_funds = _path(owner, "funding_ceiling_usd")
    owner_equity = _path(owner, "equity_ceiling_usd")
    lender_max = _path(lender, "maximum_draw_usd")
    lender_rate = _path(lender, "advance_rate")
    draw_cap = _minimum_draw_cap(eligible, lender_max, lender_rate)
    released = _released_external_total(payment)
    supplier_ceiling = _sum_values(cash, outside)
    counterparty_ceiling = _sum_values(bridge, owner_funds, owner_equity, draw_cap)
    visible_ceiling = _sum_values(released, supplier_ceiling, counterparty_ceiling)

    ledger = [
        _source_item(
            "document_supported_value",
            "verified",
            eligible,
            [_phase_ref(B1_NODE_ID, ("payment", "eligible_stored_value_usd"), eligible)],
        ),
        _source_item(
            "application_request",
            "submitted_request",
            requested,
            [_phase_ref(B1_NODE_ID, ("payment", "requested_usd"), requested)],
        ),
        _source_item(
            "request_contract_cap",
            "public_contract_cap",
            contract_cap,
            _baseline_ref("first_steel_sequence_contract_value_usd", contract_cap),
        ),
        _source_item(
            "provisional_certification",
            "structured_provisional_amount",
            provisional,
            [_phase_ref(B1_NODE_ID, ("payment", "provisional_certified_usd"), provisional)],
        ),
        _source_item(
            "lot_a_cash_threshold",
            "recipient_private_threshold",
            lot_a_threshold,
            _private_ref("cash_required_to_ready_lot_a_usd", lot_a_threshold),
        ),
        _source_item(
            "full_sequence_cash_threshold",
            "recipient_private_threshold",
            full_threshold,
            _private_ref("cash_required_to_ready_full_sequence_usd", full_threshold),
        ),
        _source_item(
            "supplier_unrestricted_cash",
            "possessed",
            cash,
            _private_ref("unrestricted_cash_usd", cash),
        ),
        _source_item(
            "outside_financing_capacity",
            "available_not_committed",
            outside,
            _private_ref("maximum_outside_financing_usd", outside),
        ),
        _source_item(
            "gc_bridge_ceiling",
            "structured_provisional_ceiling",
            bridge,
            _decision_ref(B1_NODE_ID, "S01_A2_GC_INITIAL_REVIEW", "gc_bridge_ceiling_usd", bridge),
        ),
        _source_item(
            "owner_funding_ceiling",
            "structured_provisional_ceiling",
            owner_funds,
            _offer_ref(B1_NODE_ID, "OWNER_PROVISIONAL_SUPPORT", "funding_ceiling_usd", owner_funds),
        ),
        _source_item(
            "owner_equity_ceiling",
            "structured_provisional_ceiling",
            owner_equity,
            _offer_ref(B1_NODE_ID, "OWNER_PROVISIONAL_SUPPORT", "equity_ceiling_usd", owner_equity),
        ),
        _source_item(
            "lender_draw_operative_ceiling",
            "structured_provisional_ceiling",
            draw_cap,
            [
                _phase_ref(B1_NODE_ID, ("payment", "eligible_stored_value_usd"), eligible),
                _offer_ref(B1_NODE_ID, "LENDER_PROVISIONAL_DRAW", "maximum_draw_usd", lender_max)[
                    0
                ],
                _offer_ref(B1_NODE_ID, "LENDER_PROVISIONAL_DRAW", "advance_rate", lender_rate)[0],
            ],
        ),
        _source_item(
            "external_support_released",
            "released",
            released,
            [
                _phase_ref(B1_NODE_ID, ("payment", field), _path(payment, field))
                for field in _RELEASE_FIELDS
            ],
        ),
    ]
    measures = [
        _measure(
            "request_minus_verified_value",
            "subtract",
            _subtract(requested, eligible),
            ["application_request", "document_supported_value"],
        ),
        _measure(
            "provisional_minus_verified_value",
            "subtract",
            _subtract(provisional, eligible),
            ["provisional_certification", "document_supported_value"],
        ),
        _measure(
            "supplier_controlled_ceiling",
            "sum",
            supplier_ceiling,
            ["supplier_unrestricted_cash", "outside_financing_capacity"],
        ),
        _measure(
            "conditional_counterparty_ceiling",
            "sum",
            counterparty_ceiling,
            [
                "gc_bridge_ceiling",
                "owner_funding_ceiling",
                "owner_equity_ceiling",
                "lender_draw_operative_ceiling",
            ],
        ),
        _measure(
            "all_visible_source_ceiling",
            "sum",
            visible_ceiling,
            [
                "external_support_released",
                "supplier_controlled_ceiling",
                "conditional_counterparty_ceiling",
            ],
        ),
        _measure(
            "full_sequence_gap_to_supplier_controlled",
            "positive_gap",
            _positive_gap(full_threshold, supplier_ceiling),
            ["full_sequence_cash_threshold", "supplier_controlled_ceiling"],
        ),
        _measure(
            "full_sequence_gap_to_all_visible",
            "positive_gap",
            _positive_gap(full_threshold, visible_ceiling),
            ["full_sequence_cash_threshold", "all_visible_source_ceiling"],
        ),
        _measure(
            "all_visible_headroom_over_full_sequence",
            "positive_difference",
            _positive_gap(visible_ceiling, full_threshold),
            ["all_visible_source_ceiling", "full_sequence_cash_threshold"],
        ),
    ]
    return _packet_payload(
        observation,
        packet_id="S01_V2_SUPPLIER_B1_DERIVED_STATE",
        source_ledger=ledger,
        measures=measures,
        structured_context={
            "verified_value_source": "S01_V2_R1_INSPECTION_RECORD",
            "provisional_sources_are_not_released_cash": True,
        },
    )


def _gc_b2_packet(observation: AgentObservation) -> dict[str, Any]:
    phase = _phase_fact(observation, B2_NODE_ID)
    payment = phase.get("payment", {})
    b1 = _visible_decision(phase, B1_NODE_ID)
    owner = _offer(phase, "OWNER_PROVISIONAL_SUPPORT")
    bounds = _constraint(phase, "verified_value_and_draw_bounds")

    eligible = _path(payment, "eligible_stored_value_usd")
    requested = _path(payment, "requested_usd")
    provisional = _path(payment, "provisional_certified_usd")
    supplier_cash = _path(b1, "supplier_cash_committed_usd")
    supplier_finance = _path(b1, "outside_financing_usd")
    supplier_commitment = _sum_values(supplier_cash, supplier_finance)
    released = _released_external_total(payment)
    hard_current = _sum_values(supplier_commitment, released)
    cert_cap = _path(bounds, "maximum_final_certified_payment_usd")
    draw_cap = _path(bounds, "maximum_lender_draw_requested_usd")
    bridge_cap = _path(bounds, "maximum_gc_bridge_usd")
    owner_cap = _path(bounds, "maximum_owner_funds_requested_usd")
    owner_equity = _path(owner, "equity_ceiling_usd")
    selectable = _sum_values(draw_cap, bridge_cap, owner_cap)
    provisional_total = _sum_values(selectable, owner_equity)

    ledger = [
        _source_item(
            "document_supported_value",
            "verified",
            eligible,
            [_phase_ref(B2_NODE_ID, ("payment", "eligible_stored_value_usd"), eligible)],
        ),
        _source_item(
            "application_request",
            "submitted_request",
            requested,
            [_phase_ref(B2_NODE_ID, ("payment", "requested_usd"), requested)],
        ),
        _source_item(
            "provisional_certification",
            "structured_provisional_amount",
            provisional,
            [_phase_ref(B2_NODE_ID, ("payment", "provisional_certified_usd"), provisional)],
        ),
        _source_item(
            "final_certification_cap",
            "current_decision_operative_ceiling",
            cert_cap,
            _constraint_ref(
                "verified_value_and_draw_bounds", "maximum_final_certified_payment_usd", cert_cap
            ),
        ),
        _source_item(
            "supplier_cash_commitment",
            "structured_commitment",
            supplier_cash,
            _decision_ref(B2_NODE_ID, B1_NODE_ID, "supplier_cash_committed_usd", supplier_cash),
        ),
        _source_item(
            "supplier_outside_financing_commitment",
            "structured_commitment",
            supplier_finance,
            _decision_ref(B2_NODE_ID, B1_NODE_ID, "outside_financing_usd", supplier_finance),
        ),
        _source_item(
            "external_support_released",
            "released",
            released,
            [
                _phase_ref(B2_NODE_ID, ("payment", field), _path(payment, field))
                for field in _RELEASE_FIELDS
            ],
        ),
        _source_item(
            "lender_draw_request_cap",
            "current_decision_operative_ceiling",
            draw_cap,
            _constraint_ref(
                "verified_value_and_draw_bounds", "maximum_lender_draw_requested_usd", draw_cap
            ),
        ),
        _source_item(
            "gc_bridge_cap",
            "current_decision_operative_ceiling",
            bridge_cap,
            _constraint_ref("verified_value_and_draw_bounds", "maximum_gc_bridge_usd", bridge_cap),
        ),
        _source_item(
            "owner_funds_request_cap",
            "current_decision_operative_ceiling",
            owner_cap,
            _constraint_ref(
                "verified_value_and_draw_bounds", "maximum_owner_funds_requested_usd", owner_cap
            ),
        ),
        _source_item(
            "owner_equity_ceiling",
            "structured_provisional_ceiling_not_gc_selectable",
            owner_equity,
            _offer_ref(B2_NODE_ID, "OWNER_PROVISIONAL_SUPPORT", "equity_ceiling_usd", owner_equity),
        ),
    ]
    measures = [
        _measure(
            "request_minus_verified_value",
            "subtract",
            _subtract(requested, eligible),
            ["application_request", "document_supported_value"],
        ),
        _measure(
            "provisional_minus_verified_value",
            "subtract",
            _subtract(provisional, eligible),
            ["provisional_certification", "document_supported_value"],
        ),
        _measure(
            "supplier_structured_commitment",
            "sum",
            supplier_commitment,
            ["supplier_cash_commitment", "supplier_outside_financing_commitment"],
        ),
        _measure(
            "hard_current_total",
            "sum",
            hard_current,
            ["supplier_structured_commitment", "external_support_released"],
        ),
        _measure(
            "gc_selectable_external_ceiling",
            "sum",
            selectable,
            ["lender_draw_request_cap", "gc_bridge_cap", "owner_funds_request_cap"],
        ),
        _measure(
            "all_visible_provisional_ceiling",
            "sum",
            provisional_total,
            ["gc_selectable_external_ceiling", "owner_equity_ceiling"],
        ),
    ]
    return _packet_payload(
        observation,
        packet_id="S01_V2_GC_B2_DERIVED_STATE",
        source_ledger=ledger,
        measures=measures,
        structured_context={
            "supplier_cure_plan": b1.get("cure_plan"),
            "supplier_cure_plan_source": B1_NODE_ID,
            "supplier_private_cash_threshold": "not_disclosed_to_this_recipient",
            "provisional_sources_are_not_released_cash": True,
        },
    )


def _packet_payload(
    observation: AgentObservation,
    *,
    packet_id: str,
    source_ledger: list[dict[str, Any]],
    measures: list[dict[str, Any]],
    structured_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": PACKET_SOURCE,
        "schema_version": DERIVED_STATE_PACKET_SCHEMA_VERSION,
        "contract_hash": DERIVED_STATE_PACKET_CONTRACT_HASH,
        "packet_id": packet_id,
        "recipient_id": observation.agent_id,
        "node_id": PACKET_NODES_BY_AGENT[observation.agent_id],
        "summary": (
            "Arithmetic restatement of values already present in this recipient's "
            "current observation. Source status remains attached to every amount."
        ),
        "status_legend": {
            "verified": "amount in the published inspection and payment state",
            "submitted_request": "amount in the recorded application",
            "public_contract_cap": "public contract-value ceiling",
            "structured_provisional_amount": "recorded preliminary amount, not final release",
            "recipient_private_threshold": "recipient-authorized internal operating threshold",
            "possessed": "held by the recipient but not yet committed in this node",
            "available_not_committed": "available under a visible capacity, not selected",
            "structured_commitment": "amount stated in a prior structured decision",
            "structured_provisional_ceiling": "conditional offer ceiling, not released cash",
            "structured_provisional_ceiling_not_gc_selectable": (
                "conditional offer ceiling controlled by a later organization decision"
            ),
            "current_decision_operative_ceiling": "upper bound on a current decision field",
            "released": "amount shown as released in the current payment state",
        },
        "source_ledger": source_ledger,
        "measures": measures,
        "structured_context": structured_context,
        "visibility_basis": "current_recipient_observation",
        "action_recommendation": False,
    }


def _source_item(
    item_id: str,
    status: str,
    value: Any,
    provenance: list[dict[str, Any]],
) -> dict[str, Any]:
    known = value is not _MISSING
    return {
        "item_id": item_id,
        "status": status,
        "value_status": "known" if known else "unavailable",
        "value_usd": value if known else None,
        "provenance": provenance,
    }


def _measure(
    measure_id: str,
    operation: str,
    value: Any,
    input_refs: list[str],
) -> dict[str, Any]:
    known = value is not _MISSING
    return {
        "measure_id": measure_id,
        "operation": operation,
        "value_status": "known" if known else "unavailable",
        "value_usd": value if known else None,
        "input_refs": input_refs,
    }


def _phase_fact(observation: AgentObservation, node_id: str) -> dict[str, Any]:
    for fact in observation.known_facts:
        if fact.get("source") == "s01_v2_phase_contract" and fact.get("node_id") == node_id:
            return fact
    return {}


def _private_facts(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        private = fact.get("private_facts")
        if isinstance(private, dict):
            return private
    return {}


def _public_baseline(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        if fact.get("event_id") == "S01_V2_PUBLIC_BASELINE":
            return fact
    return {}


def _visible_decision(phase: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    for record in phase.get("visible_decisions", []) or []:
        if record.get("node_id") == node_id:
            return dict(record.get("parameters", {}))
    return {}


def _offer(phase: Mapping[str, Any], offer_id: str) -> dict[str, Any]:
    commitments = phase.get("commitments", {})
    if not isinstance(commitments, Mapping):
        return {}
    for offer in commitments.get("provisional_offers", []) or []:
        if offer.get("offer_id") == offer_id:
            return dict(offer)
    return {}


def _constraint(phase: Mapping[str, Any], constraint_id: str) -> dict[str, Any]:
    constraints = phase.get("decision_constraints", {})
    if not isinstance(constraints, Mapping):
        return {}
    for rule in constraints.get("rules", []) or []:
        if rule.get("constraint_id") == constraint_id:
            return dict(rule)
    return {}


def _path(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    if current is None or isinstance(current, bool) or not isinstance(current, (int, float)):
        return _MISSING
    return current


def _released_external_total(payment: Mapping[str, Any]) -> Any:
    return _sum_values(*(_path(payment, field) for field in _RELEASE_FIELDS))


def _minimum_draw_cap(eligible: Any, lender_max: Any, rate: Any) -> Any:
    if _MISSING in (eligible, lender_max, rate):
        return _MISSING
    return min(int(lender_max), floor(float(rate) * int(eligible)))


def _sum_values(*values: Any) -> Any:
    if any(value is _MISSING for value in values):
        return _MISSING
    return sum(int(value) for value in values)


def _subtract(left: Any, right: Any) -> Any:
    if _MISSING in (left, right):
        return _MISSING
    return int(left) - int(right)


def _positive_gap(required: Any, available: Any) -> Any:
    if _MISSING in (required, available):
        return _MISSING
    return max(0, int(required) - int(available))


def _phase_ref(node_id: str, path: tuple[str, ...], value: Any) -> dict[str, Any]:
    return {
        "selector_type": "known_fact",
        "source": "s01_v2_phase_contract",
        "node_id": node_id,
        "path": list(path),
        "source_value": None if value is _MISSING else value,
        "visibility_basis": "current_recipient_observation",
    }


def _private_ref(field: str, value: Any) -> list[dict[str, Any]]:
    return [
        {
            "selector_type": "private_fact",
            "path": [field],
            "source_value": None if value is _MISSING else value,
            "visibility_basis": "current_recipient_observation",
        }
    ]


def _baseline_ref(field: str, value: Any) -> list[dict[str, Any]]:
    return [
        {
            "selector_type": "known_fact",
            "event_id": "S01_V2_PUBLIC_BASELINE",
            "path": [field],
            "source_value": None if value is _MISSING else value,
            "visibility_basis": "current_recipient_observation",
        }
    ]


def _decision_ref(
    consumer_node: str,
    producer_node: str,
    field: str,
    value: Any,
) -> list[dict[str, Any]]:
    return [
        {
            "selector_type": "visible_decision",
            "consumer_node_id": consumer_node,
            "producer_node_id": producer_node,
            "path": ["parameters", field],
            "source_value": None if value is _MISSING else value,
            "visibility_basis": "current_recipient_observation",
        }
    ]


def _offer_ref(
    node_id: str,
    offer_id: str,
    field: str,
    value: Any,
) -> list[dict[str, Any]]:
    return [
        {
            "selector_type": "provisional_offer",
            "node_id": node_id,
            "offer_id": offer_id,
            "path": [field],
            "source_value": None if value is _MISSING else value,
            "visibility_basis": "current_recipient_observation",
        }
    ]


def _constraint_ref(
    constraint_id: str,
    field: str,
    value: Any,
) -> list[dict[str, Any]]:
    return [
        {
            "selector_type": "decision_constraint",
            "constraint_id": constraint_id,
            "path": [field],
            "source_value": None if value is _MISSING else value,
            "visibility_basis": "current_recipient_observation",
        }
    ]


def _validate_condition(condition: str) -> None:
    if condition not in {CONTROL_CONDITION, TREATMENT_CONDITION}:
        raise ValueError(f"unknown derived-state packet condition {condition!r}")


def _difference(value: Any, reference: int) -> int | None:
    return int(value) - reference if isinstance(value, int) else None


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _count_true(rows: list[dict[str, Any]], field: str) -> int:
    return sum(row.get(field) is True for row in rows)


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    return _count_true(rows, field) / len(rows) if rows else None


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return sum(values) / len(values) if values else None


def _earliest_reference_divergence(
    decisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    fixture = SCENARIOS["S01_V2"].fixtures["efficient_phased_coalition_success"]
    reference = {node_id: parameters for node_id, (_, parameters) in fixture["decisions"].items()}
    fields_by_node = {
        "S01_A1_SUPPLIER_APPLICATION": (
            "payment_requested_usd",
            "submitted_document_ids",
        ),
        "S01_A2_GC_INITIAL_REVIEW": (
            "review_strategy",
            "provisional_certified_value_usd",
            "backup_action",
            "preliminary_erection_strategy",
            "gc_bridge_ceiling_usd",
            "owner_lender_package_document_ids",
            "inspector_package_document_ids",
        ),
        B1_NODE_ID: (
            "cure_plan",
            "supplier_cash_committed_usd",
            "outside_financing_usd",
            "outside_work_action",
            "provisional_offer_actions",
            "requested_price_adjustment_usd",
            "lot_a_commitment_tick",
            "lot_b_commitment_tick",
        ),
        B2_NODE_ID: (
            "supplier_proposal_action",
            "final_certified_payment_usd",
            "gc_bridge_usd",
            "owner_funds_requested_usd",
            "lender_draw_requested_usd",
            "supplier_price_adjustment_usd",
            "backup_action",
        ),
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": (
            "ship_action",
            "supplier_recovery_spend_usd",
        ),
        "S01_C2_GC_RECOVERY_PLAN": (
            "recovery_plan",
            "supplemental_gc_bridge_usd",
        ),
    }
    for node_id, fields in fields_by_node.items():
        differences = [
            {
                "field": field,
                "expected": reference.get(node_id, {}).get(field),
                "actual": decisions.get(node_id, {}).get(field),
            }
            for field in fields
            if decisions.get(node_id, {}).get(field)
            != reference.get(node_id, {}).get(field)
        ]
        if differences:
            return {
                "node_id": node_id,
                "differences": differences,
            }
    return None
