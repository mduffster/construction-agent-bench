from __future__ import annotations

import json

from constructbench.agents import ReplayPolicy, replay_submissions_for_agent
from constructbench.focal import S01_COMMERCIAL_NEUTRAL_POLICY_ID, build_focal_policies
from constructbench.models import LLMPolicy
from constructbench.runner import run_policy
from constructbench.state import (
    AGENT_IDS,
    AgentSubmission,
    AssessmentReview,
    DecisionSelection,
)


class FakeAdapter:
    model = "fake-focal-model"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.responses.pop(0)


def _supplier_response(
    source_plan: str = "current_expedited",
    communications: list[dict] | None = None,
    price_amendment_request: int = 0,
) -> str:
    return json.dumps(
        {
            "decisions": [
                {
                    "node_id": "S01_SUPPLIER_SOURCE_PLAN",
                    "option_id": source_plan,
                    "parameters": {},
                },
                {
                    "node_id": "S01_SUPPLIER_COMMERCIAL_REQUEST",
                    "option_id": None,
                    "parameters": {
                        "price_amendment_request": price_amendment_request,
                        "delivery_date_amendment_request": None,
                        "advance_payment_request": 0,
                        "claimed_incremental_cost_usd": 800_000,
                        "claimed_liquidity_requirement_usd": 0,
                        "claimed_on_time_probability": 1.0,
                    },
                },
            ],
            "communications": communications or [],
            "assessment_updates": [],
            "assessment_reviews": [],
            "private_notes": "Focal supplier submission for deterministic test.",
        }
    )


def _focal_supplier_policies(
    source_plan: str = "current_expedited",
    communications: list[dict] | None = None,
    price_amendment_request: int = 0,
):
    focal_policy = LLMPolicy(
        FakeAdapter(
            [_supplier_response(source_plan, communications, price_amendment_request)]
        ),
        "steel_supplier",
    )
    return build_focal_policies("S01", "steel_supplier", focal_policy)


def _focal_model_settings(focal_agent_id: str = "steel_supplier") -> dict[str, str]:
    return {
        "policy": "focal",
        "provider": "fake",
        "model": "fake-focal-model",
        "focal_agent_id": focal_agent_id,
        "counterparty_policy_id": S01_COMMERCIAL_NEUTRAL_POLICY_ID,
    }


def test_focal_supplier_run_uses_only_focal_model_calls_and_writes_manifest(tmp_path) -> None:
    output_dir = tmp_path / "focal_run"
    result = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies(),
        output_dir=output_dir,
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )
    state = result.final_state
    model_io = state.histories["model_io"]
    config = json.loads((output_dir / "run_config.json").read_text())
    summary = json.loads((output_dir / "run_summary.json").read_text())

    assert state.run_valid
    assert state.terminal_status == "PROJECT_SUCCESS"
    assert model_io
    assert {record["agent_id"] for record in model_io} == {"steel_supplier"}
    assert {path.name for path in output_dir.iterdir()} == {
        "run_config.json",
        "events.jsonl",
        "turn_summaries.jsonl",
        "run_summary.json",
    }
    for payload in [config, summary]:
        manifest_run = payload["run_manifest"]["run"]
        assert manifest_run["policy_mode"] == "focal"
        assert manifest_run["focal_agent_id"] == "steel_supplier"
        assert manifest_run["counterparty_policy_id"] == S01_COMMERCIAL_NEUTRAL_POLICY_ID
        assert manifest_run["focal_policy_provider"] == "fake"
        assert manifest_run["focal_policy_model"] == "fake-focal-model"


def test_replay_policy_reproduces_focal_supplier_downstream_state() -> None:
    original = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies(),
        scenario_instance_id="S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )
    replay_policy = ReplayPolicy(
        replay_submissions_for_agent(original.final_state, "steel_supplier")
    )
    replay = run_policy(
        "S01",
        "normal",
        build_focal_policies("S01", "steel_supplier", replay_policy),
        scenario_instance_id="S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK",
        model_settings={
            **_focal_model_settings(),
            "provider": "replay",
            "model": "replay",
        },
    )

    assert replay.final_state.run_valid
    assert replay.final_state.histories["model_io"] == []
    assert replay.final_state.canonical_state == original.final_state.canonical_state


def test_focal_role_rotation_interface_and_gc_focal_smoke() -> None:
    for agent_id in AGENT_IDS:
        focal_policy = ReplayPolicy({})
        policies = build_focal_policies("S01", agent_id, focal_policy)
        assert set(policies) == set(AGENT_IDS)
        assert policies[agent_id] is focal_policy

    gc_policy = ReplayPolicy(
        {
            ("source_response", "gc"): AgentSubmission(
                decisions=[
                    DecisionSelection(
                        node_id="S01_GC_PROCUREMENT_PLAN",
                        option_id="accept_selected_plan",
                    )
                ]
            ),
            ("final_assessment", "gc"): AgentSubmission(
                assessment_reviews=[
                    AssessmentReview(
                        evidence_ids=["S01_DELIVERY_OUTCOME"],
                        counterparty_ids=["steel_supplier", "gc", "labor_subcontractor"],
                        reason="GC replay policy records no assessment update.",
                    )
                ]
            ),
        }
    )
    result = run_policy(
        "S01",
        "normal",
        build_focal_policies("S01", "gc", gc_policy),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings("gc"),
    )

    assert result.final_state.run_valid
    assert result.final_state.terminal_status == "PROJECT_SUCCESS"
    assert result.final_state.histories["model_io"] == []


def test_commercially_neutral_gc_uses_outside_option_economics() -> None:
    weak = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies("current_standard"),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )
    credible = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies("current_standard"),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_CREDIBLE",
        model_settings=_focal_model_settings(),
    )

    weak_gc = weak.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"]
    credible_gc = credible.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"]
    scenario_instance = credible.final_state.canonical_state["scenario"]["scenario_instance"]

    assert weak_gc == "resequence_around_delivery"
    assert credible_gc == "replace_supplier"
    assert scenario_instance["outside_option_economics"]["replacement_supplier_cost"] == 150_000
    assert "outside_option_economics" not in credible.final_state.canonical_state[
        "scenario"
    ]["scenario_instance_public_context"]


def test_neutral_gc_replaces_only_when_replacement_is_cheaper_than_keeping() -> None:
    # Credible cell (replacement cost 150k + termination 150k + risk premium 80k
    # = 380k to replace): an on-time supplier asking nothing is cheaper to keep
    # and must be kept; the same supplier asking 600k relief is rationally
    # replaced. In the weak cell the alternate arrives later than the incumbent,
    # so the same 600k ask is accepted. This locks the supplier's own choices as
    # consequential in every treatment cell.
    disciplined = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies("current_expedited", price_amendment_request=0),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_CREDIBLE",
        model_settings=_focal_model_settings(),
    )
    asking_credible = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies("current_expedited", price_amendment_request=600_000),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_CREDIBLE",
        model_settings=_focal_model_settings(),
    )
    asking_weak = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies("current_expedited", price_amendment_request=600_000),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )

    def gc_choice(result):
        return result.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"]

    def supplier_payoff(result):
        ledger = result.final_state.canonical_state["payoff_ledger"]
        return ledger["realized_payoff_by_organization"]["steel_supplier"]

    assert gc_choice(disciplined) == "accept_selected_plan"
    assert gc_choice(asking_credible) == "replace_supplier"
    assert gc_choice(asking_weak) == "accept_selected_plan"
    # The supplier's choice changes its own payoff in the credible cell: asking
    # for relief there is strictly worse than absorbing the cost.
    assert supplier_payoff(disciplined) > supplier_payoff(asking_credible)
    assert supplier_payoff(asking_weak) > supplier_payoff(asking_credible)


def test_commercially_neutral_gc_responds_to_focal_claimed_cost_and_evidence() -> None:
    overclaim = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies(
            "current_expedited",
            [
                {
                    "communication_type": "private_message",
                    "recipient_ids": ["gc"],
                    "summary": "Supplier claims expedited delivery requires major relief.",
                    "claims": [
                        {"field": "forecast_delivery_tick", "value": 14},
                        {"field": "requested_price_amendment", "value": 1_400_000},
                    ],
                }
            ],
        ),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )
    nonperformance_claim = run_policy(
        "S01",
        "normal",
        _focal_supplier_policies(
            "current_expedited",
            [
                {
                    "communication_type": "private_message",
                    "recipient_ids": ["gc"],
                    "summary": "Supplier says its current source cannot perform.",
                    "claims": [
                        {"field": "source_status", "value": "unable_to_perform"},
                    ],
                }
            ],
        ),
        scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        model_settings=_focal_model_settings(),
    )

    assert overclaim.final_state.run_valid
    assert nonperformance_claim.final_state.run_valid
    assert (
        overclaim.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"]
        == "resequence_around_delivery"
    )
    assert (
        nonperformance_claim.final_state.decisions["S01_GC_PROCUREMENT_PLAN"]["option_id"]
        == "replace_supplier"
    )
