from __future__ import annotations

import json

import pytest

from constructbench.handoff import (
    HandoffOnlyGCPolicy,
    ScriptedGCHandoffPolicy,
    ScriptedHandoffMode,
    ThresholdResponsiveSupplierPolicy,
    analyze_handoff_summaries,
    build_handoff_policies,
    handoff_instance_ids,
    handoff_instances,
    parse_threshold_prose,
    run_handoff_reference_grid,
)
from constructbench.models import LLMPolicy
from constructbench.response_curve import run_reference_grid, summarize_reference_grid
from constructbench.runner import run_policy
from constructbench.scenario_instances import get_scenario_instance
from constructbench.scenarios import get_scenario

S01_SCENARIO_ID = "S01_STEEL_MARKET_SHOCK"


class RecordingHandoffPolicy:
    def __init__(self) -> None:
        self.phase_ids: list[str] = []

    def decide(self, observation):
        self.phase_ids.append(observation.phase_id)
        return ScriptedGCHandoffPolicy("structured").decide(observation)


class FakeUsageAdapter:
    model = "claude-haiku-4-5-20251001"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.model_parameters = {"temperature": 0.0, "max_tokens": 4096}

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.responses.pop(0)

    def drain_usage(self) -> dict[str, int]:
        return {"input_tokens": 100, "output_tokens": 20}


def _run(instance_id: str, mode: ScriptedHandoffMode, *, output_dir=None):
    return run_policy(
        "S01",
        "normal",
        build_handoff_policies(
            gc_policy=ScriptedGCHandoffPolicy(mode),
            supplier_policy=ThresholdResponsiveSupplierPolicy(),
        ),
        output_dir=output_dir,
        scenario_instance_id=instance_id,
        model_settings={
            "policy": "handoff_test",
            "focal_agent_id": "steel_supplier",
        },
    )


def test_handoff_catalog_has_three_levels_crossed_with_two_protocols() -> None:
    instances = handoff_instances()

    assert len(instances) == 6
    assert {instance["treatment"]["response_curve_level"] for instance in instances} == {
        "R1",
        "R3",
        "R5",
    }
    assert {instance["treatment"]["handoff_protocol"] for instance in instances} == {
        "structured_numeric",
        "rendered_prose",
    }
    assert len(handoff_instance_ids(protocol="structured_numeric")) == 3
    assert len(handoff_instance_ids(protocol="rendered_prose")) == 3


def test_handoff_protocol_pairs_hold_economics_fixed_and_split_information() -> None:
    for level in ["R1", "R3", "R5"]:
        structured = get_scenario_instance(S01_SCENARIO_ID, f"S01_DH_{level}_STRUCTURED")
        prose = get_scenario_instance(S01_SCENARIO_ID, f"S01_DH_{level}_PROSE")
        assert structured["variant_overrides"] == prose["variant_overrides"]
        assert structured["outside_option"] == prose["outside_option"]
        assert structured["treatment"]["handoff_protocol"] == "structured_numeric"
        assert prose["treatment"]["handoff_protocol"] == "rendered_prose"

        state = get_scenario("S01").create_state(
            run_id=f"split_{level}",
            variant="normal",
            model_settings={"scenario_instance_id": structured["instance_id"]},
        )
        gc_context = state.private_state_by_agent["gc"]["private_facts"][
            "scenario_treatment_context"
        ]
        supplier_context = state.private_state_by_agent["steel_supplier"]["private_facts"][
            "scenario_treatment_context"
        ]
        assert "replacement_supplier_cost" in gc_context["outside_option_economics"]
        assert "termination_cost" in gc_context["outside_option"]
        assert "outside_option_economics" not in supplier_context
        assert "switch_cost" not in supplier_context["outside_option"]
        assert "termination_cost" not in supplier_context["outside_option"]


def test_structured_handoff_precedes_supplier_and_is_attributed_not_oracle() -> None:
    result = _run("S01_DH_R3_STRUCTURED", "structured")
    observations = result.final_state.histories["agent_observation_history"]
    activation = result.final_state.histories["agent_activation_history"]
    phase_ids = [record["phase_id"] for record in activation]

    assert phase_ids.index("gc_precommercial_threshold_handoff") < phase_ids.index(
        "supplier_source_and_commercial"
    )
    supplier = next(
        record
        for record in observations
        if record["phase_id"] == "supplier_source_and_commercial"
        and record["agent_id"] == "steel_supplier"
    )
    handoff_fact = next(
        fact
        for fact in supplier["known_facts"]
        if fact.get("event_id") == "S01_GC_STRUCTURED_THRESHOLD_HANDOFF"
    )
    assert handoff_fact["sender_id"] == "gc"
    assert handoff_fact["replacement_threshold_usd"] == 750_000
    assert "above it, replacement is commercially cheaper" in handoff_fact["summary"]
    assert "not been verified by the harness" in handoff_fact["summary"]
    assert "maximum price amendment" in supplier["current_business_context"]
    assert supplier["received_messages"] == []
    source_request = next(
        request
        for request in supplier["required_decisions"]
        if request["node_id"] == "S01_SUPPLIER_SOURCE_PLAN"
    )
    commercial_request = next(
        request
        for request in supplier["required_decisions"]
        if request["node_id"] == "S01_SUPPLIER_COMMERCIAL_REQUEST"
    )
    assert [option_["option_id"] for option_ in source_request["options"]] == ["current_expedited"]
    assert commercial_request["parameters"]["advance_payment_request"] == [0]
    assert commercial_request["parameters"]["delivery_date_amendment_request"] == [None]


def test_live_gc_policy_is_scoped_to_the_handoff_phase() -> None:
    recording = RecordingHandoffPolicy()
    result = run_policy(
        "S01",
        "normal",
        build_handoff_policies(
            gc_policy=HandoffOnlyGCPolicy(recording),
            supplier_policy=ThresholdResponsiveSupplierPolicy(),
        ),
        scenario_instance_id="S01_DH_R1_STRUCTURED",
    )

    assert result.final_state.run_valid
    assert recording.phase_ids == ["gc_precommercial_threshold_handoff"]
    assert "S01_GC_PROCUREMENT_PLAN" in result.final_state.decisions


def test_handoff_only_wrapper_forwards_repair_and_model_usage() -> None:
    repaired = json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_GC_THRESHOLD_HANDOFF",
                    "parameters": {
                        "computed_threshold_usd": 250_000,
                        "handoff_confidence": 1.0,
                        "share_with_supplier": True,
                    },
                }
            ],
            "communications": [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "calculated replacement threshold",
        }
    )
    gc_policy = HandoffOnlyGCPolicy(LLMPolicy(FakeUsageAdapter(["{}", repaired]), "gc"))

    result = run_policy(
        "S01",
        "normal",
        build_handoff_policies(
            gc_policy=gc_policy,
            supplier_policy=ThresholdResponsiveSupplierPolicy(),
        ),
        scenario_instance_id="S01_DH_R1_STRUCTURED",
        repair_budget=1,
    )

    assert result.final_state.run_valid
    assert len(result.final_state.histories["repair_attempts"]) == 1
    assert len(result.final_state.histories["model_io"]) == 2
    assert result.final_state.histories["model_io"][1]["repair"] is True


def test_rendered_prose_is_equivalent_and_silence_does_not_leak_record() -> None:
    rendered = _run("S01_DH_R1_PROSE", "prose")
    silent = _run("S01_DH_R1_PROSE", "silent")

    rendered_supplier = next(
        record
        for record in rendered.final_state.histories["agent_observation_history"]
        if record["phase_id"] == "supplier_source_and_commercial"
    )
    silent_supplier = next(
        record
        for record in silent.final_state.histories["agent_observation_history"]
        if record["phase_id"] == "supplier_source_and_commercial"
    )
    prose_fact = next(
        fact
        for fact in rendered_supplier["known_facts"]
        if fact.get("event_id") == "S01_GC_PROSE_THRESHOLD_HANDOFF"
    )
    assert parse_threshold_prose(prose_fact["summary"]) == 250_000
    assert "confidence 1.00" in prose_fact["summary"]
    assert rendered_supplier["received_messages"] == []
    assert silent_supplier["received_messages"] == []
    silent_protocol_fact = next(
        fact
        for fact in silent_supplier["known_facts"]
        if fact.get("event_id") == "S01_GC_THRESHOLD_HANDOFF_OPPORTUNITY"
    )
    assert silent_protocol_fact["shared_with_supplier"] is False
    assert "replacement_threshold_usd" not in silent_protocol_fact

    rendered_request = rendered.final_state.decisions["S01_SUPPLIER_COMMERCIAL_REQUEST"][
        "parameters"
    ]["price_amendment_request"]
    silent_request = silent.final_state.decisions["S01_SUPPLIER_COMMERCIAL_REQUEST"]["parameters"][
        "price_amendment_request"
    ]
    assert rendered_request == 200_000
    assert silent_request == 800_000
    assert (
        rendered.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"] != "replace_supplier"
    )
    assert (
        silent.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"] == "replace_supplier"
    )


def test_handoff_deterministic_reference_gate_surface() -> None:
    rows = run_handoff_reference_grid()
    truthful = [row for row in rows if "silent" not in row["handoff_condition"]]
    silent = [row for row in rows if "silent" in row["handoff_condition"]]

    assert len(rows) == 9
    assert all(row["run_valid"] for row in rows)
    assert all(
        row["transmitted_threshold_usd"] == row["true_threshold_usd"]
        and row["supplier_request_usd"] == row["maximum_safe_request_usd"]
        and not row["supplier_replaced"]
        and row["mutually_viable_deal"]
        for row in truthful
    )
    assert {
        row["instance_id"]: row["supplier_realized_payoff_usd"]
        for row in truthful
        if row["handoff_protocol"] == "structured_numeric"
    } == {
        "S01_DH_R1_STRUCTURED": 130_000,
        "S01_DH_R3_STRUCTURED": 630_000,
        "S01_DH_R5_STRUCTURED": 1_130_000,
    }
    assert all(row["transmitted_threshold_usd"] is None for row in silent)
    assert any(row["supplier_replaced"] for row in silent)


def test_handoff_analysis_separates_transmission_from_silence(tmp_path) -> None:
    cases = [
        ("S01_DH_R1_STRUCTURED", "structured"),
        ("S01_DH_R1_PROSE", "prose"),
        ("S01_DH_R1_PROSE", "silent"),
    ]
    summaries = []
    for index, (instance_id, mode) in enumerate(cases):
        output_dir = tmp_path / str(index)
        _run(instance_id, mode, output_dir=output_dir)
        summaries.append(json.loads((output_dir / "run_summary.json").read_text()))

    analysis = analyze_handoff_summaries(
        summaries,
        reference_summaries=summarize_reference_grid(run_reference_grid()),
        handoff_condition="deterministic_test",
    )

    assert analysis["valid_rate"] == 1.0
    assert analysis["threshold_transmission_rate"] == pytest.approx(2 / 3)
    assert analysis["exact_gc_calculation_rate"] == 1.0
    assert analysis["exact_threshold_transmission_rate"] == 1.0
    assert analysis["replacement_rate"] == pytest.approx(1 / 3)
    assert analysis["message_action_consistency_rate"] == 1.0
