from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from constructbench.manifest import canonical_json_sha256

SCENARIO_INSTANCE_SCHEMA_VERSION = "constructbench.scenario_instance.v1"
S01_INSTANCE_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "scenario_instances"
    / "S01_steel_market_shock_instances.yaml"
)


class StrictScenarioInstanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioInstance(StrictScenarioInstanceModel):
    schema_version: str
    scenario_id: str
    instance_id: str
    treatment: dict[str, str] = Field(default_factory=dict)
    relationship_history: list[dict[str, Any]] = Field(default_factory=list)
    outside_option: dict[str, Any] = Field(default_factory=dict)
    public_context: dict[str, Any] = Field(default_factory=dict)
    variant_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ScenarioInstancePack(StrictScenarioInstanceModel):
    schema_version: str
    scenario_id: str
    instances: list[dict[str, Any]]


@lru_cache(maxsize=8)
def load_scenario_instance_pack(path: str | None = None) -> ScenarioInstancePack:
    config_path = Path(path) if path is not None else S01_INSTANCE_CONFIG
    raw = yaml.safe_load(config_path.read_text()) or {}
    pack = ScenarioInstancePack.model_validate(raw)
    if pack.schema_version != SCENARIO_INSTANCE_SCHEMA_VERSION:
        raise ValueError(f"unsupported scenario instance schema: {pack.schema_version}")
    return pack


def list_scenario_instances(scenario_id: str) -> list[dict[str, Any]]:
    pack = load_scenario_instance_pack()
    if pack.scenario_id != scenario_id:
        return []
    instances = []
    for raw in pack.instances:
        instance = _compose_instance(pack, raw).model_dump(mode="json")
        instance["scenario_instance_hash"] = scenario_instance_hash(instance)
        instances.append(instance)
    return instances


def get_scenario_instance(scenario_id: str, instance_id: str) -> dict[str, Any]:
    pack = load_scenario_instance_pack()
    if pack.scenario_id != scenario_id:
        raise KeyError(f"no scenario instance pack for {scenario_id}")
    for raw in pack.instances:
        if raw.get("instance_id") == instance_id:
            instance = _compose_instance(pack, raw).model_dump(mode="json")
            instance["scenario_instance_hash"] = scenario_instance_hash(instance)
            return instance
    raise KeyError(f"unknown scenario instance {instance_id!r} for {scenario_id}")


def scenario_instance_hash(instance: dict[str, Any]) -> str:
    payload = {key: value for key, value in instance.items() if key != "scenario_instance_hash"}
    return canonical_json_sha256(payload)


def apply_scenario_instance_to_start(
    start: dict[str, Any],
    *,
    instance: dict[str, Any],
    variant: str,
) -> dict[str, Any]:
    result = deepcopy(start)
    override = instance.get("variant_overrides", {}).get(variant, {})
    _deep_merge(result, override)
    return result


def scenario_instance_public_fact(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": "S01_SCENARIO_INSTANCE_TREATMENT",
        "source": "scenario_instance",
        "summary": instance.get("public_context", {}).get(
            "summary",
            "Structured scenario treatment context is active for this run.",
        ),
        "schema_version": instance["schema_version"],
        "instance_id": instance["instance_id"],
        "scenario_instance_hash": instance["scenario_instance_hash"],
        "treatment": deepcopy(instance.get("treatment", {})),
        "relationship_history": deepcopy(instance.get("relationship_history", [])),
        "outside_option": deepcopy(instance.get("outside_option", {})),
    }


def _compose_instance(pack: ScenarioInstancePack, raw: dict[str, Any]) -> ScenarioInstance:
    return ScenarioInstance.model_validate(
        {
            "schema_version": pack.schema_version,
            "scenario_id": pack.scenario_id,
            **raw,
        }
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = deepcopy(value)
