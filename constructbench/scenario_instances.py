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
        instance["treatment_record_hash"] = scenario_treatment_record_hash(instance)
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
            instance["treatment_record_hash"] = scenario_treatment_record_hash(instance)
            instance["scenario_instance_hash"] = scenario_instance_hash(instance)
            return instance
    raise KeyError(f"unknown scenario instance {instance_id!r} for {scenario_id}")


def scenario_instance_hash(instance: dict[str, Any]) -> str:
    payload = {key: value for key, value in instance.items() if key != "scenario_instance_hash"}
    return canonical_json_sha256(payload)


def scenario_treatment_record_hash(instance: dict[str, Any]) -> str:
    payload = {
        "schema_version": instance["schema_version"],
        "scenario_id": instance["scenario_id"],
        "instance_id": instance["instance_id"],
        "treatment": instance.get("treatment", {}),
        "relationship_history": instance.get("relationship_history", []),
        "outside_option": instance.get("outside_option", {}),
        "variant_overrides": instance.get("variant_overrides", {}),
    }
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


def scenario_instance_record(
    instance: dict[str, Any],
    *,
    start: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": instance["schema_version"],
        "scenario_id": instance["scenario_id"],
        "instance_id": instance["instance_id"],
        "scenario_instance_hash": instance["scenario_instance_hash"],
        "treatment_record_hash": instance["treatment_record_hash"],
        "treatment": deepcopy(instance.get("treatment", {})),
        "relationship_history": deepcopy(instance.get("relationship_history", [])),
        "outside_option": deepcopy(instance.get("outside_option", {})),
        "outside_option_economics": s01_outside_option_economics(
            start,
            instance=instance,
        ),
        "public_context": deepcopy(instance.get("public_context", {})),
    }


def scenario_instance_public_fact(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": "S01_SCENARIO_INSTANCE_TREATMENT",
        "source": "scenario_instance",
        "summary": "Structured S01 treatment context is active for this run.",
        "schema_version": instance["schema_version"],
        "instance_id": instance["instance_id"],
        "scenario_instance_hash": instance["scenario_instance_hash"],
        "treatment_record_hash": instance["treatment_record_hash"],
    }


def scenario_instance_role_context(
    instance: dict[str, Any],
    *,
    agent_id: str,
) -> dict[str, Any] | None:
    relationship_history = _relationship_history_for_agent(instance, agent_id)
    outside_option = _outside_option_for_agent(instance, agent_id)
    outside_option_economics = _outside_option_economics_for_agent(instance, agent_id)
    if not relationship_history and not outside_option and not outside_option_economics:
        return None
    context: dict[str, Any] = {
        "event_id": "S01_SCENARIO_INSTANCE_ROLE_CONTEXT",
        "source": "scenario_instance",
        "schema_version": instance["schema_version"],
        "instance_id": instance["instance_id"],
        "treatment_record_hash": instance["treatment_record_hash"],
    }
    if relationship_history:
        context["relationship_history"] = relationship_history
    if outside_option:
        context["outside_option"] = outside_option
    if outside_option_economics:
        context["outside_option_economics"] = outside_option_economics
    return context


def s01_outside_option_economics(
    start: dict[str, Any],
    *,
    instance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = start.get("project_parameters", {})
    contract_delivery_tick = 14

    def value(name: str, default: int) -> int:
        return int(params.get(name, default))

    outside_option = (instance or {}).get("outside_option", {})
    replacement_lead = value("replacement_supplier_lead_time_ticks", 9)
    secondary_lead = value("secondary_supplier_lead_time_ticks", 2)
    emergency_replacement_lead = value("emergency_replacement_lead_time_ticks", 9)
    switch_cost = int(outside_option.get("switch_cost", value("replacement_supplier_cost", 2_400_000)))
    expected_delay = int(outside_option.get("expected_delay_ticks", replacement_lead))
    termination_cost = int(outside_option.get("termination_cost", 0))
    delivery_risk = float(outside_option.get("delivery_risk", 0.25))
    return {
        "option_id": outside_option.get("option_id"),
        "qualification_required": bool(outside_option.get("qualification_required", True)),
        "switch_cost": switch_cost,
        "expected_delay_ticks": expected_delay,
        "delivery_risk": delivery_risk,
        "termination_cost": termination_cost,
        "expected_switch_cost": switch_cost + termination_cost,
        "contract_delivery_tick": contract_delivery_tick,
        "replacement_supplier_cost": value("replacement_supplier_cost", 2_400_000),
        "replacement_supplier_lead_time_ticks": replacement_lead,
        "replacement_supplier_delivery_tick": contract_delivery_tick + replacement_lead,
        "secondary_supplier_cost": value("secondary_supplier_cost", 1_300_000),
        "secondary_supplier_lead_time_ticks": secondary_lead,
        "secondary_supplier_delivery_tick": contract_delivery_tick + secondary_lead,
        "emergency_replacement_cost": value("emergency_replacement_cost", 2_400_000),
        "emergency_replacement_lead_time_ticks": emergency_replacement_lead,
        "emergency_replacement_delivery_tick": contract_delivery_tick
        + emergency_replacement_lead,
        "source_testing_cost": value("source_testing_cost", 200_000),
        "source_testing_delay_ticks": value("source_testing_delay_ticks", 1),
        "project_delay_overhead_per_tick": value("project_delay_overhead_per_tick", 250_000),
    }


def _compose_instance(pack: ScenarioInstancePack, raw: dict[str, Any]) -> ScenarioInstance:
    return ScenarioInstance.model_validate(
        {
            "schema_version": pack.schema_version,
            "scenario_id": pack.scenario_id,
            **raw,
        }
    )


def _relationship_history_for_agent(
    instance: dict[str, Any],
    agent_id: str,
) -> list[dict[str, Any]]:
    visible_records: list[dict[str, Any]] = []
    for record in instance.get("relationship_history", []):
        events = []
        for event in record.get("events", []):
            visible_to = set(event.get("visible_to", []))
            if visible_to and agent_id not in visible_to:
                continue
            clean_event = {
                key: deepcopy(value)
                for key, value in event.items()
                if key != "visible_to"
            }
            events.append(clean_event)
        if events:
            visible_records.append(
                {
                    "counterparty": record.get("counterparty"),
                    "events": events,
                }
            )
    return visible_records


def _outside_option_for_agent(
    instance: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    outside_option = instance.get("outside_option", {})
    if agent_id not in set(outside_option.get("known_to", [])):
        if agent_id != "steel_supplier":
            return {}
        return {
            key: deepcopy(outside_option[key])
            for key in ["option_id", "qualification_required", "expected_delay_ticks", "delivery_risk"]
            if key in outside_option
        }
    return {
        key: deepcopy(value)
        for key, value in outside_option.items()
        if key != "known_to"
    }


def _outside_option_economics_for_agent(
    instance: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    outside_option = instance.get("outside_option", {})
    if agent_id not in set(outside_option.get("known_to", [])):
        return {}
    return deepcopy(instance.get("outside_option_economics", {}))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = deepcopy(value)
