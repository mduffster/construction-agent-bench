from __future__ import annotations

import json

import pytest

from constructbench.agents import policies_for_fixture
from constructbench.baseline import normal_project_plan
from constructbench.manifest import canonical_json_sha256
from constructbench.models import LLMPolicy
from constructbench.replay import replay_run
from constructbench.runner import run_fixture, run_policy


class FakeUsageAdapter:
    model = "claude-haiku-4-5-20251001"

    def __init__(self, response: str, usage: dict[str, int]) -> None:
        self.response = response
        self.usage = usage

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.response

    def drain_usage(self) -> dict[str, int]:
        return self.usage


def test_normal_run_outputs_exactly_four_files(tmp_path) -> None:
    output_dir = tmp_path / "run"
    run_fixture("S01", "normal_success", output_dir=output_dir)

    assert {path.name for path in output_dir.iterdir()} == {
        "run_config.json",
        "events.jsonl",
        "turn_summaries.jsonl",
        "run_summary.json",
    }


def test_run_manifest_fields_are_written_for_fixture_run(tmp_path) -> None:
    output_dir = tmp_path / "run"
    run_fixture("S01", "normal_success", output_dir=output_dir)

    config = json.loads((output_dir / "run_config.json").read_text())
    summary = json.loads((output_dir / "run_summary.json").read_text())

    assert config["run_manifest"]["schema_version"] == "constructbench.run_manifest.v1"
    assert summary["run_manifest"]["schema_version"] == "constructbench.run_manifest.v1"
    assert summary["run_manifest"]["scenario"]["scenario_key"] == "S01"
    assert summary["run_manifest"]["scenario"]["scenario_class_name"] == "S01SteelMarketShock"
    assert summary["run_manifest"]["scenario"]["fixture_name"] == "normal_success"
    assert summary["run_manifest"]["outputs"].keys() == {
        "run_config.json",
        "events.jsonl",
        "turn_summaries.jsonl",
    }
    assert config["run_manifest"]["outputs"] == {}
    assert summary["payoff_ledger"]["schema_version"] == "constructbench.payoff.v1"


def test_manifest_hash_changes_when_baseline_content_changes() -> None:
    baseline = normal_project_plan("normal")
    changed = json.loads(json.dumps(baseline))
    changed["budget_constraints"]["baseline_project_cost"] += 1

    assert canonical_json_sha256(baseline) != canonical_json_sha256(changed)


def test_run_manifest_records_fake_model_usage_and_cost(tmp_path) -> None:
    supplier_response = json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": "current_expedited",
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": None,
                    "parameters": {
                        "price_amendment_request": 0,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                    },
                },
            ],
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Preserve the original delivery date.",
        }
    )
    fixture_decisions = {
        "S01_GC_PROCUREMENT_PLAN": ("accept_selected_plan", {}),
        "S01_LABOR_MOBILIZATION": ("flexible_hold", {}),
    }
    policies = policies_for_fixture(fixture_decisions)
    policies["steel_supplier"] = LLMPolicy(
        FakeUsageAdapter(
            supplier_response,
            {"input_tokens": 10, "output_tokens": 5},
        ),
        "steel_supplier",
    )

    output_dir = tmp_path / "run"
    run_policy(
        "S01",
        "normal",
        policies,
        output_dir=output_dir,
        model_settings={
            "policy": "llm",
            "provider": "fake",
            "model": "claude-haiku-4-5-20251001",
        },
    )

    summary = json.loads((output_dir / "run_summary.json").read_text())
    manifest = summary["run_manifest"]

    assert manifest["usage"]["call_count"] == 1
    assert manifest["usage"]["input_tokens"] == 10
    assert manifest["usage"]["output_tokens"] == 5
    assert manifest["usage"]["cost_usd"] == pytest.approx(0.000035)
    assert manifest["usage"]["cost_known"] is True
    assert manifest["model"]["adapter_class"] == "FakeUsageAdapter"
    assert manifest["model"]["prompt_style"] == "anthropic_structured"


def test_event_replay_reconstructs_final_state(tmp_path) -> None:
    output_dir = tmp_path / "run"
    result = run_fixture("S04", "stressed_success", output_dir=output_dir)

    replayed = replay_run(output_dir)

    assert replayed.model_dump(mode="json") == result.final_state.model_dump(mode="json")
