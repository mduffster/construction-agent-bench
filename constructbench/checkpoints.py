from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from constructbench.manifest import canonical_json_sha256
from constructbench.scenario_instances import (
    apply_scenario_instance_to_start,
    get_scenario_instance,
    s01_outside_option_economics,
    scenario_instance_public_fact,
)
from constructbench.scenarios import Scenario, get_scenario
from constructbench.state import AGENT_IDS, Phase, RunState

CHECKPOINT_SCHEMA_VERSION = "constructbench.state_checkpoint.v1"
TREATMENT_PATCH_SCHEMA_VERSION = "constructbench.treatment_patch.v1"


class StrictCheckpointModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StateCheckpoint(StrictCheckpointModel):
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    checkpoint_id: str
    checkpoint_type: Literal["pre_supplier_commercial_decision"]
    scenario_key: str
    scenario_id: str
    variant: Literal["normal", "stressed"]
    phase_index: int
    next_phase_id: str | None
    state_hash: str
    scenario_instance_hash: str | None = None
    state: dict[str, Any]


class S01TreatmentPatch(StrictCheckpointModel):
    schema_version: str = TREATMENT_PATCH_SCHEMA_VERSION
    scenario_id: Literal["S01_STEEL_MARKET_SHOCK"] = "S01_STEEL_MARKET_SHOCK"
    scenario_instance_id: str
    declared_intervention_fields: list[str] = Field(
        default_factory=lambda: [
            "relationship_history",
            "outside_option",
            "steel_supplier",
            "owner",
            "project_parameters",
        ]
    )


class StateDiff(StrictCheckpointModel):
    schema_version: str = "constructbench.state_diff.v1"
    changed_paths: list[str]
    allowed_prefixes: list[str]
    unexpected_paths: list[str]

    @property
    def is_valid_treatment_diff(self) -> bool:
        return not self.unexpected_paths


S01_PRE_COMMERCIAL_CHECKPOINT_ID = "S01_PRE_SUPPLIER_COMMERCIAL_DECISION"
_TREATMENT_FACT_EVENT_ID = "S01_SCENARIO_INSTANCE_TREATMENT"
_S01_ALLOWED_TREATMENT_DIFF_PREFIXES = [
    "/model_settings/scenario_instance_id",
    "/canonical_state/scenario/pre_treatment_state_hash",
    "/canonical_state/scenario/pre_treatment_scenario_start_hash",
    "/canonical_state/scenario/scenario_start",
    "/canonical_state/scenario/scenario_start_hash",
    "/canonical_state/scenario/scenario_instance",
    "/canonical_state/scenario/scenario_instance_public_context",
    "/canonical_state/scenario/treatment_patch",
    "/public_facts",
    "/public_state/facts",
    "/private_state_by_agent",
    "/briefings_by_agent",
]


def build_s01_pre_supplier_commercial_checkpoint(
    *,
    variant: Literal["normal", "stressed"] = "normal",
    seed: int = 0,
    run_id: str = "checkpoint_s01_pre_supplier_commercial",
) -> StateCheckpoint:
    scenario = get_scenario("S01")
    state = scenario.create_state(
        run_id=run_id,
        variant=variant,
        seed=seed,
        model_settings={"policy": "checkpoint_base"},
    )
    _advance_to_phase(state, scenario, "supplier_source_and_commercial")
    return create_state_checkpoint(
        state,
        scenario,
        checkpoint_id=S01_PRE_COMMERCIAL_CHECKPOINT_ID,
        checkpoint_type="pre_supplier_commercial_decision",
    )


def create_state_checkpoint(
    state: RunState,
    scenario: Scenario,
    *,
    checkpoint_id: str,
    checkpoint_type: Literal["pre_supplier_commercial_decision"],
) -> StateCheckpoint:
    next_phase = scenario.next_phase(state)
    state_payload = state.model_dump(mode="json")
    scenario_instance = state.canonical_state.get("scenario", {}).get("scenario_instance")
    return StateCheckpoint(
        checkpoint_id=checkpoint_id,
        checkpoint_type=checkpoint_type,
        scenario_key=scenario.scenario_key,
        scenario_id=scenario.scenario_id,
        variant=state.variant,
        phase_index=state.phase_index,
        next_phase_id=next_phase.phase_id if next_phase else None,
        state_hash=canonical_json_sha256(state_payload),
        scenario_instance_hash=(
            scenario_instance.get("scenario_instance_hash")
            if isinstance(scenario_instance, dict)
            else None
        ),
        state=state_payload,
    )


def fork_checkpoint(
    checkpoint: StateCheckpoint | dict[str, Any],
    *,
    treatment_patch: S01TreatmentPatch | dict[str, Any] | None = None,
    run_id: str | None = None,
) -> RunState:
    checkpoint_model = (
        checkpoint
        if isinstance(checkpoint, StateCheckpoint)
        else StateCheckpoint.model_validate(checkpoint)
    )
    state = RunState.model_validate(checkpoint_model.state).model_copy(deep=True)
    if run_id is not None:
        state.run_id = run_id
    if treatment_patch is not None:
        patch = (
            treatment_patch
            if isinstance(treatment_patch, S01TreatmentPatch)
            else S01TreatmentPatch.model_validate(treatment_patch)
        )
        apply_s01_treatment_patch(
            state,
            patch,
            pre_treatment_state_hash=checkpoint_model.state_hash,
        )
    return state


def apply_s01_treatment_patch(
    state: RunState,
    patch: S01TreatmentPatch,
    *,
    pre_treatment_state_hash: str,
) -> None:
    if state.scenario_id != "S01_STEEL_MARKET_SHOCK":
        raise ValueError("S01 treatment patches can only be applied to S01 states")
    instance = get_scenario_instance(patch.scenario_id, patch.scenario_instance_id)
    scenario = get_scenario("S01")
    scenario_record = state.canonical_state["scenario"]
    pre_treatment_start = deepcopy(
        scenario_record.get("pre_treatment_scenario_start")
        or scenario_record["scenario_start"]
    )
    patched_start = apply_scenario_instance_to_start(
        pre_treatment_start,
        instance=instance,
        variant=state.variant,
    )

    scenario_record["pre_treatment_state_hash"] = pre_treatment_state_hash
    scenario_record["pre_treatment_scenario_start_hash"] = canonical_json_sha256(
        pre_treatment_start
    )
    scenario_record["scenario_start"] = deepcopy(patched_start)
    scenario_record["scenario_start_hash"] = canonical_json_sha256(patched_start)
    scenario_record["scenario_instance"] = {
        "schema_version": instance["schema_version"],
        "scenario_id": instance["scenario_id"],
        "instance_id": instance["instance_id"],
        "scenario_instance_hash": instance["scenario_instance_hash"],
        "treatment": deepcopy(instance.get("treatment", {})),
        "relationship_history": deepcopy(instance.get("relationship_history", [])),
        "outside_option": deepcopy(instance.get("outside_option", {})),
        "outside_option_economics": s01_outside_option_economics(patched_start),
        "public_context": deepcopy(instance.get("public_context", {})),
    }
    scenario_record["treatment_patch"] = patch.model_dump(mode="json")
    state.model_settings["scenario_instance_id"] = patch.scenario_instance_id

    public_fact = scenario_instance_public_fact(scenario_record["scenario_instance"])
    scenario_record["scenario_instance_public_context"] = public_fact
    _replace_treatment_public_fact(state.public_facts, public_fact)
    _replace_treatment_public_fact(state.public_state["facts"], public_fact)

    for agent_id in AGENT_IDS:
        patched_private_facts = deepcopy(patched_start.get(agent_id, {}))
        state.private_state_by_agent[agent_id].setdefault("private_facts", {}).update(
            patched_private_facts
        )
        state.briefings_by_agent[agent_id] = scenario.briefing(
            agent_id,
            state.behavior_profile_by_agent[agent_id],
            state.goal_profile_by_agent[agent_id],
            patched_private_facts,
        )


def treatment_diff(
    base_state: RunState | dict[str, Any],
    forked_state: RunState | dict[str, Any],
    *,
    allowed_prefixes: list[str] | None = None,
) -> StateDiff:
    base_payload = _state_payload(base_state)
    fork_payload = _state_payload(forked_state)
    changed_paths = sorted(_changed_paths(base_payload, fork_payload))
    prefixes = allowed_prefixes or _S01_ALLOWED_TREATMENT_DIFF_PREFIXES
    unexpected = [
        path for path in changed_paths if not any(_path_matches(path, prefix) for prefix in prefixes)
    ]
    return StateDiff(
        changed_paths=changed_paths,
        allowed_prefixes=list(prefixes),
        unexpected_paths=unexpected,
    )


def state_content_hash(state: RunState | dict[str, Any]) -> str:
    return canonical_json_sha256(_state_payload(state))


def _advance_to_phase(state: RunState, scenario: Scenario, target_phase_id: str) -> None:
    for _ in range(20):
        phase = scenario.next_phase(state)
        if phase is None:
            raise ValueError(f"scenario ended before phase {target_phase_id!r}")
        if phase.phase_id == target_phase_id:
            return
        if phase.phase_type != "event_phase":
            raise ValueError(
                f"cannot pass active phase {phase.phase_id!r} while seeking {target_phase_id!r}"
            )
        _apply_event_phase_for_checkpoint(state, phase)
    raise ValueError(f"phase {target_phase_id!r} was not reached")


def _apply_event_phase_for_checkpoint(state: RunState, phase: Phase) -> None:
    state.phase_index += 1
    state.public_facts.extend(deepcopy(phase.public_facts))
    state.public_state["facts"].extend(deepcopy(phase.public_facts))
    for agent_id, facts in phase.private_facts_by_agent.items():
        state.private_state_by_agent[agent_id]["private_facts"].update(deepcopy(facts))
    state.histories["phase_history"].append(
        {
            "phase_index": state.phase_index,
            "phase_id": phase.phase_id,
            "phase_type": phase.phase_type,
            "summary": phase.summary,
        }
    )


def _replace_treatment_public_fact(records: list[dict[str, Any]], public_fact: dict[str, Any]) -> None:
    records[:] = [
        record for record in records if record.get("event_id") != _TREATMENT_FACT_EVENT_ID
    ]
    records.append(deepcopy(public_fact))


def _state_payload(state: RunState | dict[str, Any]) -> dict[str, Any]:
    if isinstance(state, RunState):
        return state.model_dump(mode="json")
    return deepcopy(state)


def _changed_paths(left: Any, right: Any, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        paths: list[str] = []
        for key in sorted(set(left) | set(right)):
            next_path = f"{path}/{key}"
            if key not in left or key not in right:
                paths.append(next_path)
            else:
                paths.extend(_changed_paths(left[key], right[key], next_path))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        paths = []
        for index in range(max(len(left), len(right))):
            next_path = f"{path}/{index}"
            if index >= len(left) or index >= len(right):
                paths.append(next_path)
            else:
                paths.extend(_changed_paths(left[index], right[index], next_path))
        return paths
    return [] if left == right else [path or "/"]


def _path_matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")
