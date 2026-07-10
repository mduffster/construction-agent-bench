from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "src" / "game-data" / "s01_research_program.json"
HANDOFF_REPORT = ROOT / "docs" / "s01_distributed_threshold_handoff_results.md"
MULTIPLAYER_REPORT = ROOT / "docs" / "s01_v2_multiplayer_bridge_results.md"
PACKET_REPORT = ROOT / "docs" / "s01_v2_derived_state_packet_results.md"


def test_research_program_web_export_is_public_and_traceable() -> None:
    payload = json.loads(WEB_DATA.read_text())
    serialized = json.dumps(payload, sort_keys=True)
    normalized = dict(payload)
    content_hash = normalized.pop("content_sha256")

    assert payload["schema_version"] == "constructsim.web_research_program.v2"
    assert content_hash == hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert payload["source"]["handoff_report_sha256"] == _sha256(HANDOFF_REPORT)
    assert payload["source"]["multiplayer_report_sha256"] == _sha256(
        MULTIPLAYER_REPORT
    )
    assert payload["source"]["packet_report_sha256"] == _sha256(PACKET_REPORT)
    assert "model_cost" not in serialized
    assert "program_cumulative_cost" not in serialized


def test_research_program_web_export_matches_frozen_findings() -> None:
    payload = json.loads(WEB_DATA.read_text())
    handoff = payload["handoff"]
    multiplayer = payload["multiplayer"]

    assert handoff["assigned_run_count"] == 150
    assert handoff["valid_run_count"] == 146
    assert handoff["exact_live_calculation_count"] == 18
    assert handoff["safe_action_given_exact_count"] == 18
    assert handoff["end_to_end_success_given_exact_count"] == 18
    arms = {arm["arm_id"]: arm for arm in handoff["arms"]}
    assert arms["scripted-structured"]["end_to_end_success_rate"] == 1
    assert arms["scripted-prose"]["end_to_end_success_rate"] == pytest.approx(14 / 15)
    assert arms["live-prose"]["end_to_end_success_rate"] == 0.3
    assert arms["live-structured"]["end_to_end_success_rate"] == 0.3

    assert multiplayer["completed_stage_count"] == 4
    assert multiplayer["stop_reason"] is None
    assert multiplayer["expected_exposure_count"] == 6
    assert multiplayer["operative_link_count"] == 7
    assert multiplayer["live_decision_count"] == 48
    assert multiplayer["first_pass_live_decision_count"] == 45
    assert multiplayer["repair_attempt_count"] == 3
    assert all(row["run_valid"] for row in multiplayer["rows"])
    assert all(row["project_success"] for row in multiplayer["rows"])
    assert not any(row["coalition_success"] for row in multiplayer["rows"])
    assert all(row["lineage_complete"] for row in multiplayer["rows"])
    assert multiplayer["reference"]["final_project_cost"] == 95_650_000
    assert multiplayer["reference"]["completion_tick"] == 41
    assert multiplayer["project_cost_min"] == 100_260_000
    assert multiplayer["project_cost_max"] == 100_310_000
    assert multiplayer["common_live_path"]["gc_inspector_routed_document_count"] == 4
    assert multiplayer["common_live_path"]["supplier_cure_plan"] == "LOT_A_CURE"
    assert multiplayer["common_live_path"]["gc_recovery_plan"] == "ACTIVATE_BACKUP"

    packet = payload["decision_packet"]
    control = packet["control"]
    treatment = packet["treatment"]
    assert packet["assigned_run_count"] == 6
    assert packet["valid_run_count"] == 6
    assert packet["repair_attempt_count"] == 0
    assert packet["lineage_complete_count"] == 6
    assert packet["paired_period_count"] == 3
    assert packet["paired_treatment_win_count"] == 3
    assert control["full_sequence_cure_count"] == 0
    assert treatment["full_sequence_cure_count"] == 3
    assert control["backup_activation_count"] == 3
    assert treatment["backup_activation_count"] == 0
    assert control["coalition_success_count"] == 0
    assert treatment["coalition_success_count"] == 3
    assert control["mean_completion_tick"] == 45
    assert treatment["mean_completion_tick"] == 41
    assert control["mean_final_project_cost"] == 100_310_000
    assert treatment["mean_final_project_cost"] == 96_093_333
    assert packet["mean_project_cost_difference_usd"] == 4_216_667
    assert packet["mean_completion_tick_difference"] == 4
    assert packet["advancement_gate_passed"] is True
    assert packet["accounting_replay"] == {
        "model_call_count": 0,
        "all_decisions_identical": True,
        "all_project_outcomes_identical": True,
        "source_code_commit": "a797246f8a3fdc8e027d8ddc91a0a14c5fd6650f",
        "replay_code_commit": "da13b40b380b117392eeba3bd4d1087574aa22a7",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
