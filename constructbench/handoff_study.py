from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean, stdev
from typing import Any

HANDOFF_LEVELS = ("R1", "R3", "R5")
HANDOFF_ARMS = (
    "scripted-silent",
    "scripted-prose",
    "scripted-structured",
    "live-prose",
    "live-structured",
)

CONTRASTS = {
    "structured_vs_prose_scripted": ("scripted-structured", "scripted-prose"),
    "structured_vs_silent": ("scripted-structured", "scripted-silent"),
    "prose_vs_silent": ("scripted-prose", "scripted-silent"),
    "live_vs_scripted_structured": ("live-structured", "scripted-structured"),
    "live_vs_scripted_prose": ("live-prose", "scripted-prose"),
    "structured_vs_prose_live": ("live-structured", "live-prose"),
}


def analyze_handoff_study(
    rows: list[dict[str, Any]],
    *,
    excluded_development_spend_usd: float = 0.0,
) -> dict[str, Any]:
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[(str(row["handoff_condition"]), str(row["response_curve_level"]))].append(row)

    cell_summaries = [
        _summarize_rows(cell_rows, arm=arm, level=level)
        for (arm, level), cell_rows in sorted(cells.items())
    ]
    by_arm = {
        arm: _summarize_arm(
            arm,
            [summary for summary in cell_summaries if summary["arm"] == arm],
        )
        for arm in HANDOFF_ARMS
        if any(summary["arm"] == arm for summary in cell_summaries)
    }
    contrasts = {
        name: _contrast(by_arm[left], by_arm[right], left=left, right=right)
        for name, (left, right) in CONTRASTS.items()
        if left in by_arm and right in by_arm
    }
    return {
        "schema_version": "constructbench.handoff_study_analysis.v1",
        "run_count": len(rows),
        "valid_run_count": sum(bool(row["run_valid"]) for row in rows),
        "invalid_run_count": sum(not bool(row["run_valid"]) for row in rows),
        "total_model_cost_usd": round(
            sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in rows), 6
        ),
        "development_spend_excluded_usd": round(excluded_development_spend_usd, 6),
        "program_spend_including_development_usd": round(
            excluded_development_spend_usd
            + sum(float(row.get("model_cost_usd", 0.0) or 0.0) for row in rows),
            6,
        ),
        "cell_summaries": cell_summaries,
        "arm_summaries": by_arm,
        "contrasts": contrasts,
        "interpretation_limits": [
            "Replicates are repeated API trials, not seeded independent model samples.",
            "Binary ITT outcomes count invalid runs and missing handoffs as failures.",
            "Regret means are conditional on valid terminal runs and use the frozen deterministic reference policy.",
            "Contrasts are descriptive pilot effect sizes; no null-hypothesis test is claimed.",
        ],
    }


def render_handoff_study_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# S01 distributed threshold handoff — frozen pilot results",
        "",
        f"Runs: {analysis['run_count']} ({analysis['valid_run_count']} valid); "
        f"study model cost: ${analysis['total_model_cost_usd']:.4f}; "
        f"program cost including excluded development: "
        f"${analysis['program_spend_including_development_usd']:.4f}.",
        "",
        "## Equal-weight arm summary",
        "",
        "| Arm | n | First-pass valid | Exact transfer (ITT) | Safe action (ITT) | "
        "End-to-end | Viable deal | Replacement | Mean regret |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in HANDOFF_ARMS:
        row = analysis["arm_summaries"].get(arm)
        if row is None:
            continue
        lines.append(
            f"| {arm} | {row['run_count']} | {_pct(row['first_pass_valid_rate'])} | "
            f"{_pct(row['exact_transfer_itt_rate'])} | {_pct(row['safe_action_itt_rate'])} | "
            f"{_pct(row['end_to_end_success_rate'])} | {_pct(row['viable_deal_rate'])} | "
            f"{_pct(row['replacement_rate'])} | {_usd(row['mean_regret_usd'])} |"
        )
    lines.extend(["", "## Predeclared contrasts", ""])
    for name, row in analysis["contrasts"].items():
        lines.append(
            f"- `{name}` ({row['left']} minus {row['right']}): "
            f"end-to-end {row['end_to_end_success_rate_difference']:+.3f}, "
            f"safe action {row['safe_action_itt_rate_difference']:+.3f}, "
            f"mean regret {_signed_usd(row['mean_regret_usd_difference'])}."
        )
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {limit}" for limit in analysis["interpretation_limits"])
    return "\n".join(lines) + "\n"


def _summarize_rows(
    rows: list[dict[str, Any]],
    *,
    arm: str,
    level: str,
) -> dict[str, Any]:
    valid = [row for row in rows if row["run_valid"]]
    binary = {
        "first_pass_valid": [
            bool(row["run_valid"] and int(row.get("repair_attempt_count", 0)) == 0) for row in rows
        ],
        "exact_calculation_itt": [
            bool(row["run_valid"] and row.get("gc_calculation_exact") is True) for row in rows
        ],
        "exact_transfer_itt": [
            bool(row["run_valid"] and row.get("threshold_transmission_exact") is True)
            for row in rows
        ],
        "safe_action_itt": [
            bool(row["run_valid"] and row.get("safe_action_relative_to_truth") is True)
            for row in rows
        ],
        "end_to_end_success": [bool(row.get("end_to_end_success")) for row in rows],
    }
    result: dict[str, Any] = {
        "arm": arm,
        "level": level,
        "run_count": len(rows),
        "valid_run_count": len(valid),
        "invalid_run_count": len(rows) - len(valid),
    }
    for name, values in binary.items():
        successes = sum(values)
        result[f"{name}_rate"] = successes / len(values) if values else None
        result[f"{name}_wilson_95"] = _wilson(successes, len(values))
    result["viable_deal_rate"] = _mean_bool(row["mutually_viable_deal"] for row in valid)
    result["replacement_rate"] = _mean_bool(row["supplier_replaced"] for row in valid)
    regrets = [
        float(row["supplier_attainable_regret_usd"])
        for row in valid
        if row.get("supplier_attainable_regret_usd") is not None
    ]
    result.update(_continuous(regrets, "regret_usd"))
    return result


def _summarize_arm(arm: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    cells_by_level = {cell["level"]: cell for cell in cells}
    levels = [level for level in HANDOFF_LEVELS if level in cells_by_level]

    def equal_weight(field: str) -> float | None:
        values = [cells_by_level[level].get(field) for level in levels]
        concrete = [float(value) for value in values if value is not None]
        return fmean(concrete) if concrete else None

    return {
        "arm": arm,
        "levels_present": levels,
        "run_count": sum(cells_by_level[level]["run_count"] for level in levels),
        "first_pass_valid_rate": equal_weight("first_pass_valid_rate"),
        "exact_calculation_itt_rate": equal_weight("exact_calculation_itt_rate"),
        "exact_transfer_itt_rate": equal_weight("exact_transfer_itt_rate"),
        "safe_action_itt_rate": equal_weight("safe_action_itt_rate"),
        "end_to_end_success_rate": equal_weight("end_to_end_success_rate"),
        "viable_deal_rate": equal_weight("viable_deal_rate"),
        "replacement_rate": equal_weight("replacement_rate"),
        "mean_regret_usd": equal_weight("mean_regret_usd"),
    }


def _contrast(
    left_row: dict[str, Any],
    right_row: dict[str, Any],
    *,
    left: str,
    right: str,
) -> dict[str, Any]:
    result = {"left": left, "right": right}
    for field in [
        "exact_transfer_itt_rate",
        "safe_action_itt_rate",
        "end_to_end_success_rate",
        "viable_deal_rate",
        "replacement_rate",
        "mean_regret_usd",
    ]:
        left_value = left_row.get(field)
        right_value = right_row.get(field)
        result[f"{field}_difference"] = (
            float(left_value) - float(right_value)
            if left_value is not None and right_value is not None
            else None
        )
    return result


def _wilson(successes: int, total: int) -> dict[str, float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + (z * z / total)
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) / total) + (z * z / (4 * total * total))) / denominator
    return {"lower": max(0.0, center - half), "upper": min(1.0, center + half)}


def _continuous(values: list[float], stem: str) -> dict[str, float | None]:
    return {
        f"mean_{stem}": fmean(values) if values else None,
        f"sd_{stem}": stdev(values) if len(values) > 1 else 0.0 if values else None,
        f"min_{stem}": min(values) if values else None,
        f"max_{stem}": max(values) if values else None,
    }


def _mean_bool(values: Any) -> float | None:
    concrete = [bool(value) for value in values if value is not None]
    return sum(concrete) / len(concrete) if concrete else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.0f}"


def _signed_usd(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+,.0f} USD"
