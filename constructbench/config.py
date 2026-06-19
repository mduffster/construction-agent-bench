"""YAML configuration loaders for ConstructBench."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from constructbench.enums import AgentRole
from constructbench.models import ProjectConfig, RoleConfig, ScenarioConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def load_project_config(path: str | Path) -> ProjectConfig:
    """Load a typed project config from a YAML file."""
    return ProjectConfig.model_validate(_read_yaml(Path(path)))


def load_agent_configs(path_or_dir: str | Path) -> dict[str, RoleConfig]:
    """Load one role config file or every YAML file in a role config directory."""
    path = Path(path_or_dir)
    paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    if not paths:
        raise ValueError(f"No agent config YAML files found at: {path}")

    configs: dict[str, RoleConfig] = {}
    for config_path in paths:
        role_config = RoleConfig.model_validate(_read_yaml(config_path))
        role_id = role_config.role_id.value
        if role_id in configs:
            raise ValueError(f"Duplicate role config for role_id: {role_id}")
        configs[role_id] = role_config

    expected_roles = {role.value for role in AgentRole}
    loaded_roles = set(configs)
    missing_roles = expected_roles - loaded_roles
    if path.is_dir() and missing_roles:
        missing = ", ".join(sorted(missing_roles))
        raise ValueError(f"Missing required role configs: {missing}")

    return configs


def load_scenario_config(path: str | Path) -> ScenarioConfig:
    """Load a typed scenario config from a YAML file."""
    return ScenarioConfig.model_validate(_read_yaml(Path(path)))
