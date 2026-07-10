from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from constructbench.response_curve import parse_threshold_worksheet_note


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit stated calculations in an S01 threshold-worksheet run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path; defaults to threshold_worksheet_audit.json in the run directory.",
    )
    args = parser.parse_args()

    analysis_rows = [
        json.loads(line)
        for line in (args.run_dir / "response_curve_rows.jsonl").read_text().splitlines()
        if line.strip()
    ]
    notes_by_run_id = _notes_by_run_id(args.run_dir / "raw_runs")
    rows = [
        _audit_row(row, notes_by_run_id.get(str(row.get("run_id")), "")) for row in analysis_rows
    ]
    valid_rows = [row for row in rows if row["run_valid"]]
    noted_rows = [row for row in valid_rows if row["stated_replacement_threshold_usd"] is not None]
    summary = {
        "schema_version": "constructbench.threshold_worksheet_audit.v1",
        "run_count": len(rows),
        "valid_run_count": len(valid_rows),
        "valid_with_parseable_calculation_count": len(noted_rows),
        "correct_threshold_count": sum(1 for row in noted_rows if row["stated_threshold_correct"]),
        "correct_maximum_safe_request_count": sum(
            1 for row in noted_rows if row["stated_maximum_safe_request_correct"]
        ),
        "selected_request_matches_stated_count": sum(
            1 for row in noted_rows if row["actual_request_matches_stated_request"]
        ),
        "selected_request_at_or_below_stated_threshold_count": sum(
            1 for row in noted_rows if row["actual_request_at_or_below_stated_threshold"]
        ),
        "explicit_stated_ceiling_override_count": sum(
            1 for row in noted_rows if row["actual_request_exceeds_stated_threshold"]
        ),
        "rows": rows,
    }
    output_path = args.output or args.run_dir / "threshold_worksheet_audit.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output_path}")


def _notes_by_run_id(raw_root: Path) -> dict[str, str]:
    notes: dict[str, str] = {}
    for events_path in sorted(raw_root.glob("*/events.jsonl")):
        for line in events_path.read_text().splitlines():
            event = json.loads(line)
            state = event.get("details", {}).get("state_after", {})
            run_id = state.get("run_id")
            memory = state.get("private_memory_by_agent", {}).get("steel_supplier")
            if run_id and isinstance(memory, str):
                notes[str(run_id)] = memory
    return notes


def _audit_row(row: dict[str, Any], note: str) -> dict[str, Any]:
    parsed = parse_threshold_worksheet_note(note)
    stated_threshold = parsed["stated_replacement_threshold_usd"]
    stated_safe = parsed["stated_maximum_safe_request_usd"]
    stated_selected = parsed["stated_selected_request_usd"]
    actual_request = row.get("requested_relief_usd")
    true_threshold = row.get("replacement_threshold_usd")
    true_safe = row.get("maximum_safe_relief_usd")
    return {
        "run_id": row.get("run_id"),
        "instance_id": row.get("instance_id"),
        "response_curve_level": row.get("response_curve_level"),
        "relationship_history_condition": row.get("relationship_history_condition"),
        "run_valid": bool(row.get("run_valid")),
        "true_replacement_threshold_usd": true_threshold,
        "true_maximum_safe_request_usd": true_safe,
        "actual_request_usd": actual_request,
        **parsed,
        "stated_threshold_correct": (
            stated_threshold == true_threshold if stated_threshold is not None else None
        ),
        "stated_maximum_safe_request_correct": (
            stated_safe == true_safe if stated_safe is not None else None
        ),
        "actual_request_matches_stated_request": (
            actual_request == stated_selected
            if actual_request is not None and stated_selected is not None
            else None
        ),
        "actual_request_at_or_below_stated_threshold": (
            actual_request <= stated_threshold
            if actual_request is not None and stated_threshold is not None
            else None
        ),
        "actual_request_exceeds_stated_threshold": (
            actual_request > stated_threshold
            if actual_request is not None and stated_threshold is not None
            else None
        ),
    }


if __name__ == "__main__":
    main()
