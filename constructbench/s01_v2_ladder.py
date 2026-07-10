from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from constructbench.agents import AgentPolicy, ScriptedPolicy
from constructbench.models import (
    DEFAULT_ANTHROPIC_HAIKU_MODEL,
    AnthropicModelAdapter,
    LLMPolicy,
)
from constructbench.scenarios import SCENARIOS
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    DecisionSelection,
)

S01_V2_LADDER_EXPERIMENT_ID = "s01_v2_live_multiplayer_ladder_v1"
LINEAGE_LIVE_PROFILE_ID = "s01_v2_lineage_core_fields_v1"
EFFICIENT_BACKGROUND_FIXTURE = "efficient_phased_coalition_success"
DEFAULT_PROGRAM_PRIOR_COST_USD = 6.495753
DEFAULT_NEW_MODEL_ALLOCATION_USD = 2.0
DEFAULT_HARD_TOTAL_CAP_USD = 9.5
DEFAULT_USER_LIMIT_USD = 10.0
DEFAULT_STAGE_RESERVE_PER_LIVE_ROLE_USD = 0.12

LINEAGE_LIVE_FIELDS_BY_NODE: dict[str, tuple[str, ...]] = {
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
    "S01_A3_OWNER_PROVISIONAL_POSITION": (
        "owner_funding_ceiling_usd",
        "immediate_equity_ceiling_usd",
        "required_control_codes",
    ),
    "S01_A3_INSPECTOR_REVIEW_PLAN": (
        "inspection_scope",
        "inspection_tick",
    ),
    "S01_A3_ERECTOR_CAPACITY_OFFER": (
        "capacity_offer",
        "hold_through_tick",
        "standby_price_usd",
    ),
    "S01_A4_LENDER_PROVISIONAL_POSITION": (
        "maximum_draw_usd",
        "advance_rate",
        "escrow_cap_usd",
        "minimum_owner_equity_usd",
        "required_control_codes",
    ),
    "S01_B1_SUPPLIER_COMMITMENT": (
        "cure_plan",
        "supplier_cash_committed_usd",
        "outside_financing_usd",
        "outside_work_action",
        "provisional_offer_actions",
        "requested_price_adjustment_usd",
        "lot_a_commitment_tick",
        "lot_b_commitment_tick",
    ),
    "S01_B2_GC_INTEGRATED_PACKAGE": (
        "supplier_proposal_action",
        "final_certified_payment_usd",
        "gc_bridge_usd",
        "owner_funds_requested_usd",
        "lender_draw_requested_usd",
        "supplier_price_adjustment_usd",
        "backup_action",
    ),
    "S01_B3_INSPECTOR_DISPOSITION": (
        "disposition",
        "reinspection_tick",
        "maximum_releasable_value_usd",
    ),
    "S01_B3_ERECTOR_BINDING_COMMITMENT": (
        "offer_action",
        "capacity_commitment",
        "mobilization_tick",
        "standby_compensation_usd",
        "overtime_commitment",
        "minimum_releasable_value_usd",
    ),
    "S01_B4_OWNER_PACKAGE_DECISION": (
        "package_action",
        "owner_funding_usd",
        "owner_equity_usd",
        "approved_price_adjustment_usd",
        "approved_standby_usd",
    ),
    "S01_B5_LENDER_RELEASE_DECISION": (
        "release_action",
        "draw_release_usd",
        "escrow_release_usd",
        "completion_reserve_after_usd",
        "owner_equity_required_usd",
    ),
    "S01_C1_SUPPLIER_STATUS_AND_RECOVERY": (
        "ship_action",
        "supplier_recovery_spend_usd",
    ),
    "S01_C2_GC_RECOVERY_PLAN": (
        "recovery_plan",
        "supplemental_gc_bridge_usd",
    ),
    "S01_C3_INSPECTOR_FINAL_DISPOSITION": (
        "lot_a_disposition",
        "lot_b_disposition",
        "approved_shipping_value_usd",
    ),
    "S01_C4_OWNER_FINAL_POSITION": (
        "accepted_additional_cost_usd",
        "owner_cost_share_usd",
        "gc_cost_share_usd",
        "supplier_cost_share_usd",
    ),
    "S01_C5_LENDER_SUPPLEMENTAL_POSITION": (
        "reserve_exception_usd",
    ),
    "S01_C6_ERECTOR_MOBILIZATION": (
        "mobilization_action",
        "mobilization_tick",
        "incremental_cost_usd",
        "remobilization_tick_if_released",
    ),
}


@dataclass(frozen=True)
class LadderStage:
    stage_id: str
    live_roles: tuple[str, ...]


LADDER_STAGES = (
    LadderStage("supplier_gc", ("steel_supplier", "gc")),
    LadderStage("add_inspector", ("steel_supplier", "gc", "inspector")),
    LadderStage(
        "add_owner_lender",
        ("steel_supplier", "gc", "inspector", "owner", "lender"),
    ),
    LadderStage("full_six", tuple(AGENT_IDS)),
)
LADDER_STAGE_BY_ID = {stage.stage_id: stage for stage in LADDER_STAGES}


@dataclass(frozen=True)
class BudgetConfig:
    program_prior_cost_usd: float = DEFAULT_PROGRAM_PRIOR_COST_USD
    new_model_allocation_usd: float = DEFAULT_NEW_MODEL_ALLOCATION_USD
    hard_total_cap_usd: float = DEFAULT_HARD_TOTAL_CAP_USD
    user_limit_usd: float = DEFAULT_USER_LIMIT_USD
    stage_reserve_per_live_role_usd: float = DEFAULT_STAGE_RESERVE_PER_LIVE_ROLE_USD

    def validate(self) -> None:
        values = {
            "program_prior_cost_usd": self.program_prior_cost_usd,
            "new_model_allocation_usd": self.new_model_allocation_usd,
            "hard_total_cap_usd": self.hard_total_cap_usd,
            "user_limit_usd": self.user_limit_usd,
            "stage_reserve_per_live_role_usd": self.stage_reserve_per_live_role_usd,
        }
        negative = [name for name, value in values.items() if value < 0]
        if negative:
            raise ValueError(f"budget values cannot be negative: {negative}")
        if self.hard_total_cap_usd >= self.user_limit_usd:
            raise ValueError(
                "hard_total_cap_usd must remain strictly below the user limit so an "
                "unspent safety reserve remains"
            )
        if self.program_prior_cost_usd >= self.hard_total_cap_usd:
            raise ValueError("program prior cost already reaches the hard total cap")
        if self.program_prior_cost_usd + self.new_model_allocation_usd > self.hard_total_cap_usd:
            raise ValueError(
                "program prior cost plus the new allocation exceeds the hard total cap"
            )

    @property
    def user_limit_reserve_usd(self) -> float:
        return self.user_limit_usd - self.hard_total_cap_usd

    def stage_reserve_usd(self, live_roles: Iterable[str]) -> float:
        return len(tuple(live_roles)) * self.stage_reserve_per_live_role_usd

    def assert_can_start(self, *, spent_new_usd: float, live_roles: Iterable[str]) -> None:
        self.validate()
        reserve = self.stage_reserve_usd(live_roles)
        projected_new = spent_new_usd + reserve
        projected_program = self.program_prior_cost_usd + projected_new
        if projected_new > self.new_model_allocation_usd:
            raise RuntimeError(
                "new-model allocation stop: "
                f"spent ${spent_new_usd:.6f} + next-stage reserve ${reserve:.6f} "
                f"> allocation ${self.new_model_allocation_usd:.6f}"
            )
        if projected_program > self.hard_total_cap_usd:
            raise RuntimeError(
                "hard program cost stop: "
                f"prior ${self.program_prior_cost_usd:.6f} + new ${spent_new_usd:.6f} "
                f"+ next-stage reserve ${reserve:.6f} "
                f"> cap ${self.hard_total_cap_usd:.6f}"
            )


def stages_through(stage_id: str) -> list[LadderStage]:
    try:
        stop_index = next(
            index for index, stage in enumerate(LADDER_STAGES) if stage.stage_id == stage_id
        )
    except StopIteration as exc:
        raise ValueError(f"unknown ladder stage {stage_id!r}") from exc
    return list(LADDER_STAGES[: stop_index + 1])


def validate_live_roles(live_roles: Iterable[str]) -> tuple[str, ...]:
    roles = tuple(dict.fromkeys(live_roles))
    unknown = sorted(set(roles) - set(AGENT_IDS))
    if unknown:
        raise ValueError(f"unknown live roles: {unknown}")
    if not roles:
        raise ValueError("at least one live role is required")
    return roles


class StateAwareEfficientPolicy(ScriptedPolicy):
    """Efficient fixture background adapted to facts produced by live upstream roles.

    The fixture is a deterministic adjudication control, not a simulated agent. The
    adaptations mirror facts a live organization reads from its observation and keep
    the background from submitting an impossible shipment, release, or recovery merely
    because an upstream live role departed from the efficient witness.
    """

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        submission = super().decide(observation)
        for selection in submission.decisions:
            params = selection.parameters
            if selection.node_id == "S01_A2_GC_INITIAL_REVIEW":
                submitted = _visible_submitted_documents(observation)
                for field in (
                    "owner_lender_package_document_ids",
                    "inspector_package_document_ids",
                ):
                    params[field] = [
                        document_id
                        for document_id in params.get(field, [])
                        if document_id in submitted
                    ]
            if selection.node_id == "S01_B2_GC_INTEGRATED_PACKAGE":
                _adapt_gc_package(params, observation)
            if selection.node_id == "S01_B4_OWNER_PACKAGE_DECISION":
                _adapt_owner_package(params, observation)
            if selection.node_id == "S01_B5_LENDER_RELEASE_DECISION":
                _adapt_lender_release(params, observation)
            if selection.node_id == "S01_C1_SUPPLIER_STATUS_AND_RECOVERY":
                _adapt_supplier_shipping(params, _private_readiness(observation))
            if selection.node_id in {
                "S01_B3_INSPECTOR_DISPOSITION",
                "S01_C3_INSPECTOR_FINAL_DISPOSITION",
            }:
                _adapt_inspector_release(params, observation, selection.node_id)
            if selection.node_id == "S01_B3_ERECTOR_BINDING_COMMITMENT":
                _adapt_labor_binding(params, observation)
            if selection.node_id == "S01_C2_GC_RECOVERY_PLAN":
                if params.get("recovery_plan") == "ACTIVATE_BACKUP" and not _visible_backup(
                    observation
                ):
                    params["recovery_plan"] = "ACCEPT_DELAY"
            if selection.node_id == "S01_C6_ERECTOR_MOBILIZATION":
                _adapt_labor_mobilization(params, observation)
        return submission


class LineageCorePolicy:
    """Let a live model choose only the fields used by the lineage pilot.

    Advisory S01 V2 fields remain fixed to the state-aware efficient control.
    Missing live fields stay missing in the merged submission so the ordinary
    validation and repair path still tests schema conformance.
    """

    def __init__(
        self,
        live_policy: AgentPolicy,
        *,
        background_policy: StateAwareEfficientPolicy | None = None,
    ) -> None:
        self.live_policy = live_policy
        self.background_policy = background_policy or efficient_background_policy()

    def initialize(self, briefing: Any) -> None:
        if hasattr(self.live_policy, "initialize"):
            self.live_policy.initialize(briefing)  # type: ignore[attr-defined]

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        projected = _project_lineage_observation(observation)
        live_submission = self.live_policy.decide(projected)
        return self._merge(observation, live_submission)

    def repair(
        self,
        observation: AgentObservation,
        errors: list[str],
    ) -> AgentSubmission:
        projected = _project_lineage_observation(observation)
        if hasattr(self.live_policy, "repair"):
            live_submission = self.live_policy.repair(  # type: ignore[attr-defined]
                projected,
                errors,
            )
        else:
            live_submission = self.live_policy.decide(projected)
        return self._merge(observation, live_submission)

    def drain_model_io(self) -> list[dict[str, Any]]:
        if hasattr(self.live_policy, "drain_model_io"):
            return self.live_policy.drain_model_io()  # type: ignore[attr-defined]
        return []

    def _merge(
        self,
        observation: AgentObservation,
        live_submission: AgentSubmission,
    ) -> AgentSubmission:
        background = self.background_policy.decide(observation)
        background_by_node = {
            selection.node_id: selection for selection in background.decisions
        }
        live_by_node = {
            selection.node_id: selection for selection in live_submission.decisions
        }
        merged: list[DecisionSelection] = []
        for request in observation.required_decisions:
            live = live_by_node.get(request.node_id)
            if live is None:
                continue
            baseline = background_by_node[request.node_id]
            live_fields = set(LINEAGE_LIVE_FIELDS_BY_NODE[request.node_id])
            parameters = {
                name: value
                for name, value in baseline.parameters.items()
                if name not in live_fields
            }
            parameters.update(
                {
                    name: value
                    for name, value in live.parameters.items()
                    if name in live_fields
                }
            )
            merged.append(
                DecisionSelection(
                    node_id=request.node_id,
                    option_id=live.option_id,
                    parameters=parameters,
                )
            )
        return AgentSubmission(
            decisions=merged,
            communications=live_submission.communications,
            assessment_updates=live_submission.assessment_updates,
            assessment_reviews=live_submission.assessment_reviews,
            private_notes=live_submission.private_notes,
        )


LivePolicyFactory = Callable[[str], AgentPolicy]


def efficient_background_policy() -> StateAwareEfficientPolicy:
    fixture = SCENARIOS["S01_V2"].fixtures[EFFICIENT_BACKGROUND_FIXTURE]
    return StateAwareEfficientPolicy(deepcopy(fixture["decisions"]))


def default_live_policy_factory(
    *,
    model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1200,
) -> LivePolicyFactory:
    def create(agent_id: str) -> AgentPolicy:
        return LLMPolicy(
            AnthropicModelAdapter(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            agent_id,
            prompt_style="anthropic_structured",
        )

    return create


def build_mixed_policies(
    live_roles: Iterable[str],
    *,
    live_policy_factory: LivePolicyFactory,
) -> dict[str, AgentPolicy]:
    live = set(validate_live_roles(live_roles))
    policies: dict[str, AgentPolicy] = {}
    for agent_id in AGENT_IDS:
        policies[agent_id] = (
            LineageCorePolicy(live_policy_factory(agent_id))
            if agent_id in live
            else efficient_background_policy()
        )
    return policies


def deterministic_background_policies() -> dict[str, AgentPolicy]:
    return {agent_id: efficient_background_policy() for agent_id in AGENT_IDS}


def _project_lineage_observation(
    observation: AgentObservation,
) -> AgentObservation:
    projected = observation.model_copy(deep=True)
    for request in projected.required_decisions:
        allowed = set(LINEAGE_LIVE_FIELDS_BY_NODE[request.node_id])
        request.parameter_specs = {
            name: spec
            for name, spec in request.parameter_specs.items()
            if name in allowed
        }
        request.parameters = {
            name: values
            for name, values in request.parameters.items()
            if name in allowed
        }
    return projected


def lineage_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Read the evolving S01 V2 lineage schema without making it a runner dependency."""

    analysis = summary.get("s01_v2_analysis", {})
    if not isinstance(analysis, Mapping):
        return {"available": False, "passed": None, "source": None}
    candidates = [
        ("s01_v2_analysis.lineage_gate", analysis.get("lineage_gate")),
        ("s01_v2_analysis.lineage", analysis.get("lineage")),
        ("s01_v2_analysis.lineage_metrics", analysis.get("lineage_metrics")),
        ("s01_v2_analysis.decision_lineage", analysis.get("decision_lineage")),
        ("s01_v2_analysis", analysis),
    ]
    for source, candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        earliest_failed_edge = candidate.get(
            "earliest_failed_edge",
            candidate.get("earliest_failed_edge_id"),
        )
        if "passed" in candidate and isinstance(candidate.get("passed"), bool):
            return {
                "available": True,
                "passed": bool(candidate["passed"]),
                "source": f"{source}.passed",
                "earliest_failed_edge": earliest_failed_edge,
            }
        for field in (
            "lineage_complete",
            "complete_chain",
            "complete_chain_boolean",
        ):
            if isinstance(candidate.get(field), bool):
                return {
                    "available": True,
                    "passed": bool(candidate[field]),
                    "source": f"{source}.{field}",
                    "earliest_failed_edge": earliest_failed_edge,
                }
        exposure_rate = candidate.get("expected_edge_exposure_rate")
        if isinstance(exposure_rate, (int, float)):
            return {
                "available": True,
                "passed": float(exposure_rate) == 1.0,
                "source": f"{source}.expected_edge_exposure_rate",
                "earliest_failed_edge": earliest_failed_edge,
            }
    return {"available": False, "passed": None, "source": None}


def run_row(
    *,
    stage: LadderStage,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    usage = summary.get("model_usage_summary", {}).get("total", {})
    analysis = summary.get("s01_v2_analysis", {})
    return {
        "stage_id": stage.stage_id,
        "live_roles": list(stage.live_roles),
        "run_valid": bool(summary.get("run_valid")),
        "terminal_status": summary.get("terminal_status"),
        "terminal_reason": summary.get("terminal_reason"),
        "path_label": (analysis.get("path_label") if isinstance(analysis, Mapping) else None),
        "project_success": (
            analysis.get("project_success") if isinstance(analysis, Mapping) else None
        ),
        "coalition_success": (
            analysis.get("coalition_success") if isinstance(analysis, Mapping) else None
        ),
        "model_call_count": int(usage.get("call_count", 0) or 0),
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "model_cost_usd": float(usage.get("cost_usd", 0.0) or 0.0),
        "repair_attempt_count": int(summary.get("repair_summary", {}).get("attempt_count", 0) or 0),
        "lineage_gate": lineage_gate(summary),
    }


def _visible_submitted_documents(observation: AgentObservation) -> set[str]:
    documents: set[str] = set()
    for fact in observation.known_facts:
        for record in fact.get("visible_decisions", []) or []:
            if record.get("node_id") == "S01_A1_SUPPLIER_APPLICATION":
                documents.update(record.get("parameters", {}).get("submitted_document_ids", []))
    return documents


def _private_readiness(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        private_facts = fact.get("private_facts")
        if not isinstance(private_facts, dict):
            continue
        readiness = private_facts.get("s01_v2_actual_readiness")
        if isinstance(readiness, dict):
            return dict(readiness)
    return {}


def _adapt_supplier_shipping(params: dict[str, Any], readiness: Mapping[str, Any]) -> None:
    if not readiness:
        return
    lot_a_ready = readiness.get("actual_lot_a_ready_tick") is not None
    lot_b_ready = readiness.get("actual_lot_b_ready_tick") is not None
    if params.get("ship_action") == "SHIP_BOTH" and not lot_b_ready:
        params["ship_action"] = "SHIP_A" if lot_a_ready else "HOLD_ALL"
    if params.get("ship_action") in {"SHIP_A", "SHIP_BOTH"} and not lot_a_ready:
        params["ship_action"] = "HOLD_ALL"


def _adapt_gc_package(
    params: dict[str, Any],
    observation: AgentObservation,
) -> None:
    bounds = _constraint_rule(observation, "verified_value_and_draw_bounds")
    for field, bound_field in {
        "final_certified_payment_usd": "maximum_final_certified_payment_usd",
        "lender_draw_requested_usd": "maximum_lender_draw_requested_usd",
        "gc_bridge_usd": "maximum_gc_bridge_usd",
        "owner_funds_requested_usd": "maximum_owner_funds_requested_usd",
    }.items():
        if bound_field in bounds:
            params[field] = min(int(params.get(field, 0)), int(bounds[bound_field]))


def _adapt_owner_package(
    params: dict[str, Any],
    observation: AgentObservation,
) -> None:
    bounds = _constraint_rule(observation, "owner_package_request_bounds")
    for field, bound_field in {
        "owner_funding_usd": "maximum_owner_funding_usd",
        "approved_price_adjustment_usd": "maximum_approved_price_adjustment_usd",
    }.items():
        if bound_field in bounds:
            params[field] = min(int(params.get(field, 0)), int(bounds[bound_field]))
    if not _supplier_offer_accepted(observation, "OWNER_PROVISIONAL_SUPPORT"):
        params.update(
            {
                "package_action": "REJECT",
                "owner_funding_usd": 0,
                "owner_equity_usd": 0,
                "approved_price_adjustment_usd": 0,
                "approved_standby_usd": 0,
            }
        )


def _adapt_lender_release(
    params: dict[str, Any],
    observation: AgentObservation,
) -> None:
    bounds = _constraint_rule(observation, "lender_supported_release")
    if not bounds:
        return
    maximum_draw = int(bounds.get("maximum_draw_if_reserve_preserved_usd", 0))
    minimum_reserve = int(bounds.get("minimum_completion_reserve_usd", 0))
    params["completion_reserve_after_usd"] = max(
        int(params.get("completion_reserve_after_usd", 0)),
        minimum_reserve,
    )
    params["owner_equity_required_usd"] = max(
        int(params.get("owner_equity_required_usd", 0)),
        int(bounds.get("minimum_owner_equity_usd", 0)),
    )
    params["escrow_release_usd"] = 0
    incompatible = (
        not _supplier_offer_accepted(observation, "LENDER_PROVISIONAL_DRAW")
        or _visible_params(
            observation, "S01_B2_GC_INTEGRATED_PACKAGE"
        ).get("supplier_proposal_action")
        == "REJECT"
        or _visible_params(
            observation, "S01_B3_ERECTOR_BINDING_COMMITMENT"
        ).get("offer_action")
        == "RELEASE"
        or _visible_params(
            observation, "S01_B4_OWNER_PACKAGE_DECISION"
        ).get("package_action")
        == "REJECT"
    )
    if maximum_draw <= 0 or incompatible:
        params["release_action"] = "HOLD"
        params["draw_release_usd"] = 0
        return
    params["release_action"] = "PARTIAL_RELEASE"
    params["draw_release_usd"] = min(
        int(params.get("draw_release_usd", 0)),
        maximum_draw,
    )


def _constraint_rule(
    observation: AgentObservation,
    constraint_id: str,
) -> dict[str, Any]:
    for fact in observation.known_facts:
        constraints = fact.get("decision_constraints")
        if not isinstance(constraints, dict):
            continue
        for rule in constraints.get("rules", []):
            if rule.get("constraint_id") == constraint_id:
                return dict(rule)
    return {}


def _supplier_offer_accepted(
    observation: AgentObservation,
    offer_id: str,
) -> bool:
    supplier = _visible_params(observation, "S01_B1_SUPPLIER_COMMITMENT")
    actions = set(supplier.get("provisional_offer_actions", []))
    return (
        f"{offer_id}:ACCEPT" in actions
        and f"{offer_id}:REJECT" not in actions
    )


def _adapt_labor_binding(
    params: dict[str, Any],
    observation: AgentObservation,
) -> None:
    if _supplier_offer_accepted(observation, "ERECTOR_CAPACITY_OFFER"):
        return
    params.update(
        {
            "offer_action": "RELEASE",
            "capacity_commitment": "NONE",
            "mobilization_tick": None,
            "standby_compensation_usd": 0,
            "overtime_commitment": "NONE",
            "minimum_releasable_value_usd": 0,
        }
    )


def _adapt_inspector_release(
    params: dict[str, Any], observation: AgentObservation, node_id: str
) -> None:
    bound = _releasable_value_bound(observation, node_id)
    field = (
        "maximum_releasable_value_usd"
        if node_id == "S01_B3_INSPECTOR_DISPOSITION"
        else "approved_shipping_value_usd"
    )
    if bound is not None and int(params.get(field, 0)) > bound:
        params[field] = bound
    if bound == 0 and node_id == "S01_B3_INSPECTOR_DISPOSITION":
        params["disposition"] = "NO_RELEASE"
    if bound is not None and bound < 950_000 and node_id == "S01_C3_INSPECTOR_FINAL_DISPOSITION":
        params["lot_a_disposition"] = "HOLD"
        params["lot_b_disposition"] = "HOLD"
    elif (
        bound is not None and bound < 1_350_000 and node_id == "S01_C3_INSPECTOR_FINAL_DISPOSITION"
    ):
        params["lot_b_disposition"] = "HOLD"


def _releasable_value_bound(observation: AgentObservation, node_id: str) -> int | None:
    for fact in observation.known_facts:
        bounds = fact.get("decision_bounds", {}) or {}
        node_bounds = bounds.get(node_id)
        if isinstance(node_bounds, dict) and "maximum_releasable_value_usd" in node_bounds:
            return int(node_bounds["maximum_releasable_value_usd"])
    return None


def _visible_backup(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        options = fact.get("recovery_options")
        if not isinstance(options, dict):
            continue
        backup = options.get("backup")
        if (
            isinstance(backup, dict)
            and backup.get("status") in {"RESERVED", "QUALIFYING", "ACTIVATED"}
            and int(backup.get("activation_cost_usd") or 0) > 0
            and backup.get("delivery_tick_if_activated") is not None
        ):
            return dict(backup)
    return {}


def _adapt_labor_mobilization(params: dict[str, Any], observation: AgentObservation) -> None:
    binding: Mapping[str, Any] = _constraint_rule(
        observation,
        "mobilization_within_binding_capacity",
    )
    capacity = binding.get("capacity_commitment")
    if capacity == "NONE":
        params.update(
            {
                "mobilization_action": "RELEASE",
                "remobilization_tick_if_released": 23,
            }
        )
    elif capacity == "SPLIT":
        params["mobilization_action"] = "PHASED"
    supplier = _visible_params(observation, "S01_C1_SUPPLIER_STATUS_AND_RECOVERY")
    inspector = _visible_params(observation, "S01_C3_INSPECTOR_FINAL_DISPOSITION")
    lot_a_available = (
        supplier.get("ship_action") in {"SHIP_A", "SHIP_BOTH"}
        and inspector.get("lot_a_disposition") in {"RELEASE", "CONDITIONAL"}
        and int(inspector.get("approved_shipping_value_usd", 0)) >= 950_000
    )
    if not lot_a_available and params.get("mobilization_action") != "RELEASE":
        params["mobilization_action"] = "DELAY"


def _visible_params(
    observation: AgentObservation,
    node_id: str,
) -> Mapping[str, Any]:
    for fact in observation.known_facts:
        for record in fact.get("visible_decisions", []) or []:
            if record.get("node_id") == node_id:
                parameters = record.get("parameters")
                if isinstance(parameters, dict):
                    return parameters
    return {}
