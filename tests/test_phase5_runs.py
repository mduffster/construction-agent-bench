import json
from pathlib import Path
from typing import Any, cast

from constructbench.runs import run_batch, run_single

ROOT = Path(__file__).resolve().parents[1]


def test_scripted_single_run_writes_phase5_artifacts(tmp_path: Path) -> None:
    output = run_single(
        project_config_path=ROOT / "configs" / "project_baseline.yaml",
        agent_config_dir=ROOT / "configs" / "agents",
        scenario_config_path=ROOT / "configs" / "scenarios" / "steel_shock.yaml",
        output_root=tmp_path,
        policy_mode="scripted",
        model_id="scripted",
        random_seed=7,
        run_id="run_test_scripted",
        max_tick=9,
    )

    expected_files = {
        "run_config.json",
        "state_snapshots.jsonl",
        "public_ledger.jsonl",
        "private_messages.jsonl",
        "agent_observations.jsonl",
        "agent_submissions.jsonl",
        "agent_beliefs.jsonl",
        "agent_decision_reports.jsonl",
        "contract_breaches.jsonl",
        "oversight_findings.jsonl",
        "trust_updates.jsonl",
        "disclosure_assessments.jsonl",
        "turn_summaries.jsonl",
        "final_metrics.json",
        "analysis_packet.json",
    }
    assert expected_files <= {path.name for path in output.iterdir()}

    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    final_metrics = json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))
    analysis_packet = json.loads((output / "analysis_packet.json").read_text(encoding="utf-8"))

    assert run_config["scenario_id"] == "steel_shock"
    assert run_config["random_seed"] == 7
    assert run_config["breach_profile"] == "easy"
    assert run_config["final_termination_reason"] == "max_tick_reached"
    assert final_metrics["financial_contract"]["cash_shortfall_occurred"] is False
    assert final_metrics["information"]["public_update_count"] == 8
    assert final_metrics["information"]["private_event_count"] == 1
    assert analysis_packet["final_metrics"] == final_metrics

    observations = (output / "agent_observations.jsonl").read_text(encoding="utf-8").splitlines()
    submissions = (output / "agent_submissions.jsonl").read_text(encoding="utf-8").splitlines()
    reports = (output / "agent_decision_reports.jsonl").read_text(encoding="utf-8").splitlines()
    summaries = (output / "turn_summaries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(observations) == 7
    assert len(submissions) == 7
    assert len(reports) == 7
    assert len(summaries) == 9

    first_report = json.loads(reports[0])
    assert {
        "observed_new_info",
        "decision",
        "rationale",
        "decision_parameters_used",
        "belief_update",
        "transitions_applied",
    } <= set(first_report)


def test_batch_run_writes_one_directory_per_combination(tmp_path: Path) -> None:
    outputs = run_batch(
        project_config_path=ROOT / "configs" / "project_baseline.yaml",
        agent_config_dir=ROOT / "configs" / "agents",
        scenario_config_path=ROOT / "configs" / "scenarios" / "steel_shock.yaml",
        output_root=tmp_path,
        policy_mode="scripted",
        model_id="scripted",
        seeds=[1, 2],
        oversight_conditions=["normal_operations", "central_auditor"],
        max_tick=1,
    )

    assert len(outputs) == 4
    assert len(set(outputs)) == 4
    assert all((output / "run_config.json").exists() for output in outputs)


def test_initial_resource_conditions_shift_scripted_outcomes(tmp_path: Path) -> None:
    comfortable = run_single(
        project_config_path=ROOT / "configs" / "project_baseline.yaml",
        agent_config_dir=ROOT / "configs" / "agents",
        scenario_config_path=ROOT / "configs" / "scenarios" / "steel_shock.yaml",
        output_root=tmp_path,
        policy_mode="scripted",
        model_id="scripted",
        random_seed=7,
        condition_overrides={agent: "comfortable" for agent in _agents()},
        run_id="run_comfortable",
        max_tick=8,
    )
    strained = run_single(
        project_config_path=ROOT / "configs" / "project_baseline.yaml",
        agent_config_dir=ROOT / "configs" / "agents",
        scenario_config_path=ROOT / "configs" / "scenarios" / "steel_shock.yaml",
        output_root=tmp_path,
        policy_mode="scripted",
        model_id="scripted",
        random_seed=7,
        condition_overrides={agent: "strained" for agent in _agents()},
        run_id="run_strained",
        max_tick=8,
    )

    comfortable_snapshot = _last_snapshot(comfortable)
    strained_snapshot = _last_snapshot(strained)

    assert comfortable_snapshot["canonical"]["forecast_completion_tick"] < strained_snapshot[
        "canonical"
    ]["forecast_completion_tick"]
    assert comfortable_snapshot["canonical"]["forecast_final_cost"] < strained_snapshot[
        "canonical"
    ]["forecast_final_cost"]
    assert (
        comfortable_snapshot["canonical"]["tasks"]["steel_erection"]["forecast_end_tick"]
        < strained_snapshot["canonical"]["tasks"]["steel_erection"]["forecast_end_tick"]
    )
    assert (
        comfortable_snapshot["canonical"]["tasks"]["steel_delivery"]["forecast_end_tick"]
        < strained_snapshot["canonical"]["tasks"]["steel_delivery"]["forecast_end_tick"]
    )


def _agents() -> list[str]:
    return [
        "owner_developer",
        "general_contractor",
        "steel_supplier",
        "labor_subcontractor",
        "lender",
        "inspector",
    ]


def _last_snapshot(output: Path) -> dict[str, Any]:
    lines = (output / "state_snapshots.jsonl").read_text(encoding="utf-8").splitlines()
    return cast(dict[str, Any], json.loads(lines[-1]))
