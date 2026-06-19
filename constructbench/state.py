"""State initialization and snapshot export."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from constructbench.enums import AgentRole, BehaviorProfile, ResourceConditionLevel
from constructbench.models import (
    AgentPrivateState,
    CounterpartyExpectationState,
    PairwiseTrustState,
    ProjectConfig,
    RoleConfig,
    StateStore,
)


def initialize_state(
    project_config: ProjectConfig,
    role_configs: dict[str, RoleConfig],
    condition_overrides: dict[str | AgentRole, str | ResourceConditionLevel] | None = None,
    behavior_overrides: dict[str | AgentRole, str | BehaviorProfile] | None = None,
) -> StateStore:
    """Build the Phase 1 state store from typed project and role configs."""
    typed_role_configs = {
        _coerce_role_id(role_id): config
        for role_id, config in role_configs.items()
    }
    expected_roles = set(AgentRole)

    missing_configs = expected_roles - set(typed_role_configs)
    if missing_configs:
        missing = ", ".join(sorted(role.value for role in missing_configs))
        raise ValueError(f"Missing role configs: {missing}")

    missing_private = expected_roles - set(project_config.private_states)
    if missing_private:
        missing = ", ".join(sorted(role.value for role in missing_private))
        raise ValueError(f"Missing private states: {missing}")

    baseline_beliefs = {
        role: project_config.initial_belief.model_copy(deep=True)
        for role in expected_roles
    }
    private_by_agent = _apply_private_profile_overlays(
        project_config.private_states,
        typed_role_configs,
        condition_overrides or {},
        behavior_overrides or {},
    )

    return StateStore(
        canonical=project_config.canonical.model_copy(deep=True),
        public=project_config.public_state.model_copy(deep=True),
        private_by_agent=private_by_agent,
        beliefs_by_agent=baseline_beliefs,
        role_configs=typed_role_configs,
        trust_by_agent=_initial_trust(expected_roles),
        agent_trust_by_agent=_initial_trust(expected_roles),
        agent_trust_assessments=[],
        expectations_by_agent=_initial_expectations(expected_roles),
        expectation_update_records=[],
        oversight_findings=[],
        disclosure_assessments=[],
        trust_updates=[],
        private_events_by_agent={role: [] for role in expected_roles},
        private_messages=[],
    )


def export_state_snapshot(state: StateStore) -> dict[str, Any]:
    """Return a JSON-safe snapshot of the current separated state stores."""
    return state.to_snapshot()


def _coerce_role_id(role_id: str | AgentRole) -> AgentRole:
    return role_id if isinstance(role_id, AgentRole) else AgentRole(role_id)


def _coerce_condition(value: str | ResourceConditionLevel) -> ResourceConditionLevel:
    return value if isinstance(value, ResourceConditionLevel) else ResourceConditionLevel(value)


def _coerce_behavior(value: str | BehaviorProfile) -> BehaviorProfile:
    return value if isinstance(value, BehaviorProfile) else BehaviorProfile(value)


def _apply_private_profile_overlays(
    configured_private_states: dict[AgentRole, AgentPrivateState],
    role_configs: dict[AgentRole, RoleConfig],
    condition_overrides: dict[str | AgentRole, str | ResourceConditionLevel],
    behavior_overrides: dict[str | AgentRole, str | BehaviorProfile],
) -> dict[AgentRole, AgentPrivateState]:
    normalized_condition_overrides = {
        _coerce_role_id(role): _coerce_condition(level)
        for role, level in condition_overrides.items()
    }
    normalized_behavior_overrides = {
        _coerce_role_id(role): _coerce_behavior(profile)
        for role, profile in behavior_overrides.items()
    }
    private_by_agent = deepcopy(configured_private_states)

    for role, private_state in private_by_agent.items():
        role_config = role_configs[role]
        condition_level = normalized_condition_overrides.get(
            role,
            private_state.resource_condition_level or role_config.default_condition_level,
        )
        behavior_profile = normalized_behavior_overrides.get(
            role,
            private_state.behavior_profile or role_config.default_behavior_profile,
        )
        condition_preset = role_config.resource_condition_presets.get(condition_level)
        behavior_preset = role_config.behavior_profile_presets.get(behavior_profile)

        data = dict(private_state.data)
        if condition_preset is not None:
            data.update(condition_preset.data)

        private_by_agent[role] = private_state.model_copy(
            update={
                "resource_condition_level": condition_level,
                "resource_summary": (
                    condition_preset.summary if condition_preset is not None else None
                ),
                "behavior_profile": behavior_profile,
                "behavior_summary": (
                    behavior_preset.summary if behavior_preset is not None else None
                ),
                "behavior_guidance": (
                    list(behavior_preset.decision_guidance)
                    if behavior_preset is not None
                    else []
                ),
                "dishonesty_framing": (
                    behavior_preset.dishonesty_framing
                    if behavior_preset is not None
                    else None
                ),
                "data": data,
            },
        )

    return private_by_agent


def _initial_trust(roles: set[AgentRole]) -> dict[AgentRole, dict[AgentRole, PairwiseTrustState]]:
    return {
        observer: {
            target: PairwiseTrustState(observer=observer, target=target, score=0.75)
            for target in roles
            if target != observer
        }
        for observer in roles
    }


def _initial_expectations(
    roles: set[AgentRole],
) -> dict[AgentRole, dict[AgentRole, CounterpartyExpectationState]]:
    return {
        observer: {
            target: CounterpartyExpectationState(observer=observer, target=target)
            for target in roles
            if target != observer
        }
        for observer in roles
    }
