from __future__ import annotations

from typing import Any

from constructbench.state import RunState


def build_s01_v2_lineage(state: RunState) -> dict[str, Any]:
    """Trace S01 V2 information and action flow without inferring exposure."""
    transitions = {
        row.get("phase_id"): row
        for row in state.histories.get("s01_v2_lineage_transition_history", [])
    }
    r1 = transitions.get("S01_R1_VERIFY_AND_PUBLISH", {})
    r2 = transitions.get("S01_R2_COMMIT_AND_PRODUCE", {})
    r3 = transitions.get("S01_R3_TERMINAL_RESOLUTION", {})
    decisions = {
        node_id: dict(record.get("parameters", {}))
        for node_id, record in state.decisions.items()
    }

    a1 = decisions.get("S01_A1_SUPPLIER_APPLICATION", {})
    a2 = decisions.get("S01_A2_GC_INITIAL_REVIEW", {})
    a3_inspector = decisions.get("S01_A3_INSPECTOR_REVIEW_PLAN", {})
    b1 = decisions.get("S01_B1_SUPPLIER_COMMITMENT", {})
    b2 = decisions.get("S01_B2_GC_INTEGRATED_PACKAGE", {})
    b3_inspector = decisions.get("S01_B3_INSPECTOR_DISPOSITION", {})
    b3_labor = decisions.get("S01_B3_ERECTOR_BINDING_COMMITMENT", {})
    b5 = decisions.get("S01_B5_LENDER_RELEASE_DECISION", {})
    c1 = decisions.get("S01_C1_SUPPLIER_STATUS_AND_RECOVERY", {})
    c3 = decisions.get("S01_C3_INSPECTOR_FINAL_DISPOSITION", {})
    c6 = decisions.get("S01_C6_ERECTOR_MOBILIZATION", {})

    submitted = set(a1.get("submitted_document_ids", []))
    inspector_route = set(a2.get("inspector_package_document_ids", []))
    owner_lender_route = set(a2.get("owner_lender_package_document_ids", []))
    consumed_inspector = set(r1.get("inspector_document_ids_consumed", []))
    consumed_owner_lender = set(r1.get("owner_lender_document_ids_consumed", []))
    e1_exposure = _decision_exposure(
        state,
        "S01_A2_GC_INITIAL_REVIEW",
        "S01_A1_SUPPLIER_APPLICATION",
        ["submitted_document_ids"],
    )
    e1_constraint = inspector_route <= submitted and owner_lender_route <= submitted
    e1_realized = (
        consumed_inspector == inspector_route
        and consumed_owner_lender == owner_lender_route
        and bool(r1)
    )
    e1 = _edge(
        edge_id="E1_DOCUMENTS_TO_GC_ROUTING",
        producer_refs=["S01_A1_SUPPLIER_APPLICATION"],
        producer_values={"submitted_document_ids": sorted(submitted)},
        consumer_ref="S01_A2_GC_INITIAL_REVIEW",
        exposure=e1_exposure,
        first_pass=_first_pass_validation(state, "S01_A2_GC_INITIAL_REVIEW"),
        action={
            "inspector_package_document_ids": sorted(inspector_route),
            "owner_lender_package_document_ids": sorted(owner_lender_route),
        },
        constraint_ids=["route_only_submitted_documents"],
        constraint_satisfied=e1_constraint,
        constraint_details={"both_routes_are_subsets": e1_constraint},
        realization_values={
            "inspector_document_ids_consumed": sorted(consumed_inspector),
            "owner_lender_document_ids_consumed": sorted(consumed_owner_lender),
        },
        realization_consistent=e1_realized,
        clip=_clip(False),
        information_consistent=e1_constraint,
        viability_preserving=bool(consumed_inspector),
    )

    e2_exposure = _decision_exposure(
        state,
        "S01_A3_INSPECTOR_REVIEW_PLAN",
        "S01_A2_GC_INITIAL_REVIEW",
        ["review_strategy", "inspector_package_document_ids"],
    )
    valid_ticks = {
        "DOCUMENT_ONLY": {12},
        "LOT_A_TARGETED": {12},
        "LOT_A_AND_SAMPLE_B": {13},
        "FULL_SEQUENCE": {13},
    }
    scope = a3_inspector.get("inspection_scope")
    scope_tick_valid = a3_inspector.get("inspection_tick") in valid_ticks.get(
        str(scope), set()
    )
    e2_realized = bool(r1) and r1.get("inspection_scope") == scope and r1.get(
        "inspection_tick"
    ) == a3_inspector.get("inspection_tick")
    physical_review_docs = {
        "DOC_LOT_A_INVOICE",
        "DOC_LOT_A_TITLE",
        "DOC_LOT_A_INSURANCE",
        "DOC_LOT_A_QC",
    }
    information_sufficient = scope == "DOCUMENT_ONLY" or physical_review_docs <= consumed_inspector
    e2 = _edge(
        edge_id="E2_GC_ROUTING_TO_INSPECTION_REVIEW",
        producer_refs=["S01_A2_GC_INITIAL_REVIEW"],
        producer_values={
            "review_strategy": a2.get("review_strategy"),
            "inspector_package_document_ids": sorted(inspector_route),
        },
        consumer_ref="S01_A3_INSPECTOR_REVIEW_PLAN",
        exposure=e2_exposure,
        first_pass=_first_pass_validation(
            state, "S01_A3_INSPECTOR_REVIEW_PLAN"
        ),
        action={
            "inspection_scope": scope,
            "inspection_tick": a3_inspector.get("inspection_tick"),
        },
        constraint_ids=["inspection_tick_by_scope"],
        constraint_satisfied=scope_tick_valid,
        constraint_details={
            "scope_tick_valid": scope_tick_valid,
            "routed_documents_support_physical_review": information_sufficient,
        },
        realization_values={
            "selected_scope": r1.get("inspection_scope"),
            "scheduled_tick": r1.get("inspection_tick"),
            "eligible_stored_value_usd": r1.get("eligible_stored_value_usd"),
        },
        realization_consistent=e2_realized,
        clip=_clip(False),
        information_consistent=information_sufficient,
        viability_preserving=int(r1.get("maximum_releasable_value_usd", 0)) > 0,
    )

    e3_exposure = _inspection_result_exposure(
        state, "S01_B3_INSPECTOR_DISPOSITION"
    )
    observed_bound = e3_exposure.get("observed_values", {}).get(
        "maximum_releasable_value_usd"
    )
    requested_release = int(b3_inspector.get("maximum_releasable_value_usd", 0))
    bound_satisfied = observed_bound is not None and requested_release <= int(
        observed_bound
    )
    realized_release = int(r2.get("maximum_releasable_value_usd", 0))
    initial_cap = int(r2.get("inspector_initial_release_cap_usd", 0))
    expansion_permitted = (
        realized_release <= initial_cap
        or (
            initial_cap >= 950_000
            and b3_inspector.get("reinspection_tick") is not None
            and r2.get("actual_lot_b_ready_tick") is not None
            and int(r2["actual_lot_b_ready_tick"])
            <= int(b3_inspector["reinspection_tick"])
        )
    )
    e3_realized = bool(r2) and expansion_permitted
    e3_clipped = requested_release > realized_release
    e3 = _edge(
        edge_id="E3_INSPECTION_RESULT_TO_RELEASABLE_VALUE",
        producer_refs=["S01_V2_R1_INSPECTION_RECORD"],
        producer_values={
            "maximum_releasable_value_usd": r1.get(
                "maximum_releasable_value_usd"
            ),
            "eligible_stored_value_usd": r1.get("eligible_stored_value_usd"),
        },
        consumer_ref="S01_B3_INSPECTOR_DISPOSITION",
        exposure=e3_exposure,
        first_pass=_first_pass_validation(state, "S01_B3_INSPECTOR_DISPOSITION"),
        action={
            "disposition": b3_inspector.get("disposition"),
            "maximum_releasable_value_usd": requested_release,
            "reinspection_tick": b3_inspector.get("reinspection_tick"),
        },
        constraint_ids=["inspector_verified_value_bound"],
        constraint_satisfied=bound_satisfied,
        constraint_details={
            "observed_bound_usd": observed_bound,
            "reinspection_expansion_permitted": expansion_permitted,
        },
        realization_values={
            "initial_inspector_cap_usd": initial_cap,
            "post_cure_releasable_value_usd": realized_release,
        },
        realization_consistent=e3_realized,
        clip=_clip(
            e3_clipped,
            amount=max(0, requested_release - realized_release),
            reason="READINESS_OR_CURE_NOT_SATISFIED",
            silent=False,
        ),
        information_consistent=bound_satisfied,
        viability_preserving=realized_release >= 950_000,
    )

    e4_exposure = _combined_exposure(
        state,
        "S01_B5_LENDER_RELEASE_DECISION",
        {
            "S01_A4_LENDER_PROVISIONAL_POSITION": [
                "maximum_draw_usd",
                "advance_rate",
            ],
            "S01_B2_GC_INTEGRATED_PACKAGE": [
                "final_certified_payment_usd",
                "lender_draw_requested_usd",
            ],
            "S01_B3_INSPECTOR_DISPOSITION": [
                "maximum_releasable_value_usd"
            ],
            "S01_B4_OWNER_PACKAGE_DECISION": [
                "package_action",
                "owner_funding_usd",
                "owner_equity_usd",
            ],
        },
        required_constraint_id="lender_supported_release",
    )
    draw_capacity = int(r2.get("primary_draw_capacity_usd", 0))
    requested_transfer = _requested_primary_transfer(b5)
    realized_transfer = int(r2.get("lender_draw_released_usd", 0)) + int(
        r2.get("controlled_escrow_released_usd", 0)
    )
    b2_bounds_hold = (
        int(b2.get("final_certified_payment_usd", 0))
        <= int(r1.get("eligible_stored_value_usd", 0))
        and requested_transfer <= draw_capacity
        and realized_transfer <= int(b2.get("lender_draw_requested_usd", 0))
        and draw_capacity <= requested_release
    )
    e4_clipped = requested_transfer > realized_transfer
    e4 = _edge(
        edge_id="E4_RELEASABLE_VALUE_TO_DRAW",
        producer_refs=[
            "S01_A4_LENDER_PROVISIONAL_POSITION",
            "S01_B2_GC_INTEGRATED_PACKAGE",
            "S01_B3_INSPECTOR_DISPOSITION",
            "S01_B4_OWNER_PACKAGE_DECISION",
        ],
        producer_values={
            "eligible_stored_value_usd": r1.get("eligible_stored_value_usd"),
            "inspector_release_cap_usd": requested_release,
            "gc_final_certified_payment_usd": b2.get(
                "final_certified_payment_usd"
            ),
            "gc_lender_draw_requested_usd": b2.get(
                "lender_draw_requested_usd"
            ),
        },
        consumer_ref="S01_B5_LENDER_RELEASE_DECISION",
        exposure=e4_exposure,
        first_pass=_first_pass_validation(state, "S01_B5_LENDER_RELEASE_DECISION"),
        action={
            "release_action": b5.get("release_action"),
            "requested_primary_transfer_usd": requested_transfer,
        },
        constraint_ids=[
            "verified_value_and_draw_bounds",
            "lender_supported_release",
        ],
        constraint_satisfied=b2_bounds_hold,
        constraint_details={"primary_draw_capacity_usd": draw_capacity},
        realization_values={
            "lender_draw_released_usd": r2.get("lender_draw_released_usd"),
            "controlled_escrow_released_usd": r2.get(
                "controlled_escrow_released_usd"
            ),
        },
        realization_consistent=bool(r2)
        and realized_transfer == requested_transfer,
        clip=_clip(
            e4_clipped,
            amount=max(0, requested_transfer - realized_transfer),
            reason=(
                "INCOMPATIBLE_PACKAGE"
                if r2 and not r2.get("compatible_package")
                else "OPERATIVE_DRAW_CAP"
            ),
            silent=e4_clipped and requested_transfer > draw_capacity,
        ),
        information_consistent=b2_bounds_hold,
        viability_preserving=realized_transfer > 0,
    )

    expected_readiness = _expected_readiness(b1, b3_inspector, r2)
    readiness_consistent = bool(r2) and all(
        r2.get(field) == expected_readiness[field]
        for field in [
            "actual_lot_a_ready_tick",
            "actual_lot_b_ready_tick",
            "maximum_releasable_value_usd",
        ]
    )
    funding_components = {
        key: r2.get(key)
        for key in [
            "lender_draw_released_usd",
            "controlled_escrow_released_usd",
            "owner_funds_usd",
            "owner_equity_usd",
            "gc_bridge_usd",
            "supplier_cash_committed_usd",
            "outside_financing_usd",
        ]
    }
    e5 = _edge(
        edge_id="E5_FUNDS_TO_READINESS",
        producer_refs=["S01_R2_COMMIT_AND_PRODUCE"],
        producer_values=funding_components,
        consumer_ref="HARNESS_R2_READINESS_TRANSITION",
        exposure=_non_agent_exposure(),
        first_pass=None,
        action={"cure_plan": b1.get("cure_plan")},
        constraint_ids=["funding_thresholds_to_readiness"],
        constraint_satisfied=readiness_consistent,
        constraint_details={
            "lot_a_threshold_usd": 300_000,
            "full_sequence_threshold_usd": 1_150_000,
            "available_execution_funds_usd": r2.get(
                "available_execution_funds_usd"
            ),
        },
        realization_values={
            field: r2.get(field)
            for field in [
                "actual_lot_a_ready_tick",
                "actual_lot_b_ready_tick",
                "maximum_releasable_value_usd",
            ]
        },
        realization_consistent=readiness_consistent,
        clip=_clip(False),
        information_consistent=readiness_consistent,
        viability_preserving=r2.get("actual_lot_a_ready_tick") is not None,
    )

    e6_exposure = _private_exposure(
        state,
        "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        "s01_v2_actual_readiness",
        ["actual_lot_a_ready_tick", "actual_lot_b_ready_tick"],
    )
    ready_lots = _ready_lots(r2)
    requested_lots = _requested_ship_lots(c1)
    ship_constraint = requested_lots <= ready_lots
    e6 = _edge(
        edge_id="E6_READINESS_TO_SUPPLIER_SHIPMENT_REQUEST",
        producer_refs=["S01_R2_COMMIT_AND_PRODUCE:private_readiness"],
        producer_values={
            "ready_lots": sorted(ready_lots),
            "actual_lot_a_ready_tick": r2.get("actual_lot_a_ready_tick"),
            "actual_lot_b_ready_tick": r2.get("actual_lot_b_ready_tick"),
        },
        consumer_ref="S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
        exposure=e6_exposure,
        first_pass=_first_pass_validation(
            state, "S01_C1_SUPPLIER_STATUS_AND_RECOVERY"
        ),
        action={
            "ship_action": c1.get("ship_action"),
        },
        constraint_ids=["ship_only_ready_lots"],
        constraint_satisfied=ship_constraint,
        constraint_details={"requested_lots": sorted(requested_lots)},
        realization_values={"accepted_shipment_request_lots": sorted(requested_lots)},
        realization_consistent=ship_constraint,
        clip=_clip(False),
        information_consistent=ship_constraint,
        viability_preserving="lot_a" in requested_lots,
    )

    e7_exposure = _combined_exposure(
        state,
        "S01_C6_ERECTOR_MOBILIZATION",
        {
            "S01_B3_ERECTOR_BINDING_COMMITMENT": [
                "capacity_commitment",
                "overtime_commitment",
            ],
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": ["ship_action"],
            "S01_C3_INSPECTOR_FINAL_DISPOSITION": [
                "lot_a_disposition",
                "lot_b_disposition",
                "approved_shipping_value_usd",
            ],
        },
        required_constraint_id="mobilization_within_binding_capacity",
    )
    effective_labor_commitment = {
        "capacity_commitment": r3.get("labor_binding_capacity"),
        "overtime_commitment": r3.get("labor_overtime_commitment"),
    }
    capacity_consistent = _labor_capacity_consistent(
        effective_labor_commitment,
        c6,
    )
    shipped_lots = {
        lot
        for lot in ["lot_a", "lot_b"]
        if r3.get(f"{lot}_shipped")
    }
    material_consistent = _mobilization_material_consistent(c6, shipped_lots)
    e7_realized = bool(r3) and capacity_consistent and not bool(
        r3.get("compliance_failure")
    )
    e7 = _edge(
        edge_id="E7_RELEASED_SHIPMENT_TO_LABOR_COMPLETION",
        producer_refs=[
            "S01_B3_ERECTOR_BINDING_COMMITMENT",
            "S01_C1_SUPPLIER_STATUS_AND_RECOVERY",
            "S01_C3_INSPECTOR_FINAL_DISPOSITION",
        ],
        producer_values={
            "requested_ship_lots": sorted(requested_lots),
            "approved_shipping_value_usd": c3.get(
                "approved_shipping_value_usd"
            ),
            "offered_binding_capacity": b3_labor.get("capacity_commitment"),
            "effective_binding_capacity": r3.get("labor_binding_capacity"),
        },
        consumer_ref="S01_C6_ERECTOR_MOBILIZATION",
        exposure=e7_exposure,
        first_pass=_first_pass_validation(state, "S01_C6_ERECTOR_MOBILIZATION"),
        action={
            "mobilization_action": c6.get("mobilization_action"),
            "mobilization_tick": c6.get("mobilization_tick"),
        },
        constraint_ids=["mobilization_within_binding_capacity"],
        constraint_satisfied=capacity_consistent,
        constraint_details={
            "material_available_for_selected_action": material_consistent
        },
        realization_values={
            "released_lots": sorted(
                lot
                for lot in ["lot_a", "lot_b"]
                if r3.get(f"{lot}_released")
            ),
            "shipped_lots": sorted(shipped_lots),
            "completion_tick": r3.get("completion_tick"),
            "compliance_failure": r3.get("compliance_failure"),
        },
        realization_consistent=e7_realized,
        clip=_clip(False),
        information_consistent=material_consistent,
        viability_preserving=bool(r3.get("project_success")),
    )

    edges = [e1, e2, e3, e4, e5, e6, e7]
    exposed_edges = [
        edge
        for edge in edges
        if edge["actual_exposure"]["expected"]
    ]
    first_pass_edges = [
        edge for edge in edges if edge["first_pass_validation"] is not None
    ]
    lineage_complete = all(edge["status"] == "COMPLETE" for edge in edges)
    viability_complete = all(edge["viability_preserving"] for edge in edges)
    return {
        "schema_version": "constructbench.s01_v2.lineage.v1",
        "edges": edges,
        "expected_exposure": _rate_summary(
            exposed_edges,
            lambda edge: edge["actual_exposure"]["complete"],
        ),
        "first_pass_submission_conformance": _rate_summary(
            first_pass_edges,
            lambda edge: bool(edge["first_pass_validation"]["valid"]),
        ),
        "operative_constraint_conformance": _rate_summary(
            edges,
            lambda edge: edge["operative_constraint"]["satisfied"],
        ),
        "action_realization": _rate_summary(
            edges,
            lambda edge: edge["realization"]["consistent"],
        ),
        "clip_count": sum(
            1 for edge in edges if edge["realization"]["clip"]["occurred"]
        ),
        "silent_unexplained_clamp_count": sum(
            1 for edge in edges if edge["realization"]["clip"]["silent"]
        ),
        "lineage_complete": lineage_complete,
        "earliest_failed_edge_id": next(
            (edge["edge_id"] for edge in edges if edge["status"] != "COMPLETE"),
            None,
        ),
        "viability_preserving_chain": viability_complete,
        "earliest_viability_break_edge_id": next(
            (
                edge["edge_id"]
                for edge in edges
                if not edge["viability_preserving"]
            ),
            None,
        ),
    }


def _edge(
    *,
    edge_id: str,
    producer_refs: list[str],
    producer_values: dict[str, Any],
    consumer_ref: str,
    exposure: dict[str, Any],
    first_pass: dict[str, Any] | None,
    action: dict[str, Any],
    constraint_ids: list[str],
    constraint_satisfied: bool,
    constraint_details: dict[str, Any],
    realization_values: dict[str, Any],
    realization_consistent: bool,
    clip: dict[str, Any],
    information_consistent: bool,
    viability_preserving: bool,
) -> dict[str, Any]:
    issue_codes: list[str] = []
    if exposure["expected"] and not exposure["complete"]:
        issue_codes.append("EXPECTED_EXPOSURE_MISSING")
    if not constraint_satisfied:
        issue_codes.append("OPERATIVE_CONSTRAINT_FAILED")
    if not realization_consistent:
        issue_codes.append("ACTION_NOT_REALIZED")
    if not information_consistent:
        issue_codes.append("INFORMATION_INCONSISTENT")
    complete = (
        (not exposure["expected"] or exposure["complete"])
        and constraint_satisfied
        and realization_consistent
    )
    return {
        "edge_id": edge_id,
        "producer_refs": producer_refs,
        "producer_values": producer_values,
        "consumer_ref": consumer_ref,
        "actual_exposure": exposure,
        "consumer_action": action,
        "first_pass_validation": first_pass,
        "operative_constraint": {
            "constraint_ids": constraint_ids,
            "satisfied": constraint_satisfied,
            "details": constraint_details,
        },
        "realization": {
            "values": realization_values,
            "consistent": realization_consistent,
            "clip": clip,
        },
        "information_consistent": information_consistent,
        "viability_preserving": viability_preserving,
        "issue_codes": issue_codes,
        "status": "COMPLETE" if complete else "FAILED",
    }


def _decision_exposure(
    state: RunState,
    consumer_node: str,
    producer_node: str,
    required_fields: list[str],
) -> dict[str, Any]:
    observation = _observation(state, consumer_node)
    observed: dict[str, Any] = {}
    if observation:
        for fact in observation.get("known_facts", []):
            for record in fact.get("visible_decisions", []):
                if record.get("node_id") == producer_node:
                    observed = {
                        field: record.get("parameters", {}).get(field)
                        for field in required_fields
                        if field in record.get("parameters", {})
                    }
                    break
    complete = bool(observation) and all(field in observed for field in required_fields)
    return {
        "expected": True,
        "authorized_by_contract": True,
        "observation_found": bool(observation),
        "required_fields": required_fields,
        "observed_values": observed,
        "complete": complete,
    }


def _combined_exposure(
    state: RunState,
    consumer_node: str,
    required_decisions: dict[str, list[str]],
    *,
    required_constraint_id: str,
) -> dict[str, Any]:
    observation = _observation(state, consumer_node)
    observed: dict[str, Any] = {}
    constraint_seen = False
    if observation:
        for fact in observation.get("known_facts", []):
            constraints = fact.get("decision_constraints", {})
            constraint_seen = constraint_seen or any(
                rule.get("constraint_id") == required_constraint_id
                for rule in constraints.get("rules", [])
            )
            for record in fact.get("visible_decisions", []):
                producer = record.get("node_id")
                if producer not in required_decisions:
                    continue
                params = record.get("parameters", {})
                observed[producer] = {
                    field: params.get(field)
                    for field in required_decisions[producer]
                    if field in params
                }
    decisions_complete = all(
        producer in observed
        and all(field in observed[producer] for field in fields)
        for producer, fields in required_decisions.items()
    )
    return {
        "expected": True,
        "authorized_by_contract": True,
        "observation_found": bool(observation),
        "required_fields": {
            "decisions": required_decisions,
            "constraint_id": required_constraint_id,
        },
        "observed_values": observed,
        "complete": bool(observation) and decisions_complete and constraint_seen,
    }


def _inspection_result_exposure(
    state: RunState,
    consumer_node: str,
) -> dict[str, Any]:
    observation = _observation(state, consumer_node)
    event_value = None
    bound_value = None
    if observation:
        for fact in observation.get("known_facts", []):
            if fact.get("event_id") == "S01_V2_R1_INSPECTION_RECORD":
                event_value = fact.get("maximum_releasable_value_usd")
            bounds = fact.get("decision_bounds", {}).get(consumer_node, {})
            if "maximum_releasable_value_usd" in bounds:
                bound_value = bounds["maximum_releasable_value_usd"]
    return {
        "expected": True,
        "authorized_by_contract": True,
        "observation_found": bool(observation),
        "required_fields": [
            "S01_V2_R1_INSPECTION_RECORD.maximum_releasable_value_usd",
            "decision_bounds.maximum_releasable_value_usd",
        ],
        "observed_values": {
            "event_maximum_releasable_value_usd": event_value,
            "maximum_releasable_value_usd": bound_value,
        },
        "complete": event_value is not None and bound_value is not None,
    }


def _private_exposure(
    state: RunState,
    consumer_node: str,
    private_key: str,
    required_fields: list[str],
) -> dict[str, Any]:
    observation = _observation(state, consumer_node)
    observed: dict[str, Any] = {}
    if observation:
        for fact in observation.get("known_facts", []):
            candidate = fact.get("private_facts", {}).get(private_key)
            if isinstance(candidate, dict):
                observed = {
                    field: candidate.get(field)
                    for field in required_fields
                    if field in candidate
                }
    return {
        "expected": True,
        "authorized_by_contract": True,
        "observation_found": bool(observation),
        "required_fields": required_fields,
        "observed_values": observed,
        "complete": bool(observation)
        and all(field in observed for field in required_fields),
    }


def _non_agent_exposure() -> dict[str, Any]:
    return {
        "expected": False,
        "authorized_by_contract": True,
        "observation_found": True,
        "required_fields": [],
        "observed_values": {},
        "complete": True,
    }


def _observation(state: RunState, node_id: str) -> dict[str, Any] | None:
    for observation in state.histories.get("agent_observation_history", []):
        if any(
            request.get("node_id") == node_id
            for request in observation.get("required_decisions", [])
        ):
            return observation
    return None


def _first_pass_validation(
    state: RunState,
    node_id: str,
) -> dict[str, Any] | None:
    observation = _observation(state, node_id)
    if observation is None:
        return None
    phase_index = observation.get("phase_index")
    agent_id = observation.get("agent_id")
    validation = next(
        (
            row
            for row in state.histories.get("validation_results", [])
            if row.get("phase_index") == phase_index
            and row.get("agent_id") == agent_id
        ),
        None,
    )
    repaired = any(
        row.get("phase_index") == phase_index and row.get("agent_id") == agent_id
        for row in state.histories.get("repair_attempts", [])
    )
    return {
        "valid": bool(validation and validation.get("valid")) and not repaired,
        "final_valid": bool(validation and validation.get("valid")),
        "repair_attempted": repaired,
    }


def _clip(
    occurred: bool,
    *,
    amount: int = 0,
    reason: str | None = None,
    silent: bool = False,
) -> dict[str, Any]:
    return {
        "occurred": occurred,
        "amount_usd": amount,
        "reason_code": reason if occurred else None,
        "silent": occurred and silent,
    }


def _requested_primary_transfer(lender: dict[str, Any]) -> int:
    if lender.get("release_action") in {"RELEASE", "PARTIAL_RELEASE"}:
        return int(lender.get("draw_release_usd", 0))
    if lender.get("release_action") == "ESCROW":
        return int(lender.get("escrow_release_usd", 0))
    return 0


def _expected_readiness(
    supplier: dict[str, Any],
    inspector: dict[str, Any],
    r2: dict[str, Any],
) -> dict[str, Any]:
    funds = int(r2.get("available_execution_funds_usd", 0))
    cure_plan = supplier.get("cure_plan")
    lot_a = None
    lot_b = None
    maximum_release = 0
    if (
        cure_plan in {"DOCUMENT_CURE", "LOT_A_CURE", "FULL_SEQUENCE_CURE"}
        and funds >= 300_000
    ):
        lot_a = min(int(supplier.get("lot_a_commitment_tick", 14)), 14)
        if inspector.get("disposition") != "NO_RELEASE":
            maximum_release = min(
                int(inspector.get("maximum_releasable_value_usd", 0)),
                950_000,
            )
    if cure_plan == "FULL_SEQUENCE_CURE" and funds >= 1_150_000:
        delay = {
            "DECLINE": 0,
            "ACCEPT_PARTIAL": 1,
            "ACCEPT_FULL": 3,
        }.get(str(supplier.get("outside_work_action")), 0)
        lot_b = int(supplier.get("lot_b_commitment_tick", 18)) + delay
        reinspection_tick = inspector.get("reinspection_tick")
        if (
            maximum_release >= 950_000
            and reinspection_tick is not None
            and lot_b <= int(reinspection_tick)
        ):
            maximum_release = 1_350_000
    return {
        "actual_lot_a_ready_tick": lot_a,
        "actual_lot_b_ready_tick": lot_b,
        "maximum_releasable_value_usd": maximum_release,
    }


def _ready_lots(r2: dict[str, Any]) -> set[str]:
    return {
        lot
        for lot in ["lot_a", "lot_b"]
        if r2.get(f"actual_{lot}_ready_tick") is not None
    }


def _requested_ship_lots(supplier: dict[str, Any]) -> set[str]:
    action = supplier.get("ship_action")
    if action == "SHIP_A":
        return {"lot_a"}
    if action == "SHIP_BOTH":
        return {"lot_a", "lot_b"}
    return set()


def _labor_capacity_consistent(
    binding: dict[str, Any],
    mobilization: dict[str, Any],
) -> bool:
    capacity = binding.get("capacity_commitment")
    overtime = binding.get("overtime_commitment")
    action = mobilization.get("mobilization_action")
    if action == "RELEASE":
        return True
    if capacity == "NONE":
        return False
    if capacity == "SPLIT":
        if action == "FULL":
            return False
        if action == "OVERTIME" and overtime != "FULL":
            return False
    return not (capacity == "FULL" and action == "OVERTIME" and overtime != "FULL")


def _mobilization_material_consistent(
    mobilization: dict[str, Any],
    shipped_lots: set[str],
) -> bool:
    action = mobilization.get("mobilization_action")
    if action in {"FULL", "OVERTIME"}:
        return {"lot_a", "lot_b"} <= shipped_lots
    if action == "PHASED":
        return "lot_a" in shipped_lots
    return True


def _rate_summary(
    edges: list[dict[str, Any]],
    predicate: Any,
) -> dict[str, Any]:
    count = len(edges)
    passing = sum(1 for edge in edges if predicate(edge))
    return {
        "count": count,
        "passing": passing,
        "rate": passing / count if count else 1.0,
    }
