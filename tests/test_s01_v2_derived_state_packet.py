from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from constructbench.runner import run_policy
from constructbench.s01_v2_derived_state_packet import (
    B1_NODE_ID,
    B2_NODE_ID,
    CONTROL_CONDITION,
    PACKET_SOURCE,
    TREATMENT_CONDITION,
    DerivedStatePacketPolicy,
    aggregate_study_rows,
    build_derived_state_packet,
    build_study_policies,
    packetized_deterministic_policies,
    study_run_row,
)
from constructbench.s01_v2_ladder import (
    StateAwareEfficientPolicy,
    deterministic_background_policies,
)
from constructbench.scenarios import SCENARIOS
from constructbench.state import AgentObservation, AgentSubmission


def _modal_decisions() -> dict[str, tuple[str, dict[str, Any]]]:
    decisions = deepcopy(
        SCENARIOS["S01_V2"].fixtures["efficient_phased_coalition_success"]["decisions"]
    )
    _, a1 = decisions["S01_A1_SUPPLIER_APPLICATION"]
    a1["payment_requested_usd"] = 1_800_000
    _, a2 = decisions["S01_A2_GC_INITIAL_REVIEW"]
    a2.update(
        {
            "provisional_certified_value_usd": 1_800_000,
            "backup_action": "RESERVE",
            "gc_bridge_ceiling_usd": 300_000,
            "owner_lender_package_document_ids": [
                "DOC_LOT_A_INVOICE",
                "DOC_LOT_A_TITLE",
                "DOC_LOT_A_INSURANCE",
                "DOC_LOT_A_QC",
            ],
            "inspector_package_document_ids": [
                "DOC_LOT_A_INVOICE",
                "DOC_LOT_A_TITLE",
                "DOC_LOT_A_INSURANCE",
                "DOC_LOT_A_QC",
            ],
        }
    )
    _, b1 = decisions[B1_NODE_ID]
    b1.update(
        {
            "cure_plan": "LOT_A_CURE",
            "supplier_cash_committed_usd": 350_000,
            "outside_financing_usd": 300_000,
            "outside_work_action": "ACCEPT_PARTIAL",
            "lot_b_commitment_tick": 20,
        }
    )
    _, b2 = decisions[B2_NODE_ID]
    b2.update(
        {
            "backup_action": "MAINTAIN",
            "gc_bridge_usd": 300_000,
            "owner_funds_requested_usd": 100_000,
        }
    )
    return decisions


def _run_modal(*, packetized: bool) -> Any:
    decisions = _modal_decisions()
    policies = deterministic_background_policies()
    supplier = StateAwareEfficientPolicy(decisions)
    gc = StateAwareEfficientPolicy(decisions)
    policies["steel_supplier"] = DerivedStatePacketPolicy(supplier) if packetized else supplier
    policies["gc"] = DerivedStatePacketPolicy(gc) if packetized else gc
    return run_policy("S01_V2", "normal", policies)


def _packets(result: Any) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    found: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for observation in result.final_state.histories["agent_observation_history"]:
        packets = [
            fact for fact in observation["known_facts"] if fact.get("source") == PACKET_SOURCE
        ]
        if packets:
            found[observation["phase_id"]] = (observation, packets[0])
    return found


def _ledger(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["item_id"]: item for item in packet["source_ledger"]}


def _measures(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["measure_id"]: item for item in packet["measures"]}


def test_modal_packets_restate_exact_authorized_b1_and_b2_values() -> None:
    result = _run_modal(packetized=True)
    packets = _packets(result)
    assert set(packets) == {B1_NODE_ID, B2_NODE_ID}

    b1 = _ledger(packets[B1_NODE_ID][1])
    b1_measures = _measures(packets[B1_NODE_ID][1])
    assert b1["document_supported_value"]["value_usd"] == 950_000
    assert b1["application_request"]["value_usd"] == 1_800_000
    assert b1["provisional_certification"]["value_usd"] == 1_800_000
    assert b1["lot_a_cash_threshold"]["value_usd"] == 300_000
    assert b1["full_sequence_cash_threshold"]["value_usd"] == 1_150_000
    assert b1["supplier_unrestricted_cash"]["value_usd"] == 350_000
    assert b1["outside_financing_capacity"]["value_usd"] == 450_000
    assert b1["gc_bridge_ceiling"]["value_usd"] == 300_000
    assert b1["owner_funding_ceiling"]["value_usd"] == 250_000
    assert b1["owner_equity_ceiling"]["value_usd"] == 100_000
    assert b1["lender_draw_operative_ceiling"]["value_usd"] == 760_000
    assert b1["external_support_released"]["value_usd"] == 0
    assert b1_measures["supplier_controlled_ceiling"]["value_usd"] == 800_000
    assert b1_measures["conditional_counterparty_ceiling"]["value_usd"] == 1_410_000
    assert b1_measures["all_visible_source_ceiling"]["value_usd"] == 2_210_000
    assert b1_measures["full_sequence_gap_to_supplier_controlled"]["value_usd"] == 350_000
    assert b1_measures["full_sequence_gap_to_all_visible"]["value_usd"] == 0
    assert b1_measures["all_visible_headroom_over_full_sequence"]["value_usd"] == 1_060_000
    assert b1_measures["request_minus_verified_value"]["value_usd"] == 850_000

    b2 = _ledger(packets[B2_NODE_ID][1])
    b2_measures = _measures(packets[B2_NODE_ID][1])
    assert b2["supplier_cash_commitment"]["value_usd"] == 350_000
    assert b2["supplier_outside_financing_commitment"]["value_usd"] == 300_000
    assert b2["final_certification_cap"]["value_usd"] == 950_000
    assert b2["lender_draw_request_cap"]["value_usd"] == 760_000
    assert b2["gc_bridge_cap"]["value_usd"] == 300_000
    assert b2["owner_funds_request_cap"]["value_usd"] == 250_000
    assert b2["owner_equity_ceiling"]["value_usd"] == 100_000
    assert b2_measures["supplier_structured_commitment"]["value_usd"] == 650_000
    assert b2_measures["hard_current_total"]["value_usd"] == 650_000
    assert b2_measures["gc_selectable_external_ceiling"]["value_usd"] == 1_310_000
    assert b2_measures["all_visible_provisional_ceiling"]["value_usd"] == 1_410_000


def test_packet_provenance_values_resolve_from_the_same_observation() -> None:
    for observation, packet in _packets(_run_modal(packetized=True)).values():
        for item in packet["source_ledger"]:
            for reference in item["provenance"]:
                assert _resolve(reference, observation) == reference["source_value"]


def test_packet_is_neutral_role_scoped_and_contains_no_hidden_state() -> None:
    packets = _packets(_run_modal(packetized=True))
    for _, packet in packets.values():
        assert {
            item["status"] for item in packet["source_ledger"]
        } <= set(packet["status_legend"])
    supplier = json.dumps(packets[B1_NODE_ID][1], sort_keys=True).lower()
    gc = json.dumps(packets[B2_NODE_ID][1], sort_keys=True).lower()
    for forbidden in [
        "recommended",
        "optimal",
        "should",
        "safe choice",
        "fixture",
        "true_completed_value",
        "documented_value_usd",
        "title_transferable_value_usd",
    ]:
        assert forbidden not in supplier
        assert forbidden not in gc
    assert "backup_activation_cost" not in supplier
    assert "project_delay_cost" not in supplier
    assert "cash_required_to_ready" not in gc
    assert "full_sequence_cash_threshold" not in gc
    assert "supplier_private_cash_threshold" in gc
    assert "not_disclosed_to_this_recipient" in gc


def test_packet_attachment_is_limited_idempotent_and_persisted_in_summary() -> None:
    result = _run_modal(packetized=True)
    observations = result.final_state.histories["agent_observation_history"]
    packet_counts = {
        observation["phase_id"]: sum(
            fact.get("source") == PACKET_SOURCE for fact in observation["known_facts"]
        )
        for observation in observations
    }
    assert packet_counts[B1_NODE_ID] == 1
    assert packet_counts[B2_NODE_ID] == 1
    assert sum(packet_counts.values()) == 2
    exposures = result.final_state.canonical_state["s01_v2_state"]["analysis"][
        "observation_intervention_exposures"
    ]
    assert {(row["agent_id"], row["phase_id"]) for row in exposures} == {
        ("steel_supplier", B1_NODE_ID),
        ("gc", B2_NODE_ID),
    }
    assert all(row["hash_matches"] is True for row in exposures)

    observation = AgentObservation.model_validate(_packets(result)[B1_NODE_ID][0])
    delegate = StateAwareEfficientPolicy(_modal_decisions())
    wrapper = DerivedStatePacketPolicy(delegate)
    first_hash = wrapper.decide(observation)
    repaired = wrapper.repair(observation, ["synthetic repair"])
    assert first_hash.decisions == repaired.decisions
    assert sum(fact.get("source") == PACKET_SOURCE for fact in observation.known_facts) == 1


def test_control_and_treatment_observations_differ_only_by_declared_packets() -> None:
    control = _run_modal(packetized=False)
    treatment = _run_modal(packetized=True)
    control_observations = control.final_state.histories["agent_observation_history"]
    treatment_observations = treatment.final_state.histories["agent_observation_history"]
    assert len(control_observations) == len(treatment_observations)
    for left, right in zip(control_observations, treatment_observations, strict=True):
        left = deepcopy(left)
        stripped = deepcopy(right)
        left.pop("run_id")
        stripped.pop("run_id")
        stripped["known_facts"] = [
            fact for fact in stripped["known_facts"] if fact.get("source") != PACKET_SOURCE
        ]
        assert left == stripped
    assert control.final_state.decisions == treatment.final_state.decisions
    assert control.final_state.terminal_status == treatment.final_state.terminal_status
    assert (
        control.final_state.canonical_state["project"]["project_cost"]
        == treatment.final_state.canonical_state["project"]["project_cost"]
    )


def test_packet_hash_is_fact_order_invariant_and_missing_inputs_are_unavailable() -> None:
    observation_dict = _packets(_run_modal(packetized=True))[B1_NODE_ID][0]
    clean = deepcopy(observation_dict)
    clean["known_facts"] = [
        fact for fact in clean["known_facts"] if fact.get("source") != PACKET_SOURCE
    ]
    observation = AgentObservation.model_validate(clean)
    reversed_observation = observation.model_copy(deep=True)
    reversed_observation.known_facts.reverse()
    assert build_derived_state_packet(observation) == build_derived_state_packet(
        reversed_observation
    )

    missing = observation.model_copy(deep=True)
    for fact in missing.known_facts:
        if isinstance(fact.get("private_facts"), dict):
            fact["private_facts"].pop("cash_required_to_ready_full_sequence_usd")
    packet = build_derived_state_packet(missing)
    assert packet is not None
    ledger = _ledger(packet)
    measures = _measures(packet)
    assert ledger["full_sequence_cash_threshold"]["value_status"] == "unavailable"
    assert measures["full_sequence_gap_to_all_visible"]["value_status"] == "unavailable"


def test_full_and_lot_a_only_a2_routes_have_same_current_r1_value() -> None:
    lot_a = _run_modal(packetized=False)
    full_decisions = _modal_decisions()
    _, a2 = full_decisions["S01_A2_GC_INITIAL_REVIEW"]
    all_docs = list(
        SCENARIOS["S01_V2"].fixtures["efficient_phased_coalition_success"]["decisions"][
            "S01_A1_SUPPLIER_APPLICATION"
        ][1]["submitted_document_ids"]
    )
    a2["inspector_package_document_ids"] = all_docs
    a2["owner_lender_package_document_ids"] = all_docs
    policies = deterministic_background_policies()
    policies["steel_supplier"] = StateAwareEfficientPolicy(full_decisions)
    policies["gc"] = StateAwareEfficientPolicy(full_decisions)
    full = run_policy("S01_V2", "normal", policies)

    def eligible(result: Any) -> int:
        transition = next(
            row
            for row in result.final_state.histories["s01_v2_lineage_transition_history"]
            if row["phase_id"] == "S01_R1_VERIFY_AND_PUBLISH"
        )
        return int(transition["eligible_stored_value_usd"])

    assert eligible(lot_a) == eligible(full) == 950_000


def test_study_policy_assignment_and_aggregate_advancement_are_explicit() -> None:
    created: list[str] = []

    class Empty:
        def decide(self, observation: AgentObservation) -> AgentSubmission:
            return AgentSubmission()

    policies = build_study_policies(
        TREATMENT_CONDITION,
        lambda agent_id: created.append(agent_id) or Empty(),
    )
    assert created == ["gc", "steel_supplier"]
    assert isinstance(policies["gc"], DerivedStatePacketPolicy)
    assert isinstance(policies["steel_supplier"], DerivedStatePacketPolicy)
    control = build_study_policies(CONTROL_CONDITION, lambda agent_id: Empty())
    assert not isinstance(control["gc"], DerivedStatePacketPolicy)

    reference = run_policy("S01_V2", "normal", packetized_deterministic_policies())
    from constructbench.reporting import run_summary_payload

    summary = run_summary_payload(reference.final_state, initial_state=reference.initial_state)
    row = study_run_row(
        condition=TREATMENT_CONDITION,
        replicate_index=0,
        sequence_index=0,
        summary=summary,
    )
    assert row["packet_exposure_audit_passed"] is True
    rows = []
    for index in range(3):
        rows.append(
            {
                **row,
                "condition": CONTROL_CONDITION,
                "replicate_index": index,
                "sequence_index": index * 2,
                "joint_efficient_outcome": False,
                "packet_exposure_audit_passed": True,
                "packet_exposure_count": 0,
            }
        )
        rows.append(
            {
                **row,
                "condition": TREATMENT_CONDITION,
                "replicate_index": index,
                "sequence_index": index * 2 + 1,
            }
        )
    aggregate = aggregate_study_rows(rows)
    assert aggregate["advance_to_broader_confirmation"] is True


def _resolve(reference: dict[str, Any], observation: dict[str, Any]) -> Any:
    selector = reference["selector_type"]
    if selector == "known_fact":
        candidates = observation["known_facts"]
        if "source" in reference:
            candidates = [fact for fact in candidates if fact.get("source") == reference["source"]]
        if "node_id" in reference:
            candidates = [
                fact for fact in candidates if fact.get("node_id") == reference["node_id"]
            ]
        if "event_id" in reference:
            candidates = [
                fact for fact in candidates if fact.get("event_id") == reference["event_id"]
            ]
        value: Any = candidates[0]
    elif selector == "private_fact":
        value = next(
            fact["private_facts"]
            for fact in observation["known_facts"]
            if isinstance(fact.get("private_facts"), dict)
        )
    else:
        phase = next(
            fact
            for fact in observation["known_facts"]
            if fact.get("source") == "s01_v2_phase_contract"
        )
        if selector == "visible_decision":
            value = next(
                record
                for record in phase["visible_decisions"]
                if record["node_id"] == reference["producer_node_id"]
            )
        elif selector == "provisional_offer":
            value = next(
                offer
                for offer in phase["commitments"]["provisional_offers"]
                if offer["offer_id"] == reference["offer_id"]
            )
        elif selector == "decision_constraint":
            value = next(
                rule
                for rule in phase["decision_constraints"]["rules"]
                if rule["constraint_id"] == reference["constraint_id"]
            )
        else:
            raise AssertionError(f"unknown selector {selector}")
    for part in reference["path"]:
        value = value[part]
    return value
