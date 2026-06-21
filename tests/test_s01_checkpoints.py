from __future__ import annotations

import pytest
from pydantic import ValidationError

from constructbench.agents import ReplayPolicy
from constructbench.checkpoints import (
    S01_PRE_COMMERCIAL_CHECKPOINT_ID,
    S01TreatmentPatch,
    StateCheckpoint,
    build_s01_pre_supplier_commercial_checkpoint,
    fork_checkpoint,
    state_content_hash,
    treatment_diff,
)
from constructbench.focal import build_focal_policies
from constructbench.runner import run_state_policy
from constructbench.state import AgentSubmission, DecisionSelection, RunState


def _supplier_replay_policy() -> ReplayPolicy:
    return ReplayPolicy(
        {
            (
                "supplier_source_and_commercial",
                "steel_supplier",
            ): AgentSubmission(
                decisions=[
                    DecisionSelection(
                        node_id="S01_SUPPLIER_SOURCE_PLAN",
                        option_id="current_expedited",
                    ),
                    DecisionSelection(
                        node_id="S01_SUPPLIER_COMMERCIAL_REQUEST",
                        parameters={
                            "price_amendment_request": 0,
                            "delivery_date_amendment_request": None,
                            "advance_payment_request": 0,
                        },
                    ),
                ],
                private_notes="Preserve on-time delivery without a commercial request.",
            )
        }
    )


def test_s01_pre_supplier_commercial_checkpoint_is_serializable() -> None:
    checkpoint = build_s01_pre_supplier_commercial_checkpoint(variant="normal", seed=17)
    restored = StateCheckpoint.model_validate(checkpoint.model_dump(mode="json"))
    state = fork_checkpoint(restored)

    assert restored.checkpoint_id == S01_PRE_COMMERCIAL_CHECKPOINT_ID
    assert restored.checkpoint_type == "pre_supplier_commercial_decision"
    assert restored.next_phase_id == "supplier_source_and_commercial"
    assert restored.phase_index == 1
    assert state.seed == 17
    assert state.decisions == {}
    assert state.histories["phase_history"][0]["phase_id"] == "market_shock"
    assert state.canonical_state.get("payoff_ledger") is None
    assert state_content_hash(state) == restored.state_hash


def test_s01_treatment_forks_share_pre_treatment_hash_and_have_constrained_diff() -> None:
    checkpoint = build_s01_pre_supplier_commercial_checkpoint(variant="normal")
    base_state = RunState.model_validate(checkpoint.state)
    weak = fork_checkpoint(
        checkpoint,
        treatment_patch=S01TreatmentPatch(
            scenario_instance_id="S01_REL_NONE_OUTSIDE_WEAK",
        ),
    )
    credible = fork_checkpoint(
        checkpoint,
        treatment_patch=S01TreatmentPatch(
            scenario_instance_id="S01_REL_NONE_OUTSIDE_CREDIBLE",
        ),
    )
    diff = treatment_diff(base_state, weak)

    assert weak.canonical_state["scenario"]["pre_treatment_state_hash"] == checkpoint.state_hash
    assert credible.canonical_state["scenario"]["pre_treatment_state_hash"] == checkpoint.state_hash
    assert weak.canonical_state["scenario"]["scenario_instance"]["instance_id"] == (
        "S01_REL_NONE_OUTSIDE_WEAK"
    )
    assert credible.canonical_state["scenario"]["scenario_instance"]["instance_id"] == (
        "S01_REL_NONE_OUTSIDE_CREDIBLE"
    )
    assert diff.unexpected_paths == []
    assert diff.is_valid_treatment_diff is True
    assert "/canonical_state/scenario/scenario_instance" in diff.changed_paths
    assert "/private_state_by_agent/steel_supplier/private_facts/liquidity_gap" in (
        diff.changed_paths
    )
    assert "/public_facts/1" in diff.changed_paths
    assert "/public_state/facts/1" in diff.changed_paths


def test_s01_treatment_patch_rejects_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        S01TreatmentPatch.model_validate(
            {
                "scenario_instance_id": "S01_REL_NONE_OUTSIDE_WEAK",
                "private_fact_overrides": {"steel_supplier": {"liquidity_gap": 0}},
            }
        )


def test_same_focal_action_has_identical_consequences_across_equivalent_forks() -> None:
    checkpoint = build_s01_pre_supplier_commercial_checkpoint(variant="normal")
    patch = S01TreatmentPatch(scenario_instance_id="S01_REL_PRIOR_SUCCESS_OUTSIDE_WEAK")
    fork_a = fork_checkpoint(checkpoint, treatment_patch=patch)
    fork_b = fork_checkpoint(checkpoint, treatment_patch=patch)
    policies_a = build_focal_policies("S01", "steel_supplier", _supplier_replay_policy())
    policies_b = build_focal_policies("S01", "steel_supplier", _supplier_replay_policy())

    result_a = run_state_policy("S01", fork_a, policies_a)
    result_b = run_state_policy("S01", fork_b, policies_b)

    assert result_a.final_state.run_valid
    assert result_b.final_state.run_valid
    assert result_a.final_state.canonical_state == result_b.final_state.canonical_state
    assert (
        result_a.final_state.canonical_state["payoff_ledger"]
        == result_b.final_state.canonical_state["payoff_ledger"]
    )
