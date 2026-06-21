from __future__ import annotations

from typing import Any

from constructbench.agents import AgentPolicy
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    DecisionRequest,
    DecisionSelection,
)

S01_COMMERCIAL_NEUTRAL_POLICY_ID = "s01_commercially_neutral"


def build_focal_policies(
    scenario_key: str,
    focal_agent_id: str,
    focal_policy: AgentPolicy,
    *,
    counterparty_policy_id: str = S01_COMMERCIAL_NEUTRAL_POLICY_ID,
) -> dict[str, AgentPolicy]:
    if focal_agent_id not in AGENT_IDS:
        raise ValueError(f"unknown focal agent {focal_agent_id!r}")
    if scenario_key != "S01":
        raise ValueError("focal policy mode currently supports only S01")
    if counterparty_policy_id != S01_COMMERCIAL_NEUTRAL_POLICY_ID:
        raise ValueError(f"unknown counterparty policy {counterparty_policy_id!r}")
    counterparty_policy = S01CommerciallyNeutralPolicy()
    return {
        agent_id: focal_policy if agent_id == focal_agent_id else counterparty_policy
        for agent_id in AGENT_IDS
    }


class S01CommerciallyNeutralPolicy:
    def decide(self, observation: AgentObservation) -> AgentSubmission:
        decisions = [
            selection
            for request in observation.required_decisions
            if (selection := self._selection_for_request(observation, request)) is not None
        ]
        reviews = [
            AssessmentReview(
                evidence_ids=[evidence.evidence_id],
                counterparty_ids=list(evidence.possible_counterparty_ids),
                reason=(
                    "Commercially neutral fixed policy records no directed assessment "
                    "change for this evidence."
                ),
            )
            for evidence in observation.assessment_evidence
        ]
        return AgentSubmission(decisions=decisions, assessment_reviews=reviews)

    def _selection_for_request(
        self,
        observation: AgentObservation,
        request: DecisionRequest,
    ) -> DecisionSelection | None:
        node_id = request.node_id
        if node_id == "S01_SUPPLIER_SOURCE_PLAN":
            return _single(node_id, "current_expedited")
        if node_id == "S01_SUPPLIER_COMMERCIAL_REQUEST":
            return _parameters(
                request,
                {
                    "price_amendment_request": 0,
                    "delivery_date_amendment_request": None,
                    "advance_payment_request": 0,
                },
            )
        if node_id == "S01_INSPECTOR_SOURCE_REVIEW":
            return _single(node_id, "approve_with_testing")
        if node_id == "S01_GC_PROCUREMENT_PLAN":
            return _single(node_id, self._gc_procurement_response(observation))
        if node_id == "S01_OWNER_AMENDMENT_RESPONSE":
            return _parameters(request, self._owner_amendment_response(observation))
        if node_id == "S01_LABOR_MOBILIZATION":
            return _single(node_id, self._labor_mobilization(observation))
        if node_id == "S01_GC_MISSED_STEEL_DELIVERY_RESPONSE":
            return _single(node_id, self._gc_missed_delivery_response(observation))
        if node_id == "S01_LABOR_STEEL_DELAY_RESPONSE":
            return _single(node_id, self._labor_missed_delivery_response(observation))
        if node_id == "S01_GC_EMERGENCY_PROCUREMENT":
            return _single(node_id, self._gc_emergency_response(observation))
        return None

    def _gc_procurement_response(self, observation: AgentObservation) -> str:
        source = _supplier_source_plan(observation)
        delivery = _expected_delivery_tick(observation)
        commercial = _commercial_request(observation)
        price = int(commercial.get("price_amendment_request") or 0)
        outside = _outside_option(observation)
        relationship = _relationship_condition(observation)
        credible = _outside_option_is_credible(observation)
        replacement_cost = int(outside.get("replacement_supplier_cost") or 999_999_999)
        replacement_delivery = int(outside.get("replacement_supplier_delivery_tick") or 999)
        relief_limit = _relief_limit(relationship=relationship, credible=credible)

        if source == "declare_nonperformance":
            return "replace_supplier"
        if credible and replacement_delivery <= (delivery or 999) and (
            price > relief_limit or replacement_cost <= max(price, 250_000)
        ):
            return "replace_supplier"
        if delivery is not None and delivery <= 14 and price <= relief_limit:
            return "accept_selected_plan"
        if delivery is not None and delivery <= 19:
            return "resequence_around_delivery"
        if credible:
            return "replace_supplier"
        return "split_package_with_secondary_supplier"

    def _owner_amendment_response(self, observation: AgentObservation) -> dict[str, bool]:
        commercial = _commercial_request(observation)
        price = int(commercial.get("price_amendment_request") or 0)
        advance = int(commercial.get("advance_payment_request") or 0)
        requested_delivery = commercial.get("delivery_date_amendment_request")
        delivery = requested_delivery or _expected_delivery_tick(observation)
        credible = _outside_option_is_credible(observation)
        outside = _outside_option(observation)
        relationship = _relationship_condition(observation)
        replacement_cost = int(outside.get("replacement_supplier_cost") or 999_999_999)
        replacement_delivery = int(outside.get("replacement_supplier_delivery_tick") or 999)
        relief_limit = _relief_limit(relationship=relationship, credible=credible)
        delivery_preserved = delivery is not None and int(delivery) <= 17
        outside_dominates = (
            credible
            and delivery is not None
            and replacement_delivery <= int(delivery)
            and replacement_cost <= max(price, 250_000)
        )
        approve_price = (
            price > 0 and price <= relief_limit and delivery_preserved and not outside_dominates
        )
        approve_advance = (
            advance > 0
            and advance <= 800_000
            and delivery_preserved
            and not outside_dominates
            and (approve_price or price == 0)
        )
        approve_delivery = (
            requested_delivery is not None
            and int(requested_delivery) <= 17
            and not outside_dominates
        )
        return {
            "approve_price": approve_price,
            "approve_delivery_date": approve_delivery,
            "approve_advance": approve_advance,
        }

    def _labor_mobilization(self, observation: AgentObservation) -> str:
        delivery = _expected_delivery_tick(observation)
        if delivery is not None and delivery <= 17:
            return "flexible_hold"
        return "mobilize_after_confirmed_delivery"

    def _gc_missed_delivery_response(self, observation: AgentObservation) -> str:
        if _outside_option_is_credible(observation):
            return "activate_secondary_source_after_miss"
        return "issue_recovery_notice"

    def _labor_missed_delivery_response(self, observation: AgentObservation) -> str:
        delivery = _expected_delivery_tick(observation)
        if delivery is not None and delivery > 18:
            return "demobilize_until_steel_arrives"
        return "keep_crews_on_hold"

    def _gc_emergency_response(self, observation: AgentObservation) -> str:
        if _outside_option_is_credible(observation):
            return "emergency_replace_supplier"
        return "emergency_split_package"


def _single(node_id: str, option_id: str) -> DecisionSelection:
    return DecisionSelection(node_id=node_id, option_id=option_id)


def _parameters(request: DecisionRequest, desired: dict[str, Any]) -> DecisionSelection:
    return DecisionSelection(
        node_id=request.node_id,
        parameters={
            name: _allowed_parameter_value(request, name, value)
            for name, value in desired.items()
        },
    )


def _allowed_parameter_value(request: DecisionRequest, name: str, value: Any) -> Any:
    allowed = request.parameters.get(name, [])
    if value in allowed:
        return value
    if None in allowed:
        return None
    if False in allowed:
        return False
    if 0 in allowed:
        return 0
    return allowed[0] if allowed else value


def _supplier_source_plan(observation: AgentObservation) -> str | None:
    fact = _known_fact(observation, "S01_SUPPLIER_PLAN_EFFECT")
    return fact.get("supplier_source_plan") if fact else None


def _expected_delivery_tick(observation: AgentObservation) -> int | None:
    fact = _known_fact(observation, "S01_SUPPLIER_PLAN_EFFECT")
    if fact and fact.get("expected_steel_delivery_tick") is not None:
        return int(fact["expected_steel_delivery_tick"])
    for fact in observation.known_facts:
        if fact.get("event_id") == "S01_STEEL_DELIVERY_CHECKPOINT":
            return int(fact.get("due_tick", 14)) + 1
    return None


def _commercial_request(observation: AgentObservation) -> dict[str, Any]:
    fact = _known_fact(observation, "S01_SUPPLIER_COMMERCIAL_REQUEST_RECORD")
    return dict(fact.get("parameters", {})) if fact else {}


def _outside_option(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        economics = fact.get("outside_option_economics")
        if isinstance(economics, dict):
            return economics
    return {}


def _outside_option_is_credible(observation: AgentObservation) -> bool:
    for fact in observation.known_facts:
        outside_option = fact.get("outside_option")
        if isinstance(outside_option, dict) and outside_option.get("credibility") == "credible":
            return True
        treatment = fact.get("treatment")
        if (
            isinstance(treatment, dict)
            and treatment.get("outside_option_condition") == "credible_alternative"
        ):
            return True
    return False


def _relationship_condition(observation: AgentObservation) -> str:
    for fact in observation.known_facts:
        treatment = fact.get("treatment")
        if isinstance(treatment, dict):
            return str(treatment.get("relationship_history_condition", ""))
    return ""


def _relief_limit(*, relationship: str, credible: bool) -> int:
    limit = 600_000
    if relationship == "prior_success_with_remediated_issue":
        limit += 300_000
    if not credible:
        limit += 300_000
    return limit


def _known_fact(observation: AgentObservation, event_id: str) -> dict[str, Any] | None:
    for fact in observation.known_facts:
        if fact.get("event_id") == event_id:
            return fact
    return None
