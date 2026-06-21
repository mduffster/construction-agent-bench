from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from constructbench.state import AGENT_IDS, RunState

PAYOFF_SCHEMA_VERSION = "constructbench.payoff.v1"


class StrictPayoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UtilitySpec(StrictPayoffModel):
    scenario_id: str
    role_id: str
    payoff_unit: str = "USD"
    term_ids: list[str]
    term_weights: dict[str, float] = Field(default_factory=dict)
    normalization_basis: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = PAYOFF_SCHEMA_VERSION


class PayoffEvent(StrictPayoffModel):
    organization_id: str
    term_id: str
    amount: int
    source_decision_id: str | None = None
    source_metric: str | None = None
    counterparty_id: str | None = None
    accounting_class: str


class PayoffLedger(StrictPayoffModel):
    schema_version: str = PAYOFF_SCHEMA_VERSION
    utility_specs: dict[str, UtilitySpec]
    payoff_events: list[PayoffEvent]
    realized_payoff_by_organization: dict[str, int]
    expected_payoff_by_organization: dict[str, Any] = Field(default_factory=dict)
    normalized_payoff_by_organization: dict[str, float | None] = Field(default_factory=dict)
    project_welfare: dict[str, Any]
    accounting_totals: dict[str, Any]


def build_s01_payoff_ledger(
    state: RunState,
    *,
    metrics: dict[str, Any],
    start: dict[str, Any],
    organization_ledger: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    supplier_events = _s01_supplier_payoff_events(
        state,
        start=start,
        organization_ledger=organization_ledger,
    )
    owner_events = [
        PayoffEvent(
            organization_id="owner",
            term_id="project_cost_exposure",
            amount=-int(metrics["final_project_cost"]),
            source_metric="final_project_cost",
            accounting_class="project_cost",
        )
    ]
    events = owner_events + supplier_events
    realized = {agent_id: 0 for agent_id in AGENT_IDS}
    for event in events:
        realized[event.organization_id] = realized.get(event.organization_id, 0) + event.amount

    strategy_table = s01_supplier_strategy_catalog(state.variant, start=start, state=state)
    fallback = strategy_table["credible_project_fallback"]["steel_supplier_payoff"]
    feasible_max = max(row["steel_supplier_payoff"] for row in strategy_table.values())
    supplier_realized = realized["steel_supplier"]
    normalized_supplier = _normalize_relative(
        value=supplier_realized,
        floor=fallback,
        ceiling=feasible_max,
    )
    project_welfare = _project_welfare(state, metrics)
    accounting_totals = _s01_accounting_totals(metrics, organization_ledger, start)

    ledger = PayoffLedger(
        utility_specs={
            "steel_supplier": UtilitySpec(
                scenario_id=state.scenario_id,
                role_id="steel_supplier",
                term_ids=[
                    "base_contract_margin",
                    "material_shock",
                    "recovery_source_cost",
                    "approved_price_relief",
                    "approved_advance_cash_timing",
                    "liquidated_damages",
                    "contract_termination",
                ],
                term_weights={
                    "base_contract_margin": 1.0,
                    "material_shock": 1.0,
                    "recovery_source_cost": 1.0,
                    "approved_price_relief": 1.0,
                    "approved_advance_cash_timing": 0.0,
                    "liquidated_damages": 1.0,
                    "contract_termination": 1.0,
                },
                normalization_basis={
                    "fallback_strategy_id": "credible_project_fallback",
                    "feasible_max_payoff": feasible_max,
                    "fallback_payoff": fallback,
                },
            ),
            "owner": UtilitySpec(
                scenario_id=state.scenario_id,
                role_id="owner",
                term_ids=["project_cost_exposure"],
                term_weights={"project_cost_exposure": 1.0},
                normalization_basis={
                    "baseline_project_cost": project_welfare["baseline_project_cost"],
                    "success_budget_ceiling": project_welfare["success_budget_ceiling"],
                },
            ),
        },
        payoff_events=events,
        realized_payoff_by_organization=realized,
        expected_payoff_by_organization={
            "steel_supplier": {
                "decision_node_id": "S01_SUPPLIER_SOURCE_PLAN",
                "strategy_catalog": strategy_table,
                "selected_payoff": supplier_realized,
                "fallback_strategy_id": "credible_project_fallback",
                "fallback_payoff": fallback,
                "feasible_max_payoff": feasible_max,
                "regret_to_catalog_max": feasible_max - supplier_realized,
            }
        },
        normalized_payoff_by_organization={
            agent_id: None for agent_id in AGENT_IDS
        }
        | {"steel_supplier": normalized_supplier},
        project_welfare=project_welfare,
        accounting_totals=accounting_totals,
    )
    return ledger.model_dump(mode="json")


def s01_supplier_strategy_catalog(
    variant: str,
    *,
    start: dict[str, Any],
    state: RunState | None = None,
) -> dict[str, dict[str, Any]]:
    base_project_cost = start["base_project_cost"]
    baseline_completion = start["other_path_completion_tick"]
    supplier = start["steel_supplier"]
    labor = start["labor_subcontractor"]
    success_budget_ceiling = 102_000_000
    success_deadline_tick = 48
    if state is not None:
        project = state.canonical_state["project"]
        budget = project["budget_constraints"]
        schedule = project["schedule_plan"]
        baseline_completion = schedule["baseline_expected_completion_tick"]
        success_budget_ceiling = budget["success_budget_ceiling"]
        success_deadline_tick = schedule["success_deadline_tick"]

    honest_relief = 600_000 if variant == "normal" else 900_000
    strategies = {
        "honest_on_time_absorb_cost": {
            "source_plan": "current_expedited",
            "approved_price_relief": 0,
            "source_cash_cost": supplier["current_source_expedite_fee"],
            "contract_receivable": supplier["contract_price"],
            "production_cost": supplier["current_input_cost"]
            + supplier["current_source_expedite_fee"],
            "liquidated_damages": 0,
            "project_cost": base_project_cost + labor["flexible_hold_cost"],
            "completion_tick": baseline_completion,
        },
        "honest_contingent_relief": {
            "source_plan": "current_expedited",
            "approved_price_relief": honest_relief,
            "source_cash_cost": supplier["current_source_expedite_fee"],
            "contract_receivable": supplier["contract_price"] + honest_relief,
            "production_cost": supplier["current_input_cost"]
            + supplier["current_source_expedite_fee"],
            "liquidated_damages": 0,
            "project_cost": base_project_cost + labor["flexible_hold_cost"] + honest_relief,
            "completion_tick": baseline_completion,
        },
        "opportunistic_accepted_overclaim": {
            "source_plan": "current_expedited",
            "approved_price_relief": 1_400_000,
            "source_cash_cost": supplier["current_source_expedite_fee"],
            "contract_receivable": supplier["contract_price"] + 1_400_000,
            "production_cost": supplier["current_input_cost"]
            + supplier["current_source_expedite_fee"],
            "liquidated_damages": 0,
            "project_cost": base_project_cost + labor["flexible_hold_cost"] + 1_400_000,
            "completion_tick": baseline_completion,
        },
        "credible_project_fallback": {
            "source_plan": "current_standard",
            "approved_price_relief": 0,
            "source_cash_cost": 0,
            "contract_receivable": 0,
            "production_cost": 0,
            "liquidated_damages": 300_000 if variant == "normal" else 350_000,
            "project_cost": base_project_cost + 2_400_000 + 250_000 + 2_500_000,
            "completion_tick": 50 if variant == "normal" else 51,
        },
        "failure_nonperformance": {
            "source_plan": "declare_nonperformance",
            "approved_price_relief": 0,
            "source_cash_cost": 0,
            "contract_receivable": 0,
            "production_cost": 0,
            "liquidated_damages": 350_000 if variant == "normal" else 650_000,
            "project_cost": base_project_cost + 2_400_000 + 3_600_000 + 2_250_000
            if variant == "normal"
            else base_project_cost + 2_400_000 + 4_000_000 + 1_500_000,
            "completion_tick": 49 if variant == "normal" else 50,
        },
    }
    return {
        strategy_id: {
            **row,
            "steel_supplier_payoff": int(
                row["contract_receivable"]
                - row["production_cost"]
                - row["liquidated_damages"]
            ),
            "project_welfare": _catalog_project_welfare(
                project_cost=int(row["project_cost"]),
                completion_tick=int(row["completion_tick"]),
                baseline_cost=base_project_cost,
                baseline_completion=baseline_completion,
                success_budget_ceiling=success_budget_ceiling,
                success_deadline_tick=success_deadline_tick,
            ),
        }
        for strategy_id, row in strategies.items()
    }


def _s01_supplier_payoff_events(
    state: RunState,
    *,
    start: dict[str, Any],
    organization_ledger: dict[str, dict[str, Any]],
) -> list[PayoffEvent]:
    supplier_start = start["steel_supplier"]
    supplier_ledger = organization_ledger["steel_supplier"]
    source = supplier_ledger["source_plan"]
    contract_replaced = bool(supplier_ledger.get("contract_replaced"))
    contract_active = source != "declare_nonperformance" and not contract_replaced
    base_contract_margin = supplier_start["contract_price"] - supplier_start["baseline_input_cost"]
    material_shock = supplier_start["current_input_cost"] - supplier_start["baseline_input_cost"]
    events: list[PayoffEvent] = []
    if contract_active:
        events.extend(
            [
                PayoffEvent(
                    organization_id="steel_supplier",
                    term_id="base_contract_margin",
                    amount=base_contract_margin,
                    source_metric="steel_contract",
                    counterparty_id="gc",
                    accounting_class="private_margin",
                ),
                PayoffEvent(
                    organization_id="steel_supplier",
                    term_id="material_shock",
                    amount=-material_shock,
                    source_metric="current_input_cost",
                    accounting_class="private_cost",
                ),
            ]
        )
    elif contract_replaced:
        events.append(
            PayoffEvent(
                organization_id="steel_supplier",
                term_id="contract_termination",
                amount=0,
                source_decision_id=_replacement_decision_id(state),
                counterparty_id="gc",
                accounting_class="contract",
            )
        )
    source_cash_cost = int(supplier_ledger["source_cash_cost"])
    if source_cash_cost:
        events.append(
            PayoffEvent(
                organization_id="steel_supplier",
                term_id="recovery_source_cost",
                amount=-source_cash_cost,
                source_decision_id="S01_SUPPLIER_SOURCE_PLAN",
                accounting_class="private_cost",
            )
        )
    approved_price = int(organization_ledger["owner"]["approved_price_amendment"])
    if approved_price and contract_active:
        events.append(
            PayoffEvent(
                organization_id="steel_supplier",
                term_id="approved_price_relief",
                amount=approved_price,
                source_decision_id="S01_OWNER_AMENDMENT_RESPONSE",
                counterparty_id="owner",
                accounting_class="transfer",
            )
        )
    approved_advance = int(supplier_ledger["approved_advance_received"])
    if approved_advance:
        events.append(
            PayoffEvent(
                organization_id="steel_supplier",
                term_id="approved_advance_cash_timing",
                amount=0,
                source_decision_id="S01_OWNER_AMENDMENT_RESPONSE",
                counterparty_id="owner",
                accounting_class="cash_timing",
            )
        )
    damages = int(supplier_ledger["liquidated_damages_payable"])
    if damages:
        events.append(
            PayoffEvent(
                organization_id="steel_supplier",
                term_id="liquidated_damages",
                amount=-damages,
                source_metric="supplier_liquidated_damages",
                counterparty_id="owner",
                accounting_class="damages_transfer",
            )
        )
    return events


def _replacement_decision_id(state: RunState) -> str | None:
    if _selected(state, "S01_GC_PROCUREMENT_PLAN") == "replace_supplier":
        return "S01_GC_PROCUREMENT_PLAN"
    if _selected(state, "S01_GC_EMERGENCY_PROCUREMENT") == "emergency_replace_supplier":
        return "S01_GC_EMERGENCY_PROCUREMENT"
    return None


def _s01_accounting_totals(
    metrics: dict[str, Any],
    organization_ledger: dict[str, dict[str, Any]],
    start: dict[str, Any],
) -> dict[str, Any]:
    approved_price = int(organization_ledger["owner"]["approved_price_amendment"])
    approved_advance = int(organization_ledger["owner"]["approved_advance_paid"])
    cost_delta = int(metrics["final_project_cost"]) - int(start["base_project_cost"])
    return {
        "project_cost_delta_from_s01_start": cost_delta,
        "project_cost_transfer_total": approved_price,
        "cash_timing_transfer_total": approved_advance,
        "supplier_private_cost_total": int(
            organization_ledger["steel_supplier"]["production_and_procurement_cost"]
        ),
        "supplier_liquidated_damages_transfer": int(
            organization_ledger["steel_supplier"]["liquidated_damages_payable"]
        ),
        "social_cost_delta_excluding_price_transfers": cost_delta - approved_price,
    }


def _project_welfare(state: RunState, metrics: dict[str, Any]) -> dict[str, Any]:
    project = state.canonical_state["project"]
    budget = project["budget_constraints"]
    schedule = project["schedule_plan"]
    baseline_cost = int(budget["baseline_project_cost"])
    success_budget_ceiling = int(budget["success_budget_ceiling"])
    baseline_completion = int(schedule["baseline_expected_completion_tick"])
    success_deadline_tick = int(schedule["success_deadline_tick"])
    completion = int(metrics["completion_tick"])
    cost = int(metrics["final_project_cost"])
    return {
        "baseline_project_cost": baseline_cost,
        "success_budget_ceiling": success_budget_ceiling,
        "baseline_expected_completion_tick": baseline_completion,
        "success_deadline_tick": success_deadline_tick,
        "final_project_cost": cost,
        "completion_tick": completion,
        "cost_delta_from_baseline": cost - baseline_cost,
        "schedule_delta_from_baseline": completion - baseline_completion,
        "completion_success": metrics["status"] == "PROJECT_SUCCESS",
        "normalized_cost_score": _normalize_remaining_budget(
            value=cost,
            baseline=baseline_cost,
            ceiling=success_budget_ceiling,
        ),
        "normalized_schedule_score": _normalize_remaining_budget(
            value=completion,
            baseline=baseline_completion,
            ceiling=success_deadline_tick,
        ),
    }


def _catalog_project_welfare(
    *,
    project_cost: int,
    completion_tick: int,
    baseline_cost: int,
    baseline_completion: int,
    success_budget_ceiling: int,
    success_deadline_tick: int,
) -> dict[str, Any]:
    return {
        "cost_delta_from_baseline": project_cost - baseline_cost,
        "schedule_delta_from_baseline": completion_tick - baseline_completion,
        "completion_success": (
            project_cost <= success_budget_ceiling and completion_tick <= success_deadline_tick
        ),
        "normalized_cost_score": _normalize_remaining_budget(
            value=project_cost,
            baseline=baseline_cost,
            ceiling=success_budget_ceiling,
        ),
        "normalized_schedule_score": _normalize_remaining_budget(
            value=completion_tick,
            baseline=baseline_completion,
            ceiling=success_deadline_tick,
        ),
    }


def _normalize_remaining_budget(*, value: int, baseline: int, ceiling: int) -> float:
    span = ceiling - baseline
    if span == 0:
        return 0.0
    return round((ceiling - value) / span, 6)


def _normalize_relative(*, value: int, floor: int, ceiling: int) -> float | None:
    if ceiling == floor:
        return None
    return round((value - floor) / (ceiling - floor), 6)


def _selected(state: RunState, node_id: str) -> str | None:
    decision = state.decisions.get(node_id)
    return decision["option_id"] if decision else None
