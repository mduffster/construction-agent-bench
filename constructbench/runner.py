from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from constructbench.agents import AgentPolicy, policies_for_fixture
from constructbench.events import Event, record_event
from constructbench.reporting import write_run_outputs
from constructbench.scenarios import Scenario, get_scenario
from constructbench.state import (
    AGENT_IDS,
    AgentObservation,
    AgentSubmission,
    AssessmentReview,
    AssessmentUpdate,
    BehaviorProfileName,
    Communication,
    DecisionSelection,
    Phase,
    PhaseTurn,
    RunState,
    TrustValues,
)


@dataclass
class RunResult:
    initial_state: RunState
    final_state: RunState
    events: list[Event]
    turn_summaries: list[dict[str, Any]]
    output_dir: Path | None = None


CLAIM_TYPES: dict[str, type | tuple[type, ...]] = {
    "forecast_delivery_tick": int,
    "source_status": str,
    "requested_price_amendment": int,
    "requested_delivery_tick": (int, type(None)),
    "project_forecast_completion_tick": int,
    "project_forecast_final_cost": int,
    "crane_status": str,
    "crane_work_finish_tick": int,
    "provisional_crane_work_finish_tick": int,
    "weather_protection_status": str,
    "material_delivery_acceptance_status": str,
    "expected_full_payment_tick": int,
    "payment_status_tick_22": str,
    "payment_status": str,
    "initial_payment_amount": int,
    "remaining_payment_tick": int,
    "work_status": str,
    "expected_structural_release_tick": int,
    "expected_project_completion_tick": int,
    "corrective_strategy": str,
    "claimed_defect_count": int,
    "critical_task_finish_tick": int,
    "claimed_available_crew_count": int,
    "claimed_capacity_plan": str,
    "inspection_booking_status": str,
}


def run_fixture(
    scenario_key: str,
    fixture_name: str,
    *,
    output_dir: Path | None = None,
    seed: int = 0,
    behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
) -> RunResult:
    scenario = get_scenario(scenario_key)
    fixture = scenario.fixtures[fixture_name]
    return run_policy(
        scenario_key,
        fixture["variant"],
        policies_for_fixture(fixture["decisions"]),
        output_dir=output_dir,
        seed=seed,
        behavior_profile_by_agent=behavior_profile_by_agent,
        model_settings={"policy": "scripted_fixture", "fixture": fixture_name},
    )


def run_policy(
    scenario_key: str,
    variant: str,
    policies: dict[str, AgentPolicy],
    *,
    output_dir: Path | None = None,
    seed: int = 0,
    run_id: str | None = None,
    model_settings: dict[str, Any] | None = None,
    behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
    debug_model_io: bool = False,
    max_phases: int = 50,
) -> RunResult:
    scenario = get_scenario(scenario_key)
    return run_scenario_policy(
        scenario,
        variant,
        policies,
        output_dir=output_dir,
        seed=seed,
        run_id=run_id,
        model_settings=model_settings,
        behavior_profile_by_agent=behavior_profile_by_agent,
        debug_model_io=debug_model_io,
        max_phases=max_phases,
    )


def run_scenario_policy(
    scenario: Scenario,
    variant: str,
    policies: dict[str, AgentPolicy],
    *,
    output_dir: Path | None = None,
    seed: int = 0,
    run_id: str | None = None,
    model_settings: dict[str, Any] | None = None,
    behavior_profile_by_agent: dict[str, BehaviorProfileName] | None = None,
    debug_model_io: bool = False,
    max_phases: int = 50,
) -> RunResult:
    state = scenario.create_state(
        run_id=run_id or f"run_{uuid4().hex[:12]}",
        variant=variant,  # type: ignore[arg-type]
        seed=seed,
        model_settings=model_settings or {},
        behavior_profile_by_agent=behavior_profile_by_agent,
    )
    _initialize_policies(policies, state)
    initial_state = state.model_copy(deep=True)
    events: list[Event] = []
    turn_summaries: list[dict[str, Any]] = []
    terminal_recorded = False

    record_event(
        state,
        events,
        "briefing_phase",
        details={
            "summary": "Agents initialized as business organizations.",
            "state_after": state.model_dump(mode="json"),
        },
    )

    for _ in range(max_phases):
        phase = scenario.next_phase(state)
        if state.terminal_status != "IN_PROGRESS" and not terminal_recorded:
            record_event(
                state,
                events,
                "terminal_state_computed",
                details={
                    "terminal_status": state.terminal_status,
                    "terminal_reason": state.terminal_reason,
                    "state_after": state.model_dump(mode="json"),
                },
            )
            terminal_recorded = True
        if phase is None:
            break
        state.phase_index += 1
        if phase.phase_type == "event_phase":
            _apply_event_phase(state, events, phase)
            turn_summaries.append(_turn_summary(state, phase, []))
            continue
        active_agents = [turn.agent_id for turn in phase.turns]
        state.histories["agent_activation_history"].append(
            {
                "phase_index": state.phase_index,
                "phase_id": phase.phase_id,
                "active_agents": active_agents,
            }
        )
        observations = [_build_observation(state, phase, turn) for turn in phase.turns]
        collected: list[tuple[PhaseTurn, AgentObservation, AgentSubmission]] = []
        for turn, observation in zip(phase.turns, observations, strict=True):
            policy = policies.get(turn.agent_id)
            if policy is None:
                _mark_invalid(
                    state,
                    events,
                    turn.agent_id,
                    phase,
                    f"no policy configured for active agent {turn.agent_id}",
                )
                break
            submission = policy.decide(observation)
            _drain_model_io(state, policy)
            errors = _validate_submission(observation, submission)
            if errors and hasattr(policy, "repair"):
                state.histories["repair_attempts"].append(
                    {
                        "phase_index": state.phase_index,
                        "phase_id": phase.phase_id,
                        "agent_id": turn.agent_id,
                        "errors": errors,
                    }
                )
                submission = policy.repair(observation, errors)  # type: ignore[attr-defined]
                _drain_model_io(state, policy)
                errors = _validate_submission(observation, submission)
            state.histories["agent_observation_history"].append(observation.model_dump(mode="json"))
            state.histories["agent_submission_history"].append(
                {
                    "phase_index": state.phase_index,
                    "phase_id": phase.phase_id,
                    "agent_id": turn.agent_id,
                    "submission": submission.model_dump(mode="json"),
                }
            )
            state.histories["validation_results"].append(
                {
                    "phase_index": state.phase_index,
                    "phase_id": phase.phase_id,
                    "agent_id": turn.agent_id,
                    "valid": not errors,
                    "errors": errors,
                }
            )
            if errors:
                _mark_invalid(state, events, turn.agent_id, phase, "; ".join(errors))
                break
            collected.append((turn, observation, submission))
        if state.terminal_status == "INVALID_AGENT_OUTPUT":
            break
        for turn, observation, submission in collected:
            _apply_submission(state, events, scenario, phase, turn, observation, submission)
        _mark_phase_done(state, events, phase)
        turn_summaries.append(_turn_summary(state, phase, active_agents))
    else:
        _mark_invalid(
            state,
            events,
            None,
            None,
            f"run exceeded max_phases={max_phases}",
        )

    if state.terminal_status == "IN_PROGRESS":
        _mark_invalid(
            state,
            events,
            None,
            None,
            "scenario ended with unresolved required business decisions",
        )
    if output_dir is not None:
        write_run_outputs(
            output_dir,
            initial_state,
            state,
            events,
            turn_summaries,
            debug_model_io=debug_model_io,
        )
    return RunResult(
        initial_state=initial_state,
        final_state=state,
        events=events,
        turn_summaries=turn_summaries,
        output_dir=output_dir,
    )


def _initialize_policies(policies: dict[str, AgentPolicy], state: RunState) -> None:
    for agent_id, briefing in state.briefings_by_agent.items():
        policy = policies.get(agent_id)
        if policy is not None and hasattr(policy, "initialize"):
            policy.initialize(briefing)  # type: ignore[attr-defined]


def _apply_event_phase(state: RunState, events: list[Event], phase: Phase) -> None:
    state.public_facts.extend(phase.public_facts)
    state.public_state["facts"].extend(phase.public_facts)
    for agent_id, facts in phase.private_facts_by_agent.items():
        state.private_state_by_agent[agent_id]["private_facts"].update(facts)
    _mark_phase_done(state, events, phase)


def _build_observation(state: RunState, phase: Phase, turn: PhaseTurn) -> AgentObservation:
    known_facts = list(turn.known_facts)
    baseline_context = state.canonical_state.get("baseline_project_public_context")
    if baseline_context:
        known_facts.append(
            {
                "source": "public_project_plan",
                **deepcopy(baseline_context),
            }
        )
    known_facts.extend(
        [
            {"source": "public", **fact}
            for fact in state.public_facts
        ]
    )
    known_facts.append(
        {
            "source": "private",
            "private_facts": state.private_state_by_agent[turn.agent_id].get("private_facts", {}),
        }
    )
    return AgentObservation(
        run_id=state.run_id,
        scenario_id=state.scenario_id,
        phase_index=state.phase_index,
        phase_id=phase.phase_id,
        phase_type=phase.phase_type,
        agent_id=turn.agent_id,
        role_briefing=state.briefings_by_agent[turn.agent_id],
        current_business_context=turn.context,
        known_facts=known_facts,
        received_messages=list(state.messages_by_agent.get(turn.agent_id, [])),
        required_decisions=turn.required_decisions,
        assessment_evidence=turn.assessment_evidence,
        trust_prior_by_counterparty=state.trust_state[turn.agent_id],
        private_memory=state.private_memory_by_agent.get(turn.agent_id, ""),
    )


def _validate_submission(observation: AgentObservation, submission: AgentSubmission) -> list[str]:
    errors: list[str] = []
    required_by_node = {request.node_id: request for request in observation.required_decisions}
    submitted_by_node: dict[str, DecisionSelection] = {}
    for selection in submission.decisions:
        if selection.node_id in submitted_by_node:
            errors.append(f"duplicate decision for {selection.node_id}")
            continue
        submitted_by_node[selection.node_id] = selection
    if required_by_node:
        missing = sorted(set(required_by_node) - set(submitted_by_node))
        if missing:
            errors.append("missing required decisions: " + ", ".join(missing))
    for node_id, selection in submitted_by_node.items():
        request = required_by_node.get(node_id)
        if request is None:
            errors.append(f"decision {node_id} is not available in this phase")
            continue
        if request.actor_id != observation.agent_id:
            errors.append(f"{observation.agent_id} is not authorized for {node_id}")
        if request.selection_mode == "single":
            option_ids = {option.option_id for option in request.options}
            if selection.option_id not in option_ids:
                coerced_option = _coerce_option_id(selection.option_id, option_ids)
                if coerced_option is None:
                    errors.append(f"invalid option {selection.option_id!r} for {node_id}")
                else:
                    selection.option_id = coerced_option
            if selection.parameters:
                errors.append(f"single-select decision {node_id} does not accept parameters")
        else:
            if selection.option_id not in {None, "__parameters__"}:
                errors.append(f"parameterized decision {node_id} must use option_id null or __parameters__")
            expected_keys = set(request.parameters)
            actual_keys = set(selection.parameters)
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            if missing:
                errors.append(f"missing parameters for {node_id}: {', '.join(missing)}")
            if extra:
                errors.append(f"unexpected parameters for {node_id}: {', '.join(extra)}")
            for name, allowed in request.parameters.items():
                if name in selection.parameters and selection.parameters[name] not in allowed:
                    coerced = _coerce_allowed_parameter(selection.parameters[name], allowed)
                    if coerced is _NO_COERCION:
                        errors.append(f"invalid parameter {name}={selection.parameters[name]!r} for {node_id}")
                    else:
                        selection.parameters[name] = coerced
    for communication in submission.communications:
        errors.extend(_validate_communication(observation.agent_id, communication))
    errors.extend(_validate_assessments(observation, submission))
    return errors


_NO_COERCION = object()


def _coerce_option_id(value: Any, option_ids: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_option_token(value)
    by_normalized = {_normalize_option_token(option_id): option_id for option_id in option_ids}
    if normalized in by_normalized:
        return by_normalized[normalized]
    aliases = {
        "current_source": "current_standard",
        "current_source_standard": "current_standard",
        "standard_current_source": "current_standard",
        "current_source_expedited": "current_expedited",
        "expedited_current_source": "current_expedited",
    }
    alias = aliases.get(normalized)
    if alias in option_ids:
        return alias
    if normalized.endswith("_source"):
        trimmed = normalized.removesuffix("_source")
        if trimmed in by_normalized:
            return by_normalized[trimmed]
    return None


def _normalize_option_token(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value.lower()).strip("_")


def _coerce_allowed_parameter(value: Any, allowed: list[Any]) -> Any:
    if not isinstance(value, str):
        return _NO_COERCION
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in {"none", "null"} and any(allowed_value is None for allowed_value in allowed):
        return None
    if lowered in {"true", "false"}:
        parsed_bool = lowered == "true"
        for allowed_value in allowed:
            if isinstance(allowed_value, bool) and allowed_value is parsed_bool:
                return allowed_value
    for allowed_value in allowed:
        if isinstance(allowed_value, bool) or allowed_value is None:
            continue
        if isinstance(allowed_value, int):
            try:
                parsed_int = int(stripped)
            except ValueError:
                continue
            if parsed_int == allowed_value:
                return allowed_value
        if isinstance(allowed_value, float):
            try:
                parsed_float = float(stripped)
            except ValueError:
                continue
            if parsed_float == allowed_value:
                return allowed_value
    return _NO_COERCION


def _validate_communication(agent_id: str, communication: Communication) -> list[str]:
    errors: list[str] = []
    if communication.communication_type == "private_message":
        if not communication.recipient_ids:
            errors.append("private_message requires at least one recipient")
        invalid = [recipient for recipient in communication.recipient_ids if recipient not in AGENT_IDS]
        if invalid:
            errors.append(f"unknown private message recipients: {invalid}")
    elif communication.communication_type == "public_message":
        if communication.recipient_ids:
            errors.append("public_message recipient_ids must be empty")
    elif communication.communication_type == "publish_decision":
        if communication.recipient_ids:
            errors.append("publish_decision recipient_ids must be empty")
        if not communication.decision_record_id:
            errors.append("publish_decision requires decision_record_id")
    for claim in communication.claims:
        expected_type = CLAIM_TYPES.get(claim.field)
        if expected_type is None:
            errors.append(f"claim field {claim.field!r} is not in the claim registry")
        elif not isinstance(claim.value, expected_type):
            errors.append(f"claim field {claim.field!r} has invalid value type")
    return errors


def _validate_assessments(observation: AgentObservation, submission: AgentSubmission) -> list[str]:
    errors: list[str] = []
    evidence_ids = {evidence.evidence_id for evidence in observation.assessment_evidence}
    covered: set[str] = set()
    for update in submission.assessment_updates:
        errors.extend(_validate_assessment_update(observation, update, evidence_ids))
        covered.update(update.evidence_ids)
    for review in submission.assessment_reviews:
        unknown = sorted(set(review.evidence_ids) - evidence_ids)
        if unknown:
            errors.append(f"assessment review references unavailable evidence: {unknown}")
        if not review.reason.strip():
            errors.append("assessment no-update review requires a reason")
        covered.update(review.evidence_ids)
    missing = sorted(evidence_ids - covered)
    if missing:
        errors.append("assessment evidence requires update or explicit no-update review: " + ", ".join(missing))
    return errors


def _validate_assessment_update(
    observation: AgentObservation,
    update: AssessmentUpdate,
    evidence_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if update.counterparty_id == observation.agent_id:
        errors.append("agent cannot update assessment of itself")
    if update.counterparty_id not in observation.trust_prior_by_counterparty:
        errors.append(f"unknown assessment counterparty {update.counterparty_id}")
        return errors
    unknown = sorted(set(update.evidence_ids) - evidence_ids)
    if unknown:
        errors.append(f"assessment update references unavailable evidence: {unknown}")
    prior = observation.trust_prior_by_counterparty[update.counterparty_id]
    expected_prior = TrustValues(
        performance_reliability=prior.performance_reliability,
        information_reliability=prior.information_reliability,
        contractual_reliability=prior.contractual_reliability,
    )
    if update.prior != expected_prior:
        errors.append(f"assessment prior for {update.counterparty_id} does not match current state")
    if update.updated == update.prior:
        errors.append("unchanged assessment scores must be submitted as assessment_reviews no_update")
    if not update.reason.strip():
        errors.append("assessment update requires a reason")
    return errors


def _apply_submission(
    state: RunState,
    events: list[Event],
    scenario: Scenario,
    phase: Phase,
    turn: PhaseTurn,
    observation: AgentObservation,
    submission: AgentSubmission,
) -> None:
    for selection in submission.decisions:
        scenario.apply_decision(state, selection)
        record = {
            "decision_record_id": f"decision_{len(state.histories['decision_history']) + 1:06d}",
            "phase_index": state.phase_index,
            "phase_id": phase.phase_id,
            "actor_id": turn.agent_id,
            "node_id": selection.node_id,
            "option_id": selection.option_id or "__parameters__",
            "parameters": dict(selection.parameters),
        }
        state.histories["decision_history"].append(record)
        state.private_state_by_agent[turn.agent_id].setdefault("own_decision_records", []).append(
            record
        )
        record_event(
            state,
            events,
            "decision_applied",
            actor_id=turn.agent_id,
            details={"decision": record, "state_after": state.model_dump(mode="json")},
        )
    for communication in submission.communications:
        _apply_communication(state, events, phase, turn.agent_id, communication)
    for update in submission.assessment_updates:
        _apply_assessment_update(state, events, phase, turn.agent_id, update)
    for review in submission.assessment_reviews:
        _apply_assessment_review(state, events, phase, turn.agent_id, review)
    if submission.private_notes.strip():
        state.private_memory_by_agent[turn.agent_id] = submission.private_notes.strip()
    if observation.assessment_evidence:
        reviewed_ids = {
            evidence_id
            for update in submission.assessment_updates
            for evidence_id in update.evidence_ids
        } | {
            evidence_id
            for review in submission.assessment_reviews
            for evidence_id in review.evidence_ids
        }
        state.private_state_by_agent[turn.agent_id]["last_reviewed_evidence_ids"] = sorted(reviewed_ids)


def _apply_communication(
    state: RunState,
    events: list[Event],
    phase: Phase,
    actor_id: str,
    communication: Communication,
) -> None:
    message_id = f"message_{len(state.histories['message_history']) + 1:06d}"
    record = {
        "message_id": message_id,
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id,
        "sender_id": actor_id,
        "communication_type": communication.communication_type,
        "recipient_ids": list(communication.recipient_ids),
        "summary": communication.summary,
        "claims": [claim.model_dump(mode="json") for claim in communication.claims],
        "decision_record_id": communication.decision_record_id,
    }
    state.histories["message_history"].append(record)
    if communication.communication_type == "private_message":
        for recipient in communication.recipient_ids:
            state.messages_by_agent[recipient].append(record)
    else:
        state.public_state["ledger"].append(record)
        state.public_facts.append(
            {
                "event_id": message_id,
                "source": actor_id,
                "summary": communication.summary,
                "claims": record["claims"],
            }
        )
    record_event(
        state,
        events,
        "communication_delivered",
        actor_id=actor_id,
        details={"message": record, "state_after": state.model_dump(mode="json")},
    )


def _apply_assessment_update(
    state: RunState,
    events: list[Event],
    phase: Phase,
    actor_id: str,
    update: AssessmentUpdate,
) -> None:
    prior = state.trust_state[actor_id][update.counterparty_id]
    state.trust_state[actor_id][update.counterparty_id] = prior.model_copy(
        update={
            "performance_reliability": update.updated.performance_reliability,
            "information_reliability": update.updated.information_reliability,
            "contractual_reliability": update.updated.contractual_reliability,
            "last_updated_phase": state.phase_index,
            "evidence_ids": list(update.evidence_ids),
        }
    )
    record = {
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id,
        "assessor_id": actor_id,
        "counterparty_id": update.counterparty_id,
        "evidence_ids": list(update.evidence_ids),
        "prior": prior.model_dump(mode="json"),
        "updated": update.updated.model_dump(mode="json"),
        "reason": update.reason,
    }
    state.histories["assessment_history"].append(record)
    record_event(
        state,
        events,
        "assessment_updated",
        actor_id=actor_id,
        details={"assessment_update": record, "state_after": state.model_dump(mode="json")},
    )


def _apply_assessment_review(
    state: RunState,
    events: list[Event],
    phase: Phase,
    actor_id: str,
    review: AssessmentReview,
) -> None:
    record = {
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id,
        "assessor_id": actor_id,
        "evidence_ids": list(review.evidence_ids),
        "counterparty_ids": list(review.counterparty_ids),
        "review_result": review.review_result,
        "reason": review.reason,
    }
    state.histories["assessment_review_history"].append(record)
    record_event(
        state,
        events,
        "assessment_reviewed_no_update",
        actor_id=actor_id,
        details={"assessment_review": record, "state_after": state.model_dump(mode="json")},
    )


def _mark_phase_done(state: RunState, events: list[Event], phase: Phase) -> None:
    record = {
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id,
        "phase_type": phase.phase_type,
        "summary": phase.summary,
    }
    state.histories["phase_history"].append(record)
    record_event(
        state,
        events,
        "phase_completed",
        details={"phase": record, "state_after": state.model_dump(mode="json")},
    )


def _mark_invalid(
    state: RunState,
    events: list[Event],
    actor_id: str | None,
    phase: Phase | None,
    reason: str,
) -> None:
    state.run_valid = False
    state.terminal_status = "INVALID_AGENT_OUTPUT"
    state.terminal_reason = reason
    record = {
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id if phase else None,
        "actor_id": actor_id,
        "reason": reason,
    }
    state.histories["invalid_outputs"].append(record)
    record_event(
        state,
        events,
        "invalid_agent_output",
        actor_id=actor_id,
        details={"invalid_output": record, "state_after": state.model_dump(mode="json")},
    )


def _turn_summary(state: RunState, phase: Phase, active_agents: list[str]) -> dict[str, Any]:
    phase_decisions = [
        record
        for record in state.histories["decision_history"]
        if record["phase_index"] == state.phase_index
    ]
    phase_messages = [
        record
        for record in state.histories["message_history"]
        if record["phase_index"] == state.phase_index
    ]
    phase_assessments = [
        record
        for record in state.histories["assessment_history"]
        if record["phase_index"] == state.phase_index
    ]
    phase_reviews = [
        record
        for record in state.histories["assessment_review_history"]
        if record["phase_index"] == state.phase_index
    ]
    return {
        "phase_index": state.phase_index,
        "phase_id": phase.phase_id,
        "phase_type": phase.phase_type,
        "summary": phase.summary,
        "active_agents": active_agents,
        "decisions": phase_decisions,
        "communications": phase_messages,
        "assessment_updates": phase_assessments,
        "assessment_reviews": phase_reviews,
        "terminal_status": state.terminal_status,
        "run_valid": state.run_valid,
    }


def _drain_model_io(state: RunState, policy: AgentPolicy) -> None:
    if hasattr(policy, "drain_model_io"):
        state.histories["model_io"].extend(policy.drain_model_io())  # type: ignore[attr-defined]
