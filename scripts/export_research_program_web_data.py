from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HANDOFF_ROOT = ROOT / "outputs" / "s01_handoff_v2_1_confirmation_20260710"
LADDER_ROOT = ROOT / "outputs" / "s01_v2_multiplayer_ladder_v2_20260710"
HANDOFF_REPORT = ROOT / "docs" / "s01_distributed_threshold_handoff_results.md"
MULTIPLAYER_REPORT = ROOT / "docs" / "s01_v2_multiplayer_bridge_results.md"
WEB_DATA_PATH = ROOT / "web" / "src" / "game-data" / "s01_research_program.json"

ARM_ORDER = [
    "scripted-silent",
    "scripted-prose",
    "scripted-structured",
    "live-prose",
    "live-structured",
]

ARM_PRESENTATION = {
    "scripted-silent": ("Scripted GC", "No handoff"),
    "scripted-prose": ("Scripted GC", "Rendered prose"),
    "scripted-structured": ("Scripted GC", "Structured record"),
    "live-prose": ("Live GC", "Rendered prose"),
    "live-structured": ("Live GC", "Structured record"),
}


def main() -> None:
    handoff_study_path = HANDOFF_ROOT / "study_analysis.json"
    handoff_rows_path = HANDOFF_ROOT / "study_rows.jsonl"
    ladder_summary_path = LADDER_ROOT / "ladder_summary.json"
    handoff_study = _read_json(handoff_study_path)
    handoff_rows = _read_jsonl(handoff_rows_path)
    ladder_summary = _read_json(ladder_summary_path)

    reference = _read_json(LADDER_ROOT / "reference_run" / "run_summary.json")
    live_summaries = [
        _read_json(
            LADDER_ROOT
            / "runs"
            / f"{index:02d}_{row['stage_id']}"
            / "run_summary.json"
        )
        for index, row in enumerate(ladder_summary["rows"])
    ]

    live_handoff_rows = [
        row for row in handoff_rows if row["handoff_condition"].startswith("live-")
    ]
    exact_live_rows = [row for row in live_handoff_rows if row["gc_calculation_exact"]]
    exact_safe_rows = [
        row for row in exact_live_rows if row["safe_action_relative_to_truth"]
    ]
    exact_end_to_end_rows = [
        row for row in exact_live_rows if row["end_to_end_success"]
    ]

    arm_summaries = handoff_study["arm_summaries"]
    arms = []
    for arm_id in ARM_ORDER:
        summary = arm_summaries[arm_id]
        rows = [row for row in handoff_rows if row["handoff_condition"] == arm_id]
        sender, representation = ARM_PRESENTATION[arm_id]
        arms.append(
            {
                "arm_id": arm_id,
                "sender": sender,
                "representation": representation,
                "assigned_run_count": len(rows),
                "valid_run_count": sum(bool(row["run_valid"]) for row in rows),
                "exact_calculation_itt_rate": summary["exact_calculation_itt_rate"],
                "exact_transfer_itt_rate": summary["exact_transfer_itt_rate"],
                "safe_action_itt_rate": summary["safe_action_itt_rate"],
                "end_to_end_success_rate": summary["end_to_end_success_rate"],
                "replacement_rate": summary["replacement_rate"],
            }
        )

    ladder_rows = []
    for row, summary in zip(ladder_summary["rows"], live_summaries, strict=True):
        live_decision_count = len(row["live_roles"]) * 3
        repairs = int(row["repair_attempt_count"])
        analysis = summary["s01_v2_analysis"]
        lineage = analysis["lineage"]
        ladder_rows.append(
            {
                "stage_id": row["stage_id"],
                "live_role_count": len(row["live_roles"]),
                "live_roles": row["live_roles"],
                "run_valid": row["run_valid"],
                "project_success": row["project_success"],
                "coalition_success": row["coalition_success"],
                "first_pass_live_decision_count": live_decision_count - repairs,
                "live_decision_count": live_decision_count,
                "repair_attempt_count": repairs,
                "completion_tick": analysis["completion_tick"],
                "final_project_cost": analysis["final_project_cost"],
                "path_label": analysis["path_label"],
                "lineage_complete": lineage["lineage_complete"],
                "viability_preserving_chain": lineage["viability_preserving_chain"],
                "clip_count": lineage["clip_count"],
            }
        )

    reference_analysis = reference["s01_v2_analysis"]
    common_live_path = _common_live_path(live_summaries)
    efficient_path = _path_summary(reference)
    payload = {
        "schema_version": "constructsim.web_research_program.v1",
        "title": "From one decision to six firms",
        "question": (
            "Can AI organizations receive the right business facts, carry them across "
            "organizational boundaries, and turn them into good commercial decisions?"
        ),
        "handoff": {
            "experiment_id": "s01_distributed_threshold_handoff_v2_1",
            "assigned_run_count": handoff_study["run_count"],
            "valid_run_count": handoff_study["valid_run_count"],
            "invalid_run_count": handoff_study["invalid_run_count"],
            "live_run_count": len(live_handoff_rows),
            "exact_live_calculation_count": len(exact_live_rows),
            "safe_action_given_exact_count": len(exact_safe_rows),
            "end_to_end_success_given_exact_count": len(exact_end_to_end_rows),
            "arms": arms,
            "interpretation": (
                "When the GC calculated the threshold correctly, the supplier acted safely. "
                "Structured and prose representations performed identically with a live GC, "
                "localizing the dominant failure before transmission: binding the right facts "
                "and calculating the derived value."
            ),
            "limitations": handoff_study["interpretation_limits"],
        },
        "multiplayer": {
            "experiment_id": ladder_summary["experiment_id"],
            "code_commit": ladder_summary["code_commit"],
            "completed_stage_count": ladder_summary["completed_stage_count"],
            "stop_reason": ladder_summary["stop_reason"],
            "reference": {
                "live_role_count": 0,
                "run_valid": reference["run_valid"],
                "project_success": reference_analysis["project_success"],
                "coalition_success": reference_analysis["coalition_success"],
                "repair_attempt_count": 0,
                "completion_tick": reference_analysis["completion_tick"],
                "final_project_cost": reference_analysis["final_project_cost"],
                "path_label": reference_analysis["path_label"],
            },
            "rows": ladder_rows,
            "expected_exposure_count": reference_analysis["lineage"][
                "expected_exposure"
            ]["count"],
            "operative_link_count": reference_analysis["lineage"][
                "operative_constraint_conformance"
            ]["count"],
            "live_decision_count": sum(row["live_decision_count"] for row in ladder_rows),
            "first_pass_live_decision_count": sum(
                row["first_pass_live_decision_count"] for row in ladder_rows
            ),
            "repair_attempt_count": sum(
                row["repair_attempt_count"] for row in ladder_rows
            ),
            "project_cost_min": min(row["final_project_cost"] for row in ladder_rows),
            "project_cost_max": max(row["final_project_cost"] for row in ladder_rows),
            "common_live_path": common_live_path,
            "efficient_reference_path": efficient_path,
            "interpretation": (
                "The measured data chain worked, but every live rung narrowed the technical "
                "scope to Lot A and later used expensive backup steel. The next target is the "
                "supplier-GC decision boundary where that narrowing first appears."
            ),
            "limitations": [
                "There is one frozen temperature-zero trajectory per live-role rung.",
                "The cumulative role additions do not identify an individual-role effect.",
                "Project success does not imply that every firm met its private target.",
            ],
        },
        "source": {
            "handoff_report_path": "docs/s01_distributed_threshold_handoff_results.md",
            "handoff_report_sha256": _sha256(HANDOFF_REPORT),
            "handoff_study_sha256": _sha256(handoff_study_path),
            "multiplayer_report_path": "docs/s01_v2_multiplayer_bridge_results.md",
            "multiplayer_report_sha256": _sha256(MULTIPLAYER_REPORT),
            "multiplayer_ladder_sha256": _sha256(ladder_summary_path),
        },
    }
    payload["content_sha256"] = _content_hash(payload)
    WEB_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {WEB_DATA_PATH.relative_to(ROOT)}")


def _common_live_path(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    paths = [_path_summary(summary) for summary in summaries]
    first = paths[0]
    if any(path != first for path in paths[1:]):
        raise ValueError("live ladder rungs do not share the same public path summary")
    return first


def _path_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "supplier_payment_request_usd": _decision_parameter(
            summary, "S01_A1_SUPPLIER_APPLICATION", "payment_requested_usd"
        ),
        "gc_inspector_routed_document_count": len(
            _decision_parameter(
                summary,
                "S01_A2_GC_INITIAL_REVIEW",
                "inspector_package_document_ids",
            )
        ),
        "gc_initial_backup_action": _decision_parameter(
            summary, "S01_A2_GC_INITIAL_REVIEW", "backup_action"
        ),
        "supplier_cure_plan": _decision_parameter(
            summary, "S01_B1_SUPPLIER_COMMITMENT", "cure_plan"
        ),
        "gc_package_backup_action": _decision_parameter(
            summary, "S01_B2_GC_INTEGRATED_PACKAGE", "backup_action"
        ),
        "supplier_ship_action": _decision_parameter(
            summary, "S01_C1_SUPPLIER_STATUS_AND_RECOVERY", "ship_action"
        ),
        "gc_recovery_plan": _decision_parameter(
            summary, "S01_C2_GC_RECOVERY_PLAN", "recovery_plan"
        ),
    }


def _decision_parameter(summary: dict[str, Any], node_id: str, field: str) -> Any:
    decision = next(
        decision
        for decision in summary["s01_v2_analysis"]["decisions"]
        if decision["node_id"] == node_id
    )
    return decision["parameters"][field]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _content_hash(payload: dict[str, Any]) -> str:
    normalized = dict(payload)
    normalized.pop("content_sha256", None)
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
