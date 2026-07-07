from __future__ import annotations

from copy import deepcopy

from constructbench.runner import _validate_submission, run_fixture
from constructbench.scenarios import S01_V2_CONTRACT, SCENARIOS
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    Communication,
    DecisionSelection,
)
from scripts.export_s01_v2_web_game import build_web_game_payload, payload_content_hash


def _submission(node_id: str, parameters: dict) -> AgentSubmission:
    return AgentSubmission(
        decisions=[
            DecisionSelection(
                node_id=node_id,
                option_id="__parameters__",
                parameters=parameters,
            )
        ],
        communications=[
            Communication(
                communication_type="no_communication",
                summary="Web export validation intentionally sends no message.",
            )
        ],
        assessment_reviews=[
            AssessmentReview(
                evidence_ids=[],
                counterparty_ids=[],
                reason="Web export validation intentionally leaves trust unchanged.",
            )
        ],
    )


def _observation_for_node(node_id: str) -> AgentObservation:
    scenario = SCENARIOS["S01_V2"]
    state = scenario.create_state(run_id=f"web_export_{node_id}", variant="normal")
    actor = scenario.actors[node_id]
    submitted_docs = list(
        scenario.fixtures["efficient_phased_coalition_success"]["decisions"][
            "S01_A1_SUPPLIER_APPLICATION"
        ][1]["submitted_document_ids"]
    )
    return AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=1,
        phase_id=node_id,
        phase_type="agent_execution_phase",
        agent_id=actor,
        role_briefing=state.briefings_by_agent[actor],
        current_business_context=node_id,
        known_facts=[
            {
                "visible_decisions": [
                    {
                        "node_id": "S01_A1_SUPPLIER_APPLICATION",
                        "actor_id": "steel_supplier",
                        "parameters": {"submitted_document_ids": submitted_docs},
                    }
                ],
                "decision_bounds": {
                    "S01_B3_INSPECTOR_DISPOSITION": {
                        "maximum_releasable_value_usd": 1_350_000,
                    },
                    "S01_C3_INSPECTOR_FINAL_DISPOSITION": {
                        "maximum_releasable_value_usd": 1_350_000,
                    },
                },
            }
        ],
        required_decisions=[scenario._request(node_id)],
        trust_prior_by_counterparty=state.trust_state[actor],
        submission_contract=S01_V2_CONTRACT,
    )


def test_s01_v2_web_export_covers_playable_roles_and_three_decisions() -> None:
    payload = build_web_game_payload()

    assert payload["schema_version"] == "constructbench.web_game.s01_v2.v2"
    assert set(payload["roles"]) == set(AGENT_IDS)
    assert payload["playable_roles"] == [
        "steel_supplier",
        "gc",
        "owner",
        "labor_subcontractor",
    ]
    assert payload["system_roles"] == ["lender", "inspector"]
    assert payload["scenario"]["scenario_id"] == "S01_V2_OFFSITE_STEEL_DRAW"
    for agent_id in AGENT_IDS:
        assert len(payload["roles"][agent_id]["nodes"]) == 3
        assert payload["roles"][agent_id]["playable"] is (
            agent_id in payload["playable_roles"]
        )
    for node in payload["decision_nodes"].values():
        assert node["critical_updates"]
        assert node["private_stakes"]
        assert len(node["choices"]) == 3
        assert [choice["choice_id"] for choice in node["choices"]] == [
            "balanced",
            "self_protective",
            "conservative",
        ]
        for choice in node["choices"]:
            assert choice["why_choose"]
            assert choice["tradeoff"]
            assert choice["risk_levels"]["private_benefit"] in {"low", "medium", "high"}
            assert choice["risk_levels"]["cost"] in {"low", "medium", "high"}
            assert choice["risk_levels"]["delay"] in {"low", "medium", "high"}
            assert choice["web_effect"]["state_changes"]
            assert choice["web_effect"]["public_summary"]
            assert choice["reads"]["charitable"]
            assert choice["reads"]["uncharitable"]
            assert choice["reads"]["charitable"] != choice["reads"]["uncharitable"]
    # Narrative copy must be decision-specific: the same archetype at a role's
    # different nodes may not reuse text, or players see identical language
    # every round.
    for field in ("why_choose", "tradeoff"):
        values = [
            choice[field]
            for node in payload["decision_nodes"].values()
            for choice in node["choices"]
        ]
        assert len(values) == len(set(values)), f"duplicated {field} copy across nodes"
    read_values = [
        choice["reads"][side]
        for node in payload["decision_nodes"].values()
        for choice in node["choices"]
        for side in ("charitable", "uncharitable")
    ]
    assert len(read_values) == len(set(read_values)), "duplicated partner-read copy"


def test_s01_v2_web_export_has_initial_state_and_comparisons() -> None:
    payload = build_web_game_payload()

    initial = payload["initial_game_state"]
    assert initial["cost_usd"] == 95_000_000
    assert initial["completion_week"] == 40
    assert initial["blockers"]
    assert payload["comparisons"]["ideal"]["source_id"] == "efficient_phased_coalition_success"
    assert payload["comparisons"]["ideal"]["outcome"]["final_project_cost"] == 95_650_000
    assert set(payload["private_success_thresholds"]) == set(AGENT_IDS)


def test_s01_v2_web_export_choices_are_valid_node_parameter_sets() -> None:
    scenario = SCENARIOS["S01_V2"]
    payload = build_web_game_payload()

    for node_id, node in payload["decision_nodes"].items():
        observation = _observation_for_node(node_id)
        for choice in node["choices"]:
            errors = _validate_submission(
                observation,
                _submission(node_id, choice["parameters"]),
                scenario=scenario,
            )
            assert errors == []


def test_s01_v2_web_export_hash_changes_when_payload_content_changes() -> None:
    payload = build_web_game_payload()
    changed = deepcopy(payload)
    changed["public_baseline"]["forecast_completion_tick"] = 41

    assert payload_content_hash(payload) == payload["scenario"]["content_hash"]
    assert payload_content_hash(changed) != payload["scenario"]["content_hash"]


def test_s01_v2_web_export_witnesses_match_current_harness() -> None:
    payload = build_web_game_payload()

    for fixture_name, exported in payload["witnesses"].items():
        result = run_fixture("S01_V2", fixture_name)
        project = result.final_state.canonical_state["project"]
        payoff = result.final_state.canonical_state["payoff_ledger"]
        assert exported["terminal_status"] == result.final_state.terminal_status
        assert exported["final_project_cost"] == project["project_cost"]
        assert exported["completion_tick"] == project["completion_tick"]
        assert exported["path_label"] == project["s01_v2_path_label"]
        assert exported["realized_payoff_by_organization"] == payoff[
            "realized_payoff_by_organization"
        ]
