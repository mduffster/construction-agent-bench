from __future__ import annotations

import json

import pytest

from constructbench.models import DEFAULT_ANTHROPIC_HAIKU_MODEL
from constructbench.s01_v2_derived_state_packet import (
    CONTROL_CONDITION,
    DERIVED_STATE_PACKET_EXPERIMENT_ID,
    TREATMENT_CONDITION,
)
from scripts import run_s01_v2_derived_state_packet as runner


def _write_run(
    tmp_path,
    *,
    settings: dict,
    commit: str = "abc",
    archival: bool = True,
    cost_known: bool = True,
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "scenario_id": "S01_V2_OFFSITE_STEEL_DRAW",
                "model_settings": settings,
            }
        )
        + "\n"
    )
    (run_dir / "events.jsonl").write_text("{}\n")
    (run_dir / "turn_summaries.jsonl").write_text("{}\n")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "run_manifest": {
                    "archival": archival,
                    "code": {"git_commit": commit},
                    "usage": {"cost_known": cost_known},
                },
                "model_usage_summary": {"total": {"call_count": 6, "cost_usd": 0.12}},
            }
        )
        + "\n"
    )
    return run_dir


def _reference_summary(*, decision_value: int = 950_000, packet_exposed: bool = False) -> dict:
    exposures = (
        [
            {
                "agent_id": "steel_supplier",
                "phase_id": "S01_B1_SUPPLIER_COMMITMENT",
                "hash_matches": True,
            },
            {
                "agent_id": "gc",
                "phase_id": "S01_B2_GC_INTEGRATED_PACKAGE",
                "hash_matches": True,
            },
        ]
        if packet_exposed
        else []
    )
    return {
        "run_valid": True,
        "terminal_status": "PROJECT_SUCCESS",
        "terminal_reason": "all terminal success criteria satisfied",
        "final_project_cost": 95_650_000,
        "completion_tick": 41,
        "cost_components": {"inspection": 45_000},
        "decision_history": [
            {
                "node_id": "S01_B2_GC_INTEGRATED_PACKAGE",
                "parameters": {"final_certified_payment_usd": decision_value},
            }
        ],
        "s01_v2_lineage_transition_history": [
            {"phase_id": "S01_R2_COMMIT_AND_PRODUCE", "lot_b_ready": True}
        ],
        "organization_ledger": {"gc": {"realized_payoff_usd": 780_000}},
        "terminal_values": {"gc": 780_000},
        "s01_v2_analysis": {
            "project_success": True,
            "coalition_success": True,
            "observation_intervention_exposure_count": len(exposures),
            "observation_intervention_exposures": exposures,
            "lineage": {"lineage_complete": True},
        },
        "model_usage_summary": {"total": {"call_count": 0, "cost_usd": 0}},
    }


def test_study_sequence_is_frozen_abbaab_with_paired_seeds() -> None:
    assert [condition for condition, _ in runner.STUDY_SEQUENCE] == [
        CONTROL_CONDITION,
        TREATMENT_CONDITION,
        TREATMENT_CONDITION,
        CONTROL_CONDITION,
        CONTROL_CONDITION,
        TREATMENT_CONDITION,
    ]
    assert [replicate for _, replicate in runner.STUDY_SEQUENCE] == [0, 0, 1, 1, 2, 2]
    assert {
        condition: sorted(
            replicate
            for row_condition, replicate in runner.STUDY_SEQUENCE
            if row_condition == condition
        )
        for condition in {CONTROL_CONDITION, TREATMENT_CONDITION}
    } == {
        CONTROL_CONDITION: [0, 1, 2],
        TREATMENT_CONDITION: [0, 1, 2],
    }


def test_budget_defaults_reserve_all_six_runs_below_both_caps() -> None:
    budget = runner.StudyBudget()

    budget.validate()

    assert budget.requested_reserve_usd() == pytest.approx(1.02)
    assert budget.program_prior_cost_usd + budget.requested_reserve_usd() == pytest.approx(9.496765)
    assert budget.user_limit_reserve_usd == pytest.approx(0.5)
    budget.assert_can_start(spent_new_usd=0.85)
    with pytest.raises(RuntimeError, match="new-model allocation stop"):
        budget.assert_can_start(spent_new_usd=0.850001)


def test_budget_rejects_a_seventh_reserved_dispatch() -> None:
    with pytest.raises(ValueError, match="requested run reserve"):
        runner.StudyBudget().validate(run_count=7)


def test_model_settings_freeze_arm_order_seed_and_packet_contract() -> None:
    settings = runner._model_settings(
        condition=TREATMENT_CONDITION,
        replicate_index=1,
        sequence_index=2,
    )

    assert settings["experiment_id"] == DERIVED_STATE_PACKET_EXPERIMENT_ID
    assert settings["experiment_condition"] == TREATMENT_CONDITION
    assert settings["replicate_index"] == 1
    assert settings["sequence_index"] == 2
    assert settings["seed"] == 1
    assert settings["temperature"] == 0.0
    assert settings["max_tokens"] == 1200
    assert settings["repair_budget"] == 1
    assert settings["live_agent_ids"] == ["steel_supplier", "gc"]
    assert settings["packet_intervention_nodes"] == [
        "S01_B1_SUPPLIER_COMMITMENT",
        "S01_B2_GC_INTEGRATED_PACKAGE",
    ]
    assert settings["study_sequence"] == [condition for condition, _ in runner.STUDY_SEQUENCE]


def test_live_settings_require_explicit_opt_in_and_frozen_configuration() -> None:
    with pytest.raises(SystemExit, match="requires --allow-live-batch"):
        runner._validate_live_settings(
            model=DEFAULT_ANTHROPIC_HAIKU_MODEL,
            temperature=0.0,
            max_tokens=1200,
            repair_budget=1,
            allow_live_batch=False,
        )
    with pytest.raises(ValueError, match="temperature 0"):
        runner._validate_live_settings(
            model=DEFAULT_ANTHROPIC_HAIKU_MODEL,
            temperature=1.0,
            max_tokens=1200,
            repair_budget=1,
            allow_live_batch=True,
        )


def test_reference_gate_requires_success_lineage_and_consequence_inertness() -> None:
    control = _reference_summary()
    treatment = _reference_summary(packet_exposed=True)

    passed = runner._reference_gate(control, treatment)
    treatment["decision_history"][0]["parameters"]["final_certified_payment_usd"] = 760_000
    failed = runner._reference_gate(control, treatment)

    assert passed["passed"] is True
    assert passed["checks"]["control_has_no_packet_exposure"] is True
    assert passed["checks"]["treatment_has_exact_packet_exposures"] is True
    assert passed["checks"]["treatment_packet_hashes_match"] is True
    assert passed["checks"]["packet_is_consequence_inert"] is True
    assert failed["passed"] is False
    assert failed["checks"]["packet_is_consequence_inert"] is False


def test_reference_gate_rejects_missing_misdirected_or_bad_hash_exposure() -> None:
    control = _reference_summary()
    treatment = _reference_summary(packet_exposed=True)
    treatment["s01_v2_analysis"]["observation_intervention_exposures"][1]["phase_id"] = (
        "S01_C2_GC_RECOVERY_PLAN"
    )
    treatment["s01_v2_analysis"]["observation_intervention_exposures"][0]["hash_matches"] = False

    gate = runner._reference_gate(control, treatment)

    assert gate["passed"] is False
    assert gate["checks"]["treatment_has_exact_packet_exposures"] is False
    assert gate["checks"]["treatment_packet_hashes_match"] is False


def test_resume_accepts_only_exact_archival_known_cost_run(tmp_path) -> None:
    settings = runner._model_settings(
        condition=CONTROL_CONDITION,
        replicate_index=0,
        sequence_index=0,
    )
    run_dir = _write_run(tmp_path, settings=settings)

    summary = runner._validate_existing_run(
        run_dir,
        expected_settings=settings,
        current_commit="abc",
        require_archival=True,
    )

    assert summary["run_manifest"]["usage"]["cost_known"] is True


@pytest.mark.parametrize("mismatch", ["scenario", "settings", "commit", "cost", "archival"])
def test_resume_rejects_incompatible_run(tmp_path, mismatch: str) -> None:
    settings = runner._model_settings(
        condition=CONTROL_CONDITION,
        replicate_index=0,
        sequence_index=0,
    )
    run_dir = _write_run(
        tmp_path,
        settings=settings,
        commit="wrong" if mismatch == "commit" else "abc",
        archival=mismatch != "archival",
        cost_known=mismatch != "cost",
    )
    if mismatch == "scenario":
        config = json.loads((run_dir / "run_config.json").read_text())
        config["scenario_id"] = "S01_STEEL_MARKET_SHOCK"
        (run_dir / "run_config.json").write_text(json.dumps(config) + "\n")
    expected_settings = settings if mismatch != "settings" else {"condition": "wrong"}

    with pytest.raises(RuntimeError):
        runner._validate_existing_run(
            run_dir,
            expected_settings=expected_settings,
            current_commit="abc",
            require_archival=True,
        )


def test_resume_rejects_extra_output_files(tmp_path) -> None:
    settings = runner._model_settings(
        condition=CONTROL_CONDITION,
        replicate_index=0,
        sequence_index=0,
    )
    run_dir = _write_run(tmp_path, settings=settings)
    (run_dir / "unexpected.json").write_text("{}\n")

    with pytest.raises(RuntimeError, match="output contract"):
        runner._validate_existing_run(
            run_dir,
            expected_settings=settings,
            current_commit="abc",
            require_archival=True,
        )


def test_existing_runs_must_form_exact_sequence_prefix(tmp_path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    condition, replicate = runner.STUDY_SEQUENCE[1]
    later = run_root / runner._run_dir_name(
        sequence_index=1,
        condition=condition,
        replicate_index=replicate,
    )
    later.mkdir()
    (later / "run_summary.json").write_text("{}\n")

    with pytest.raises(RuntimeError, match="exact sequence prefix"):
        runner._validate_existing_prefix(run_root)


def test_existing_prefix_rejects_partial_and_unexpected_run_directories(tmp_path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    condition, replicate = runner.STUDY_SEQUENCE[0]
    first = run_root / runner._run_dir_name(
        sequence_index=0,
        condition=condition,
        replicate_index=replicate,
    )
    first.mkdir()
    (first / "events.jsonl").write_text("{}\n")

    with pytest.raises(RuntimeError, match="partial run directory"):
        runner._validate_existing_prefix(run_root)

    (first / "run_summary.json").write_text("{}\n")
    extra = run_root / "99_extra"
    extra.mkdir()
    (extra / "run_summary.json").write_text("{}\n")
    with pytest.raises(RuntimeError, match="unexpected run summaries"):
        runner._validate_existing_prefix(run_root)


def test_study_manifest_rejects_incompatible_resume(tmp_path) -> None:
    kwargs = {
        "current_commit": "abc",
        "budget": runner.StudyBudget(),
        "model": DEFAULT_ANTHROPIC_HAIKU_MODEL,
        "temperature": 0.0,
        "max_tokens": 1200,
        "repair_budget": 1,
    }
    runner._write_or_validate_manifest(tmp_path, **kwargs)
    runner._write_or_validate_manifest(tmp_path, **kwargs)

    with pytest.raises(RuntimeError, match="manifest mismatch"):
        runner._write_or_validate_manifest(
            tmp_path,
            **{**kwargs, "max_tokens": 1000},
        )


def test_progress_writes_rows_aggregate_and_program_ledger(tmp_path, monkeypatch) -> None:
    rows = [
        {"condition": CONTROL_CONDITION, "model_cost_usd": 0.11},
        {"condition": TREATMENT_CONDITION, "model_cost_usd": 0.12},
    ]
    monkeypatch.setattr(
        runner,
        "aggregate_study_rows",
        lambda values: {"run_count": len(values), "contrast": "descriptive"},
    )

    runner._write_progress(
        tmp_path,
        rows=rows,
        budget=runner.StudyBudget(),
        current_commit="abc",
        stop_reason=None,
    )

    analysis = json.loads((tmp_path / "study_analysis.json").read_text())
    persisted_rows = [
        json.loads(line) for line in (tmp_path / "study_rows.jsonl").read_text().splitlines()
    ]
    assert persisted_rows == rows
    assert analysis["completed_run_count"] == 2
    assert analysis["new_model_cost_usd"] == pytest.approx(0.23)
    assert analysis["program_cumulative_cost_usd"] == pytest.approx(8.706765)
    assert analysis["program_cost_projected_from_reserve_usd"] == pytest.approx(9.496765)
    assert analysis["aggregate"] == {"run_count": 2, "contrast": "descriptive"}


def test_aggregate_advances_on_joint_coalition_without_backup_outcome() -> None:
    rows = []
    for sequence_index, (condition, replicate_index) in enumerate(runner.STUDY_SEQUENCE):
        treatment_success = condition == TREATMENT_CONDITION and replicate_index == 0
        rows.append(
            {
                "condition": condition,
                "replicate_index": replicate_index,
                "sequence_index": sequence_index,
                "run_valid": True,
                "project_success": True,
                "coalition_success": True,
                "backup_activated": not treatment_success,
                "joint_efficient_outcome": treatment_success,
                "target_decision_pair": treatment_success,
                "b1_cure_plan": ("FULL_SEQUENCE_CURE" if treatment_success else "LOT_A_CURE"),
                "b2_backup_action": "DROP" if treatment_success else "MAINTAIN",
                "r2_full_sequence_ready": treatment_success,
                "c1_ship_action": "SHIP_BOTH" if treatment_success else "SHIP_A",
                "lineage_complete": True,
                "packet_exposure_audit_passed": True,
                "repair_attempt_count": 0,
                "final_project_cost": 95_650_000,
                "completion_tick": 41,
                "model_cost_usd": 0.1,
            }
        )

    aggregate = runner.aggregate_study_rows(rows)

    control = aggregate["by_condition"][CONTROL_CONDITION]
    treatment = aggregate["by_condition"][TREATMENT_CONDITION]
    assert control["coalition_success_count"] == 3
    assert control["backup_activation_count"] == 3
    assert control["joint_efficient_outcome_count"] == 0
    assert treatment["joint_efficient_outcome_count"] == 1
    assert treatment["target_decision_pair_count"] == 1
    assert aggregate["advancement_checks"]["treatment_joint_outcome_strictly_higher"] is True
    assert aggregate["advance_to_broader_confirmation"] is True
