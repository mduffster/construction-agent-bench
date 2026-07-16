from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from math import comb
from typing import Any, Literal

from constructbench.agents import AgentPolicy
from constructbench.s01_v2_derived_state_packet import (
    build_packet_assignment_policies,
    packetized_deterministic_policies,
    study_run_row,
)

DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID = "s01_v2_decision_summary_factorial_v1"
NO_SUMMARY = "no_summary"
SUPPLIER_ONLY = "supplier_only"
CONTRACTOR_ONLY = "contractor_only"
BOTH_SUMMARIES = "both_summaries"
FACTORIAL_CONDITIONS = (NO_SUMMARY, SUPPLIER_ONLY, CONTRACTOR_ONLY, BOTH_SUMMARIES)
FactorialCondition = Literal[
    "no_summary",
    "supplier_only",
    "contractor_only",
    "both_summaries",
]

SUMMARY_RECIPIENTS: dict[str, frozenset[str]] = {
    NO_SUMMARY: frozenset(),
    SUPPLIER_ONLY: frozenset({"steel_supplier"}),
    CONTRACTOR_ONLY: frozenset({"gc"}),
    BOTH_SUMMARIES: frozenset({"steel_supplier", "gc"}),
}


def summary_recipients(condition: str) -> frozenset[str]:
    try:
        return SUMMARY_RECIPIENTS[condition]
    except KeyError as exc:
        raise ValueError(f"unknown decision-summary condition {condition!r}") from exc


def build_factorial_policies(
    condition: str,
    factory: Callable[[str], AgentPolicy] | None = None,
) -> dict[str, AgentPolicy]:
    return build_packet_assignment_policies(summary_recipients(condition), factory)


def factorial_reference_policies(condition: str) -> dict[str, AgentPolicy]:
    return packetized_deterministic_policies(summary_recipients(condition))


def factorial_run_row(
    *,
    condition: str,
    replicate_index: int,
    sequence_index: int,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    recipients = summary_recipients(condition)
    row = study_run_row(
        condition=condition,
        replicate_index=replicate_index,
        sequence_index=sequence_index,
        summary=summary,
        exposure_agents=recipients,
    )
    row["supplier_summary"] = "steel_supplier" in recipients
    row["contractor_summary"] = "gc" in recipients
    return row


def aggregate_factorial_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition = {
        condition: _arm_summary([row for row in rows if row.get("condition") == condition])
        for condition in FACTORIAL_CONDITIONS
    }
    supplier_present = [row for row in rows if row.get("supplier_summary") is True]
    supplier_absent = [row for row in rows if row.get("supplier_summary") is False]
    contractor_present = [row for row in rows if row.get("contractor_summary") is True]
    contractor_absent = [row for row in rows if row.get("contractor_summary") is False]
    return {
        "experiment_id": DECISION_SUMMARY_FACTORIAL_EXPERIMENT_ID,
        "assigned_count": len(rows),
        "valid_count": _count_true(rows, "run_valid"),
        "by_condition": by_condition,
        "supplier_summary_main_effect": _risk_difference(
            supplier_present, supplier_absent, "joint_efficient_outcome"
        ),
        "contractor_summary_main_effect": _risk_difference(
            contractor_present, contractor_absent, "joint_efficient_outcome"
        ),
        "interaction_risk_difference": _interaction_risk_difference(by_condition),
        "all_exposure_audits_passed": all(
            row.get("packet_exposure_audit_passed") is True for row in rows
        ),
        "total_model_cost_usd": round(
            sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in rows), 6
        ),
    }


def _arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    assigned = len(rows)
    valid = _count_true(rows, "run_valid")
    joint = _count_true(rows, "joint_efficient_outcome")
    backup = _count_true(rows, "backup_activated")
    coalition = _count_true(rows, "coalition_success")
    return {
        "assigned_count": assigned,
        "valid_count": valid,
        "joint_efficient_outcome_count": joint,
        "joint_efficient_outcome_rate": joint / assigned if assigned else None,
        "joint_efficient_outcome_exact_95_ci": exact_binomial_interval(joint, assigned),
        "coalition_success_count": coalition,
        "coalition_success_rate": coalition / assigned if assigned else None,
        "coalition_success_exact_95_ci": exact_binomial_interval(coalition, assigned),
        "backup_activation_count": backup,
        "backup_activation_rate": backup / assigned if assigned else None,
        "backup_activation_exact_95_ci": exact_binomial_interval(backup, assigned),
        "full_sequence_cure_count": sum(
            row.get("b1_cure_plan") == "FULL_SEQUENCE_CURE" for row in rows
        ),
        "lot_b_ready_count": _count_true(rows, "r2_full_sequence_ready"),
        "lineage_complete_count": _count_true(rows, "lineage_complete"),
        "repair_attempt_count": sum(int(row.get("repair_attempt_count", 0) or 0) for row in rows),
        "mean_final_project_cost": _mean(rows, "final_project_cost"),
        "mean_completion_tick": _mean(rows, "completion_tick"),
        "model_cost_usd": round(
            sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in rows), 6
        ),
    }


def exact_binomial_interval(successes: int, trials: int, alpha: float = 0.05) -> list[float] | None:
    """Two-sided Clopper-Pearson interval using binomial-tail inversion."""

    if trials == 0:
        return None
    if not 0 <= successes <= trials:
        raise ValueError("successes must be between zero and trials")
    lower = 0.0 if successes == 0 else _bisect_tail(
        lambda probability: _binomial_survival(successes - 1, trials, probability),
        alpha / 2,
        increasing=True,
    )
    upper = 1.0 if successes == trials else _bisect_tail(
        lambda probability: _binomial_cdf(successes, trials, probability),
        alpha / 2,
        increasing=False,
    )
    return [round(lower, 6), round(upper, 6)]


def _risk_difference(
    present: list[dict[str, Any]], absent: list[dict[str, Any]], field: str
) -> dict[str, Any]:
    present_rate = _count_true(present, field) / len(present) if present else None
    absent_rate = _count_true(absent, field) / len(absent) if absent else None
    return {
        "present_rate": present_rate,
        "absent_rate": absent_rate,
        "risk_difference": (
            present_rate - absent_rate
            if present_rate is not None and absent_rate is not None
            else None
        ),
    }


def _interaction_risk_difference(by_condition: Mapping[str, Mapping[str, Any]]) -> float | None:
    rates = {
        condition: by_condition[condition].get("joint_efficient_outcome_rate")
        for condition in FACTORIAL_CONDITIONS
    }
    if any(rate is None for rate in rates.values()):
        return None
    return float(
        rates[BOTH_SUMMARIES]
        - rates[SUPPLIER_ONLY]
        - rates[CONTRACTOR_ONLY]
        + rates[NO_SUMMARY]
    )


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    return sum(
        comb(n, index)
        * probability**index
        * (1 - probability) ** (n - index)
        for index in range(k + 1)
    )


def _binomial_survival(k: int, n: int, probability: float) -> float:
    return 1.0 - _binomial_cdf(k, n, probability)


def _bisect_tail(function: Callable[[float], float], target: float, *, increasing: bool) -> float:
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2
        value = function(midpoint)
        if increasing:
            if value < target:
                low = midpoint
            else:
                high = midpoint
        else:
            if value > target:
                low = midpoint
            else:
                high = midpoint
    return (low + high) / 2


def _count_true(rows: Collection[Mapping[str, Any]], field: str) -> int:
    return sum(row.get(field) is True for row in rows)


def _mean(rows: Collection[Mapping[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return sum(values) / len(values) if values else None
