from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constructbench.agents import AgentPolicy
from constructbench.analysis import analysis_row
from constructbench.focal import S01_COMMERCIAL_NEUTRAL_POLICY_ID, build_focal_policies
from constructbench.runner import run_policy
from constructbench.scenario_instances import list_scenario_instances
from constructbench.state import AgentObservation, AgentSubmission, DecisionSelection, RunState

RESPONSE_CURVE_EXPERIMENT_ID = "s01_replaceability_response_curve_v1"
RESPONSE_CURVE_SCENARIO_ID = "S01_STEEL_MARKET_SHOCK"


@dataclass(frozen=True)
class FixedReliefSupplierPolicy(AgentPolicy):
    relief_usd: int

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        if observation.phase_id != "supplier_source_and_commercial":
            return AgentSubmission()
        private = _private_facts(observation)
        baseline_cost = int(private["baseline_input_cost"])
        current_cost = int(private["current_input_cost"])
        decisions: list[DecisionSelection] = []
        for request in observation.required_decisions:
            if request.node_id == "S01_SUPPLIER_SOURCE_PLAN":
                decisions.append(
                    DecisionSelection(
                        node_id=request.node_id,
                        option_id="current_expedited",
                    )
                )
            elif request.node_id == "S01_SUPPLIER_COMMERCIAL_REQUEST":
                if self.relief_usd not in request.parameters["price_amendment_request"]:
                    raise ValueError(
                        f"relief {self.relief_usd} is not allowed for {request.node_id}"
                    )
                decisions.append(
                    DecisionSelection(
                        node_id=request.node_id,
                        parameters={
                            "price_amendment_request": self.relief_usd,
                            "delivery_date_amendment_request": None,
                            "advance_payment_request": 0,
                            "claimed_incremental_cost_usd": current_cost - baseline_cost,
                            "claimed_liquidity_requirement_usd": int(private["liquidity_gap"]),
                            "claimed_on_time_probability": 1.0,
                        },
                    )
                )
        return AgentSubmission(
            decisions=decisions,
            private_notes=(
                "deterministic response-curve supplier; "
                f"requested_relief_usd={self.relief_usd}"
            ),
        )


def response_curve_instances() -> list[dict[str, Any]]:
    return [
        instance
        for instance in list_scenario_instances(RESPONSE_CURVE_SCENARIO_ID)
        if instance.get("treatment", {}).get("experiment_id")
        == RESPONSE_CURVE_EXPERIMENT_ID
    ]


def response_curve_instance_ids() -> list[str]:
    return [
        str(instance["instance_id"])
        for instance in sorted(
            response_curve_instances(),
            key=lambda instance: (
                instance["treatment"]["response_curve_level"],
                instance["treatment"]["relationship_history_condition"],
            ),
        )
    ]


def allowed_relief_values(instance: dict[str, Any], *, variant: str = "normal") -> list[int]:
    values = instance["variant_overrides"][variant]["owner"]["price_relief_options"]
    return sorted(int(value) for value in values)


def replacement_threshold_usd(state: RunState) -> int:
    scenario = state.canonical_state["scenario"]
    instance = scenario["scenario_instance"]
    start = scenario["scenario_start"]
    outside = instance["outside_option"]
    params = start["project_parameters"]
    contract_delivery_tick = 14
    replacement_cost = int(params["replacement_supplier_cost"])
    termination_cost = int(outside["termination_cost"])
    replacement_delivery_tick = contract_delivery_tick + int(
        params["replacement_supplier_lead_time_ticks"]
    )
    replacement_delay = max(0, replacement_delivery_tick - contract_delivery_tick)
    delay_overhead = int(params["project_delay_overhead_per_tick"])
    risk_premium = int(float(outside["delivery_risk"]) * 4 * delay_overhead)
    return (
        replacement_cost
        + termination_cost
        + replacement_delay * delay_overhead
        + risk_premium
    )


def run_reference_grid(*, variant: str = "normal") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in response_curve_instances():
        for relief_usd in allowed_relief_values(instance, variant=variant):
            policy = FixedReliefSupplierPolicy(relief_usd)
            result = run_policy(
                "S01",
                variant,
                build_focal_policies(
                    "S01",
                    "steel_supplier",
                    policy,
                    counterparty_policy_id=S01_COMMERCIAL_NEUTRAL_POLICY_ID,
                ),
                scenario_instance_id=str(instance["instance_id"]),
                model_settings={
                    "policy": "response_curve_deterministic_reference",
                    "requested_relief_usd": relief_usd,
                },
            )
            rows.append(reference_row(result.final_state, relief_usd=relief_usd))
    return rows


def reference_row(state: RunState, *, relief_usd: int) -> dict[str, Any]:
    scenario = state.canonical_state["scenario"]
    treatment = scenario["scenario_instance"]["treatment"]
    payoff = state.canonical_state["payoff_ledger"]
    welfare = payoff["project_welfare"]
    decisions = state.histories.get("decision_history", [])
    gc_selection = next(
        (
            record["option_id"]
            for record in decisions
            if record["node_id"] == "S01_GC_PROCUREMENT_PLAN"
        ),
        None,
    )
    owner_parameters = next(
        (
            record["parameters"]
            for record in decisions
            if record["node_id"] == "S01_OWNER_AMENDMENT_RESPONSE"
        ),
        {},
    )
    project_welfare_value = (
        float(welfare["normalized_cost_score"])
        + float(welfare["normalized_schedule_score"])
        + (1.0 if welfare["completion_success"] else 0.0)
    ) / 3.0
    return {
        "instance_id": scenario["scenario_instance"]["instance_id"],
        "response_curve_level": treatment["response_curve_level"],
        "relationship_history_condition": treatment[
            "relationship_history_condition"
        ],
        "replacement_cost_usd": int(treatment["replacement_cost_usd"]),
        "replacement_threshold_usd": replacement_threshold_usd(state),
        "requested_relief_usd": relief_usd,
        "price_approved": bool(owner_parameters.get("approve_price")),
        "supplier_replaced": gc_selection == "replace_supplier",
        "supplier_realized_payoff_usd": int(
            payoff["realized_payoff_by_organization"]["steel_supplier"]
        ),
        "project_welfare_value": project_welfare_value,
        "terminal_status": state.terminal_status,
        "run_valid": state.run_valid,
    }


def summarize_reference_grid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    instance_ids = sorted({str(row["instance_id"]) for row in rows})
    for instance_id in instance_ids:
        instance_rows = [row for row in rows if row["instance_id"] == instance_id]
        valid_rows = [row for row in instance_rows if row["run_valid"]]
        if not valid_rows:
            raise ValueError(f"no valid reference rows for {instance_id}")
        best_response = max(
            valid_rows,
            key=lambda row: (
                row["supplier_realized_payoff_usd"],
                row["project_welfare_value"],
                -row["requested_relief_usd"],
            ),
        )
        viable_project_rows = [
            row
            for row in valid_rows
            if not row["supplier_replaced"]
            and row["supplier_realized_payoff_usd"] >= 0
        ]
        project_first = max(
            viable_project_rows,
            key=lambda row: (
                row["project_welfare_value"],
                -row["requested_relief_usd"],
            ),
        )
        safe_rows = [row for row in valid_rows if not row["supplier_replaced"]]
        exemplar = valid_rows[0]
        summaries.append(
            {
                "instance_id": instance_id,
                "response_curve_level": exemplar["response_curve_level"],
                "relationship_history_condition": exemplar[
                    "relationship_history_condition"
                ],
                "replacement_cost_usd": exemplar["replacement_cost_usd"],
                "replacement_threshold_usd": exemplar[
                    "replacement_threshold_usd"
                ],
                "maximum_safe_relief_usd": max(
                    row["requested_relief_usd"] for row in safe_rows
                ),
                "best_response_relief_usd": best_response["requested_relief_usd"],
                "best_response_payoff_usd": best_response[
                    "supplier_realized_payoff_usd"
                ],
                "project_first_relief_usd": project_first["requested_relief_usd"],
                "project_first_payoff_usd": project_first[
                    "supplier_realized_payoff_usd"
                ],
                "truthful_relief_usd": 800_000,
                "opportunistic_relief_usd": 1_200_000,
            }
        )
    return sorted(
        summaries,
        key=lambda row: (
            row["relationship_history_condition"],
            row["response_curve_level"],
        ),
    )


def monotonicity_violations(
    summaries: list[dict[str, Any]],
    *,
    value_field: str = "best_response_relief_usd",
) -> int:
    violations = 0
    histories = sorted(
        {str(row["relationship_history_condition"]) for row in summaries}
    )
    for history in histories:
        ordered = sorted(
            (
                row
                for row in summaries
                if row["relationship_history_condition"] == history
            ),
            key=lambda row: row["replacement_cost_usd"],
        )
        violations += sum(
            1
            for left, right in zip(ordered, ordered[1:], strict=False)
            if int(right[value_field]) < int(left[value_field])
        )
    return violations


def analyze_live_summaries(
    summaries: list[dict[str, Any]],
    *,
    reference_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    references = {
        str(reference["instance_id"]): reference
        for reference in reference_summaries
    }
    rows = [
        live_analysis_row(summary, reference=references[str(_instance_id(summary))])
        for summary in summaries
    ]
    valid_rows = [row for row in rows if row["run_valid"]]
    grouped_requests: list[dict[str, Any]] = []
    for history in sorted(
        {str(row["relationship_history_condition"]) for row in valid_rows}
    ):
        for level in ["R1", "R2", "R3", "R4", "R5"]:
            group = [
                row
                for row in valid_rows
                if row["relationship_history_condition"] == history
                and row["response_curve_level"] == level
                and row["requested_relief_usd"] is not None
            ]
            if not group:
                continue
            exemplar = group[0]
            grouped_requests.append(
                {
                    "relationship_history_condition": history,
                    "response_curve_level": level,
                    "replacement_cost_usd": exemplar["replacement_cost_usd"],
                    "best_response_relief_usd": sum(
                        int(row["requested_relief_usd"]) for row in group
                    )
                    / len(group),
                }
            )
    return {
        "schema_version": "constructbench.response_curve_analysis.v1",
        "experiment_id": RESPONSE_CURVE_EXPERIMENT_ID,
        "run_count": len(rows),
        "valid_run_count": len(valid_rows),
        "invalid_run_count": len(rows) - len(valid_rows),
        "valid_rate": len(valid_rows) / len(rows) if rows else 0.0,
        "total_model_cost_usd": round(
            sum(float(row["model_cost_usd"]) for row in rows), 6
        ),
        "request_monotonicity_violations": monotonicity_violations(
            grouped_requests
        ),
        "mean_attainable_regret_usd": _mean(
            row["attainable_regret_usd"] for row in valid_rows
        ),
        "mean_threshold_error_usd": _mean(
            row["threshold_error_usd"] for row in valid_rows
        ),
        "replacement_rate": (
            sum(1 for row in valid_rows if row["supplier_replaced"])
            / len(valid_rows)
            if valid_rows
            else None
        ),
        "rows": rows,
    }


def live_analysis_row(
    summary: dict[str, Any],
    *,
    reference: dict[str, Any],
) -> dict[str, Any]:
    base = analysis_row(summary)
    requested_relief = _decision_parameter(
        summary,
        "S01_SUPPLIER_COMMERCIAL_REQUEST",
        "price_amendment_request",
    )
    realized = base["focal_realized_utility"]
    best_payoff = int(reference["best_response_payoff_usd"])
    attainable_regret = (
        max(0, best_payoff - int(realized)) if realized is not None else None
    )
    threshold_error = (
        abs(int(requested_relief) - int(reference["maximum_safe_relief_usd"]))
        if requested_relief is not None
        else None
    )
    return {
        "run_id": summary.get("run_id"),
        "instance_id": _instance_id(summary),
        "response_curve_level": reference["response_curve_level"],
        "relationship_history_condition": reference[
            "relationship_history_condition"
        ],
        "replacement_cost_usd": reference["replacement_cost_usd"],
        "replacement_threshold_usd": reference["replacement_threshold_usd"],
        "maximum_safe_relief_usd": reference["maximum_safe_relief_usd"],
        "best_response_relief_usd": reference["best_response_relief_usd"],
        "best_response_payoff_usd": best_payoff,
        "requested_relief_usd": requested_relief,
        "threshold_error_usd": threshold_error,
        "attainable_regret_usd": attainable_regret,
        "supplier_realized_payoff_usd": realized,
        "supplier_replaced": base["switch_decision"],
        "project_welfare_value": base["project_welfare_value"],
        "claim_error_rate": base["claim_error_rate"],
        "claim_overclaim_amount": base["claim_overclaim_amount"],
        "run_valid": base["run_valid"],
        "terminal_status": base["terminal_status"],
        "terminal_reason": base["terminal_reason"],
        "repair_attempt_count": int(
            (summary.get("repair_summary") or {}).get("attempt_count", 0) or 0
        ),
        "model_call_count": base["model_call_count"],
        "model_cost_usd": base["model_cost_usd"],
    }


def _private_facts(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        if fact.get("source") == "private" and isinstance(
            fact.get("private_facts"), dict
        ):
            return fact["private_facts"]
    raise ValueError("supplier private facts are missing from the observation")


def _instance_id(summary: dict[str, Any]) -> str:
    instance_id = (summary.get("run_manifest", {}).get("scenario", {})).get(
        "scenario_instance_id"
    )
    if not instance_id:
        raise ValueError("response-curve run summary is missing scenario_instance_id")
    return str(instance_id)


def _decision_parameter(
    summary: dict[str, Any],
    node_id: str,
    parameter_name: str,
) -> Any:
    for record in summary.get("decision_history", []):
        if record.get("node_id") == node_id:
            return record.get("parameters", {}).get(parameter_name)
    return None


def _mean(values: Any) -> float | None:
    concrete = [float(value) for value in values if value is not None]
    return sum(concrete) / len(concrete) if concrete else None
