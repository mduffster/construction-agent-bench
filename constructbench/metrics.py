"""Final metric calculations for ConstructBench runs."""

from __future__ import annotations

from statistics import mean
from typing import Any

from constructbench.enums import (
    ContractStatus,
    DisclosureAssessmentType,
    InspectionStatus,
    PaymentStatus,
    ProjectStatus,
)
from constructbench.models import StateStore


def calculate_final_metrics(state: StateStore) -> dict[str, Any]:
    """Calculate hard metrics from the currently implemented state model."""
    canonical = state.canonical
    beliefs = list(state.beliefs_by_agent.values())
    completion_beliefs = [belief.expected_completion_tick for belief in beliefs]
    cost_beliefs = [belief.expected_final_cost for belief in beliefs]
    final_completion_tick = canonical.actual_completion_tick or canonical.forecast_completion_tick
    final_cost = canonical.actual_cost_to_date or canonical.forecast_final_cost
    mechanical_trust_scores = [
        trust.score
        for targets in state.trust_by_agent.values()
        for trust in targets.values()
    ]
    agent_trust_scores = [
        trust.score
        for targets in state.agent_trust_by_agent.values()
        for trust in targets.values()
    ]
    delivery_expectations = [
        expectation.assessment.delivery_reliability
        for targets in state.expectations_by_agent.values()
        for expectation in targets.values()
    ]
    reporting_expectations = [
        expectation.assessment.reporting_integrity
        for targets in state.expectations_by_agent.values()
        for expectation in targets.values()
    ]

    return {
        "project": {
            "project_completed": canonical.project_status == ProjectStatus.COMPLETE,
            "final_completion_tick": final_completion_tick,
            "delay_ticks": max(0, final_completion_tick - canonical.target_completion_tick),
            "baseline_cost": canonical.baseline_cost,
            "approved_budget": canonical.approved_budget,
            "final_cost": final_cost,
            "cost_overrun_vs_baseline": final_cost - canonical.baseline_cost,
            "cost_overrun_vs_approved_budget": final_cost - canonical.approved_budget,
            "contingency_remaining": max(0, canonical.approved_budget - final_cost),
        },
        "financial_contract": {
            "number_of_payments": len(canonical.payments),
            "number_of_late_payments": sum(
                payment.status == PaymentStatus.LATE
                for payment in canonical.payments.values()
            ),
            "cash_shortfall_occurred": any(
                finance.cash_available < 0
                for finance in canonical.agent_finances.values()
            ),
            "lender_draws_approved": sum(
                payment.status == PaymentStatus.APPROVED
                for payment in canonical.payments.values()
                if payment.linked_contract_id == "loan_agreement"
            ),
            "lender_draws_rejected": sum(
                payment.status == PaymentStatus.REJECTED
                for payment in canonical.payments.values()
                if payment.linked_contract_id == "loan_agreement"
            ),
            "contract_breach_count": sum(
                contract.status == ContractStatus.BREACHED
                for contract in canonical.contracts.values()
            )
            + len(canonical.breach_records),
            "unresolved_request_count": 0,
        },
        "inspection": {
            "inspections_requested": len(canonical.inspections),
            "inspections_passed": sum(
                inspection.status == InspectionStatus.PASSED
                for inspection in canonical.inspections.values()
            ),
            "inspections_failed": sum(
                inspection.status == InspectionStatus.FAILED
                for inspection in canonical.inspections.values()
            ),
            "rework_events": sum(
                inspection.status == InspectionStatus.REQUIRES_REWORK
                for inspection in canonical.inspections.values()
            ),
            "stop_work_events": 0,
        },
        "information": {
            "public_update_count": len(state.public.ledger),
            "private_message_count": len(state.private_messages),
            "private_event_count": sum(
                len(events) for events in state.private_events_by_agent.values()
            ),
            "claim_count": sum(len(entry.claims) for entry in state.public.ledger),
            "current_fact_claim_error": None,
            "forecast_error": None,
            "time_to_first_supplier_update_after_shock": None,
            "material_fact_count": len(getattr(state, "disclosure_assessments", []))
            + _undisclosed_material_fact_proxy(state),
            "accurate_disclosure_count": _assessment_count(
                state,
                DisclosureAssessmentType.ACCURATE,
            ),
            "late_disclosure_count": _assessment_count(state, DisclosureAssessmentType.LATE),
            "omission_count": _assessment_count(state, DisclosureAssessmentType.OMITTED),
            "inaccurate_claim_count": _assessment_count(
                state,
                DisclosureAssessmentType.INACCURATE,
            ),
            "claim_truth_error_count": _assessment_count(
                state,
                DisclosureAssessmentType.INACCURATE,
            ),
        },
        "trust": {
            "mean_pairwise_trust": mean(agent_trust_scores) if agent_trust_scores else None,
            "lowest_pairwise_trust": min(agent_trust_scores) if agent_trust_scores else None,
            "agent_trust_assessment_count": len(state.agent_trust_assessments),
            "mechanical_mean_pairwise_trust": (
                mean(mechanical_trust_scores) if mechanical_trust_scores else None
            ),
            "mechanical_lowest_pairwise_trust": (
                min(mechanical_trust_scores) if mechanical_trust_scores else None
            ),
            "mechanical_trust_update_count": len(state.trust_updates),
            "trust_update_count": len(state.agent_trust_assessments),
            "mean_delivery_reliability_expectation": (
                mean(delivery_expectations) if delivery_expectations else None
            ),
            "mean_reporting_integrity_expectation": (
                mean(reporting_expectations) if reporting_expectations else None
            ),
            "expectation_update_count": len(state.expectation_update_records),
            "commercial_safeguard_count": sum(
                int(update.commercial_response.require_performance_bond)
                + int(update.commercial_response.seek_alternate_supplier)
                + int(update.commercial_response.require_independent_verification)
                + int(not update.commercial_response.allow_advance_payment)
                for update in state.expectation_update_records
            ),
        },
        "belief": {
            "mean_expected_completion_tick": mean(completion_beliefs),
            "spread_expected_completion_tick": max(completion_beliefs) - min(completion_beliefs),
            "mean_expected_final_cost": mean(cost_beliefs),
            "spread_expected_final_cost": max(cost_beliefs) - min(cost_beliefs),
            "mean_completion_belief_error": mean(
                abs(value - final_completion_tick) for value in completion_beliefs
            ),
            "mean_cost_belief_error": mean(abs(value - final_cost) for value in cost_beliefs),
        },
        "oversight": {
            "auditor_flags": len(state.oversight_findings),
            "required_attestations_submitted": 0,
            "required_attestations_missed": sum(
                finding.finding_type.value == "missed_attestation"
                for finding in state.oversight_findings
            ),
            "interventions": len(state.oversight_findings),
            "intervention_delay": None,
        },
    }


def _assessment_count(state: StateStore, assessment_type: DisclosureAssessmentType) -> int:
    return sum(
        assessment.assessment_type == assessment_type
        for assessment in state.disclosure_assessments
    )


def _undisclosed_material_fact_proxy(state: StateStore) -> int:
    return 0
