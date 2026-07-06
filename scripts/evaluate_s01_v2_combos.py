"""Deterministic pre-flight evaluation of S01 V2 decision combinations.

Before spending money on live all-agent runs, walk a curated set of per-role
archetype combinations (balanced / self_protective / conservative per
organization, composed from the three archetype fixtures) through the full
deterministic runtime. Every combo must produce a valid, terminal run. The
report shows the outcome each combination reaches, so flat spots (roles whose
deviation never changes anything) are visible before any model call.

This is not the 3^6 grid; it is the uniform paths, every single-role deviation
from all-balanced, and a handful of adversarial mixes.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from constructbench.agents import ScriptedPolicy
from constructbench.runner import run_policy
from constructbench.scenarios import SCENARIOS
from constructbench.state import AGENT_IDS, AgentObservation, AgentSubmission

ARCHETYPE_FIXTURES = {
    "balanced": "efficient_phased_coalition_success",
    "self_protective": "coordination_failure",
    "conservative": "conservative_project_success",
}
ROLES = ["steel_supplier", "gc", "owner", "inspector", "labor_subcontractor", "lender"]
ROLE_SHORT = {
    "steel_supplier": "supplier",
    "gc": "gc",
    "owner": "owner",
    "inspector": "inspector",
    "labor_subcontractor": "labor",
    "lender": "lender",
}


def combo_catalog() -> dict[str, dict[str, str]]:
    combos: dict[str, dict[str, str]] = {}
    for archetype in ARCHETYPE_FIXTURES:
        combos[f"uniform_{archetype}"] = {role: archetype for role in ROLES}
    for role in ROLES:
        for deviation in ["self_protective", "conservative"]:
            assignment = {other: "balanced" for other in ROLES}
            assignment[role] = deviation
            combos[f"{ROLE_SHORT[role]}_{deviation}_only"] = assignment
    mixes = {
        "defensive_money": {"owner": "self_protective", "lender": "self_protective"},
        "defensive_field": {"inspector": "conservative", "labor_subcontractor": "conservative"},
        "distrust_pairing": {"steel_supplier": "self_protective", "gc": "conservative"},
        "everyone_guarded_but_supplier": {
            role: "conservative" for role in ROLES if role != "steel_supplier"
        },
        "supplier_alone_cooperates": {
            role: "self_protective" for role in ROLES if role != "steel_supplier"
        },
        "split_postures": {
            "steel_supplier": "conservative",
            "gc": "self_protective",
            "owner": "conservative",
            "inspector": "self_protective",
        },
    }
    for name, overrides in mixes.items():
        assignment = {role: "balanced" for role in ROLES}
        assignment.update(overrides)
        combos[name] = assignment
    return combos


def compose_decisions(assignment: dict[str, str]) -> dict[str, tuple[str, dict[str, Any]]]:
    scenario = SCENARIOS["S01_V2"]
    decisions: dict[str, tuple[str, dict[str, Any]]] = {}
    for node_id, actor_id in scenario.actors.items():
        fixture_name = ARCHETYPE_FIXTURES[assignment[actor_id]]
        decisions[node_id] = deepcopy(scenario.fixtures[fixture_name]["decisions"][node_id])
    return decisions


class StateAwareComboPolicy(ScriptedPolicy):
    """Fixture decisions with the state-contingent fields adapted at decide time.

    Mixed-archetype combos compose decisions from different fixtures, so the
    handful of parameters that must reference actual run state (documents the
    supplier really submitted, whether Lot B really became ready, the
    inspector's verified-value bound, whether a backup really exists) can
    disagree with the state the mix produced. A live agent reads these from its
    observation; this policy performs the same reads so the evaluation
    exercises the scenario's processes rather than the fixture's assumptions.
    """

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        submission = super().decide(observation)
        for selection in submission.decisions:
            params = selection.parameters
            if selection.node_id == "S01_A2_GC_INITIAL_REVIEW":
                submitted = _visible_submitted_documents(observation)
                for field in [
                    "owner_lender_package_document_ids",
                    "inspector_package_document_ids",
                ]:
                    params[field] = [doc for doc in params.get(field, []) if doc in submitted]
            if selection.node_id == "S01_C1_SUPPLIER_STATUS_AND_RECOVERY":
                readiness = _private_readiness(observation)
                if readiness:
                    lot_a_ready = readiness.get("actual_lot_a_ready_tick") is not None
                    lot_b_ready = readiness.get("actual_lot_b_ready_tick") is not None
                    if params.get("ship_action") == "SHIP_BOTH" and not lot_b_ready:
                        params["ship_action"] = "SHIP_A" if lot_a_ready else "HOLD_ALL"
                        params["reported_lot_b_status"] = "NOT_READY"
                    if params.get("ship_action") in {"SHIP_A", "SHIP_BOTH"} and not lot_a_ready:
                        params["ship_action"] = "HOLD_ALL"
                        params["reported_lot_a_status"] = "NOT_READY"
            if selection.node_id in {
                "S01_B3_INSPECTOR_DISPOSITION",
                "S01_C3_INSPECTOR_FINAL_DISPOSITION",
            }:
                bound = _releasable_value_bound(observation, selection.node_id)
                field = (
                    "maximum_releasable_value_usd"
                    if selection.node_id == "S01_B3_INSPECTOR_DISPOSITION"
                    else "approved_shipping_value_usd"
                )
                if bound is not None and int(params.get(field, 0)) > int(bound):
                    params[field] = int(bound)
            if selection.node_id == "S01_C2_GC_RECOVERY_PLAN":
                if params.get("recovery_plan") == "ACTIVATE_BACKUP" and not _visible_backup(
                    observation
                ):
                    params["recovery_plan"] = "ACCEPT_DELAY"
        return submission


def _visible_submitted_documents(observation: AgentObservation) -> set[str]:
    documents: set[str] = set()
    for fact in observation.known_facts:
        for record in fact.get("visible_decisions", []) or []:
            if record.get("node_id") == "S01_A1_SUPPLIER_APPLICATION":
                documents.update(record.get("parameters", {}).get("submitted_document_ids", []))
    return documents


def _private_readiness(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        private_facts = fact.get("private_facts")
        if isinstance(private_facts, dict):
            readiness = private_facts.get("s01_v2_actual_readiness")
            if isinstance(readiness, dict):
                return dict(readiness)
    return {}


def _releasable_value_bound(observation: AgentObservation, node_id: str) -> int | None:
    for fact in observation.known_facts:
        bounds = fact.get("decision_bounds", {}) or {}
        node_bounds = bounds.get(node_id)
        if isinstance(node_bounds, dict) and "maximum_releasable_value_usd" in node_bounds:
            return int(node_bounds["maximum_releasable_value_usd"])
    return None


def _visible_backup(observation: AgentObservation) -> dict[str, Any]:
    for fact in observation.known_facts:
        options = fact.get("recovery_options")
        if isinstance(options, dict):
            backup = options.get("backup")
            if (
                isinstance(backup, dict)
                and backup.get("status") in {"RESERVED", "QUALIFYING", "ACTIVATED"}
                and int(backup.get("activation_cost_usd") or 0) > 0
                and backup.get("delivery_tick_if_activated") is not None
            ):
                return backup
    return {}


def combo_policies(assignment: dict[str, str]) -> dict[str, Any]:
    policy = StateAwareComboPolicy(compose_decisions(assignment))
    return {agent_id: policy for agent_id in AGENT_IDS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/s01_v2_combo_eval/report.json"),
    )
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for combo_id, assignment in combo_catalog().items():
        result = run_policy(
            "S01_V2",
            "normal",
            combo_policies(assignment),
            model_settings={"policy": "scripted_combo", "combo_id": combo_id},
        )
        state = result.final_state
        project = state.canonical_state["project"]
        organizations = state.canonical_state.get("organizations", {})
        row = {
            "combo_id": combo_id,
            "assignment": assignment,
            "run_valid": state.run_valid,
            "terminal_status": state.terminal_status,
            "path_label": project.get("s01_v2_path_label"),
            "final_project_cost": project.get("project_cost"),
            "completion_tick": project.get("completion_tick"),
            "project_success": project.get("s01_v2_project_success"),
            "coalition_success": project.get("s01_v2_coalition_success"),
            "private_success_by_organization": {
                org: record.get("private_success")
                for org, record in organizations.items()
            },
        }
        rows.append(row)
        if not state.run_valid or state.terminal_status == "IN_PROGRESS":
            failures.append(combo_id)

    distinct_outcomes = len(
        {
            (row["terminal_status"], row["final_project_cost"], row["completion_tick"])
            for row in rows
        }
    )
    report = {
        "combo_count": len(rows),
        "all_valid": not failures,
        "failures": failures,
        "distinct_outcomes": distinct_outcomes,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"{'combo':<32} {'status':<22} {'path':<30} {'cost':>12} {'tick':>4}  coalition")
    for row in rows:
        cost = row["final_project_cost"]
        tick = row["completion_tick"]
        print(
            f"{row['combo_id']:<32}"
            f" {str(row['terminal_status']):<22}"
            f" {str(row['path_label']):<30}"
            f" {('n/a' if cost is None else format(cost, ',')):>12}"
            f" {('n/a' if tick is None else tick):>4}"
            f"  {row['coalition_success']}"
        )
    print(f"\ncombos={len(rows)} all_valid={not failures} distinct_outcomes={distinct_outcomes}")
    print(f"wrote {args.output}")
    if failures:
        raise SystemExit(f"invalid combos: {failures}")


if __name__ == "__main__":
    main()
