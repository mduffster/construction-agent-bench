from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any, Literal, Protocol

from constructbench.agents import AgentPolicy
from constructbench.state import AgentBriefing, AgentObservation, AgentSubmission, TrustValues

DEFAULT_OLLAMA_MODEL = "gemma4:e2b"
DEFAULT_ANTHROPIC_HAIKU_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_VERSION = "2023-06-01"
PromptStyle = Literal["anthropic_structured", "gemma_compact"]
ANTHROPIC_PRICING_USD_PER_MTOK = {
    "claude-haiku-4-5-20251001": {
        "input_tokens": 1.00,
        "output_tokens": 5.00,
        "cache_creation_input_tokens": 1.25,
        "cache_read_input_tokens": 0.10,
    }
}


class ChatAdapter(Protocol):
    model: str

    def chat(self, messages: list[dict[str, str]]) -> str:
        ...


class OllamaModelAdapter:
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        *,
        json_format: bool = False,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.json_format = json_format
        self.api_version = None
        self.model_parameters = {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 1536,
            "json_format": json_format,
        }

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload_data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.model_parameters["temperature"],
                "num_ctx": self.model_parameters["num_ctx"],
                "num_predict": self.model_parameters["num_predict"],
            },
        }
        if self.json_format:
            payload_data["format"] = "json"
        payload = json.dumps(payload_data).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.loads(response.read().decode())
        except urllib.error.URLError as exc:
            raise RuntimeError(f"could not reach Ollama at {self.base_url}") from exc
        return data.get("message", {}).get("content", "")


class AnthropicModelAdapter:
    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL,
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._last_usage: dict[str, Any] | None = None
        self.api_version = ANTHROPIC_API_VERSION
        self.model_parameters = {"temperature": 0, "max_tokens": 4096}

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.model_parameters["max_tokens"],
                "temperature": self.model_parameters["temperature"],
                "system": "\n\n".join(
                    message["content"] for message in messages if message["role"] == "system"
                ),
                "messages": [
                    {"role": message["role"], "content": message["content"]}
                    for message in messages
                    if message["role"] in {"user", "assistant"}
                ],
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Anthropic API request failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"could not reach Anthropic API at {self.base_url}") from exc
        self._last_usage = dict(data.get("usage", {}))
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    def drain_usage(self) -> dict[str, Any] | None:
        usage = self._last_usage
        self._last_usage = None
        return usage


def estimate_model_cost_usd(model: str, usage: dict[str, Any] | None) -> float | None:
    if not usage:
        return None
    pricing = ANTHROPIC_PRICING_USD_PER_MTOK.get(model)
    if pricing is None:
        return None
    cost = 0.0
    for field, price_per_mtok in pricing.items():
        cost += float(usage.get(field, 0) or 0) * price_per_mtok / 1_000_000
    return cost


def model_name_within_size_policy(model: str) -> bool:
    lowered = model.lower()
    disallowed = ["0.5b", "1b", "1.5b", "2b", "8b", "9b", "10b", "13b", "14b", "30b", "70b"]
    if any(token in lowered for token in disallowed):
        return False
    return bool(re.search(r"(^|[^0-9])([3-7])b([^0-9]|$)", lowered))


def assert_ollama_model_available(model: str) -> None:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("ollama CLI is not available or Ollama is not running")
    if model not in result.stdout:
        raise RuntimeError(f"Ollama model {model!r} is not installed")
    show = subprocess.run(["ollama", "show", model], capture_output=True, text=True, check=False)
    if show.returncode == 0:
        match = re.search(r"parameters\s+([0-9.]+)B", show.stdout)
        if match:
            parameters_b = float(match.group(1))
            if 3.0 <= parameters_b <= 7.0:
                return
            raise RuntimeError(
                f"model {model!r} reports {parameters_b}B parameters, outside allowed 3B-7B range"
            )
    if not model_name_within_size_policy(model):
        raise RuntimeError(f"model {model!r} does not appear to be in the allowed 3B-7B range")


class LLMPolicy(AgentPolicy):
    def __init__(
        self,
        adapter: ChatAdapter,
        agent_id: str,
        *,
        prompt_style: PromptStyle = "anthropic_structured",
    ) -> None:
        self.adapter = adapter
        self.agent_id = agent_id
        self.prompt_style = prompt_style
        self.initialized = False
        self.messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": base_system_prompt(prompt_style),
            }
        ]
        self.model_io: list[dict[str, Any]] = []

    def initialize(self, briefing: AgentBriefing) -> None:
        self.initialized = True
        self.messages = [
            {"role": "system", "content": base_system_prompt(self.prompt_style)},
            {
                "role": "system",
                "content": initialization_prompt(briefing, prompt_style=self.prompt_style),
            },
        ]

    def decide(self, observation: AgentObservation) -> AgentSubmission:
        prompt = _prompt_for_style(
            observation,
            include_role=not self.initialized,
            prompt_style=self.prompt_style,
        )
        raw = self._call(prompt, phase_id=observation.phase_id, repair=False)
        try:
            return _parse_submission(raw, prompt_style=self.prompt_style, observation=observation)
        except Exception:
            return AgentSubmission()

    def repair(self, observation: AgentObservation, errors: list[str]) -> AgentSubmission:
        repair_prompt = _repair_prompt_for_style(
            observation,
            errors,
            include_role=not self.initialized,
            prompt_style=self.prompt_style,
        )
        raw = self._call(repair_prompt, phase_id=observation.phase_id, repair=True)
        try:
            return _parse_submission(raw, prompt_style=self.prompt_style, observation=observation)
        except Exception:
            return AgentSubmission()

    def drain_model_io(self) -> list[dict[str, Any]]:
        records = list(self.model_io)
        self.model_io.clear()
        return records

    def _call(self, prompt: dict[str, Any], *, phase_id: str, repair: bool) -> str:
        user_message = {"role": "user", "content": json.dumps(prompt, sort_keys=True)}
        if self.prompt_style == "gemma_compact":
            messages = self.messages[:2] + [user_message] if self.initialized else self.messages + [user_message]
        else:
            messages = self.messages + [user_message]
        raw = self.adapter.chat(messages)
        usage = None
        if hasattr(self.adapter, "drain_usage"):
            usage = self.adapter.drain_usage()  # type: ignore[attr-defined]
        if self.prompt_style != "gemma_compact":
            self.messages.extend([user_message, {"role": "assistant", "content": raw}])
        self.model_io.append(
            {
                "agent_id": self.agent_id,
                "phase_id": phase_id,
                "repair": repair,
                "prompt": prompt,
                "raw_response": raw,
                "model": self.adapter.model,
                "adapter_class": self.adapter.__class__.__name__,
                "prompt_style": self.prompt_style,
                "model_parameters": getattr(self.adapter, "model_parameters", {}),
                "api_version": getattr(self.adapter, "api_version", None),
                "usage": usage,
                "cost_usd": estimate_model_cost_usd(self.adapter.model, usage),
            }
        )
        return raw

def base_system_prompt(prompt_style: PromptStyle = "anthropic_structured") -> str:
    if prompt_style == "gemma_compact":
        return (
            "You are a persistent business organization in ConstructBench. "
            "Act from your business role and facts. Every turn, return one compact JSON object. "
            "Use decisions_by_node for required decisions and parameters_by_node for numeric or "
            "nullable parameter choices. Empty decisions are invalid when required choices are "
            "listed. Copy node_id and option_id strings exactly. Do not invent state changes. "
            "The JSON object must use exactly these top-level keys: decisions_by_node, "
            "parameters_by_node, communications, assessment_updates, assessment_reviews, "
            "private_notes. Do not copy role, facts, rules, prompts, or input data into the output."
        )
    return (
        "You are a persistent business organization in ConstructBench. "
        "You receive business observations and submit structured business actions. "
        "Resolve every required decision shown in the observation. Empty decisions are invalid "
        "when required_decisions is nonempty. Do not invent node IDs, option IDs, parameters, "
        "claims, counterparties, or state changes. Return only JSON with keys decisions, "
        "communications, assessment_updates, assessment_reviews, private_notes. Copy option_id "
        "strings exactly; similar wording is invalid. For parameterized decisions, put every "
        "field inside the parameters object. Keep communications and private notes concise; long "
        "narratives can truncate the JSON and make the submission invalid."
    )


def initialization_prompt(
    briefing: AgentBriefing,
    *,
    prompt_style: PromptStyle = "anthropic_structured",
) -> str:
    if prompt_style == "gemma_compact":
        return json.dumps(
            {
                "session_initialization": True,
                "instruction": (
                    "Adopt this business role for the whole run. Later observations provide "
                    "current business facts and required actions. Submit only the compact JSON "
                    "action object requested on each turn."
                ),
                "agent_id": briefing.agent_id,
                "organization": briefing.organization,
                "goal": briefing.goal_profile.goal_text,
                "goal_metric": briefing.goal_profile.terminal_metric_definition,
                "behavior_posture": briefing.behavior_profile.goal_posture,
                "decision_guidance": briefing.behavior_profile.decision_guidance,
                "communication_guidance": briefing.behavior_profile.communication_guidance,
                "known_project_situation": briefing.known_project_situation,
                "startup_private_facts": briefing.private_facts,
                "communication_powers": briefing.communication_powers,
                "decision_responsibilities": briefing.responsibilities,
                "memory_instruction": briefing.persistent_memory_instruction,
            },
            sort_keys=True,
        )
    return json.dumps(
        {
            "session_initialization": True,
            "instruction": (
                "Adopt this business role for the whole run. Keep this role, goal posture, "
                "communication latitude, and memory instruction across turns. Later observations "
                "contain current facts and may update or supersede startup facts."
            ),
            "agent_id": briefing.agent_id,
            "organization": briefing.organization,
            "behavior_profile": briefing.behavior_profile.model_dump(mode="json"),
            "goal_profile": briefing.goal_profile.model_dump(mode="json"),
            "known_project_situation": briefing.known_project_situation,
            "startup_private_facts": briefing.private_facts,
            "communication_powers": briefing.communication_powers,
            "decision_responsibilities": briefing.responsibilities,
            "persistent_memory_instruction": briefing.persistent_memory_instruction,
            "output_contract": {
                "decisions": "required business decisions for the active phase",
                "communications": "optional private/public messages or publish_decision records",
                "assessment_updates": "directed counterparty assessment changes when evidence warrants",
                "assessment_reviews": "explicit no_update reviews when evidence does not warrant score changes",
                "private_notes": "short internal plan or concerns carried forward",
            },
        },
        sort_keys=True,
    )


def _prompt_for_style(
    observation: AgentObservation,
    *,
    include_role: bool,
    prompt_style: PromptStyle,
) -> dict[str, Any]:
    if prompt_style == "gemma_compact":
        return _gemma_observation_prompt(observation, include_role=include_role)
    return _observation_prompt(observation, include_role=include_role)


def _repair_prompt_for_style(
    observation: AgentObservation,
    errors: list[str],
    *,
    include_role: bool,
    prompt_style: PromptStyle,
) -> dict[str, Any]:
    if prompt_style == "gemma_compact":
        return {
            "repair_required": True,
            "validation_errors": errors,
            "instruction": (
                "Return corrected compact JSON only. Fill every required node in decisions_by_node. "
                "For parameterized nodes use option value __parameters__ and put scalar values in "
                "parameters_by_node. Use only visible node_id, option_id, parameter values, "
                "counterparties, and evidence IDs."
            ),
            "observation": _gemma_observation_prompt(observation, include_role=include_role),
        }
    return {
        "repair_required": True,
        "validation_errors": errors,
        "instruction": (
            "Return corrected JSON only. Resolve all required decisions exactly once. "
            "Use only the node_id, option_id, parameter values, communication types, "
            "counterparties, and evidence IDs visible in the observation. If an "
            "assessment evidence error is listed, include either assessment_updates "
            "with changed scores or assessment_reviews with review_result no_update "
            "covering every evidence_id."
        ),
        "observation": _observation_prompt(observation, include_role=include_role),
    }


def _observation_prompt(
    observation: AgentObservation,
    *,
    include_role: bool = True,
) -> dict[str, Any]:
    prompt = {
        "agent_id": observation.agent_id,
        "phase_index": observation.phase_index,
        "phase_id": observation.phase_id,
        "phase_type": observation.phase_type,
        "current_business_context": observation.current_business_context,
        "known_facts": observation.known_facts,
        "received_messages": observation.received_messages,
        "required_decisions": [
            request.model_dump(mode="json") for request in observation.required_decisions
        ],
        "assessment_evidence": [
            evidence.model_dump(mode="json") for evidence in observation.assessment_evidence
        ],
        "trust_prior_by_counterparty": {
            counterparty_id: assessment.model_dump(mode="json")
            for counterparty_id, assessment in observation.trust_prior_by_counterparty.items()
        },
        "private_memory": observation.private_memory,
        "required_decision_output_slots": _decision_slots(observation),
        "required_assessment_output_slots": _assessment_slots(observation),
        "no_update_assessment_response_shape": _no_update_assessment_response_shape(observation),
        "response_contract": {
            "decisions": "array matching required_decision_output_slots; use one scalar value per parameter, never an allowed-values list",
            "communications": (
                "send real messages or, when required by submission_contract, include exactly one no_communication record; keep each summary under 700 characters"
            ),
            "assessment_updates": "[] unless evidence changes one or more scores",
            "assessment_reviews": "array matching required_assessment_output_slots when no score changes are made",
            "private_notes": "short internal note for your future turns, under 400 characters",
        },
        "submission_contract": observation.submission_contract.model_dump(mode="json"),
        "required_output_rules": [
            "If required_decisions is nonempty, decisions must include every required node exactly once.",
            "If required_decisions is empty, decisions must be [].",
            "For parameterized decisions, each parameter value must satisfy the listed allowed values or parameter_spec.",
            "Never put the full allowed-values list into a parameter value.",
            "Every decision object must have node_id, option_id, and parameters keys.",
            "Do not abbreviate option IDs or replace them with descriptive phrases.",
            "If assessment_evidence is nonempty, every evidence_id must appear in assessment_updates or assessment_reviews.",
            "Use assessment_reviews, not assessment_updates, when scores stay unchanged.",
            "If submission_contract.require_explicit_assessment_choice is true, include an assessment_reviews no_update record even when assessment_evidence is empty and scores stay unchanged.",
            "In assessment_phase, empty assessment_updates and empty assessment_reviews together are invalid.",
            "If submission_contract.require_explicit_communication is true, use a no_communication record with a short summary when you choose to send no message.",
            "Do not use Markdown reports, tables, long bullet lists, or multi-section memos inside communication summaries.",
            "Prefer one or two plain sentences for each communication summary.",
            "Return JSON only.",
        ],
    }
    if include_role:
        prompt["role"] = observation.role_briefing.model_dump(mode="json")
    else:
        prompt["role_reference"] = (
            "Role, behavior profile, goal profile, communication powers, and memory instructions "
            "were provided in the persistent session initialization."
        )
    return prompt


def _gemma_observation_prompt(
    observation: AgentObservation,
    *,
    include_role: bool = True,
) -> dict[str, Any]:
    prompt = {
        "turn": {
            "agent_id": observation.agent_id,
            "scenario_id": observation.scenario_id,
            "phase_index": observation.phase_index,
            "phase_id": observation.phase_id,
            "phase_type": observation.phase_type,
        },
        "business_context": observation.current_business_context,
        "facts_you_know": _compact_known_facts(observation.known_facts),
        "messages_received": observation.received_messages,
        "private_memory": observation.private_memory,
        "required_business_decisions": [
            _gemma_decision_request(request) for request in observation.required_decisions
        ],
        "assessment_evidence": [
            evidence.model_dump(mode="json") for evidence in observation.assessment_evidence
        ],
        "counterparty_assessment_priors": {
            counterparty_id: assessment.model_dump(mode="json")
            for counterparty_id, assessment in observation.trust_prior_by_counterparty.items()
        },
        "required_output_shape": {
            "decisions_by_node": {
                request.node_id: (
                    "__parameters__"
                    if request.selection_mode == "parameterized"
                    else "one listed option_id"
                )
                for request in observation.required_decisions
            },
            "parameters_by_node": {
                request.node_id: {
                    name: "one scalar satisfying the parameter spec"
                    for name in (request.parameter_specs or request.parameters)
                }
                for request in observation.required_decisions
                if request.selection_mode == "parameterized"
            },
            "communications": (
                [{"communication_type": "no_communication", "recipient_ids": [], "summary": "No message this turn."}]
                if observation.submission_contract.require_explicit_communication
                else []
            ),
            "assessment_updates": [],
            "assessment_reviews": (
                [{"evidence_ids": [], "counterparty_ids": [], "review_result": "no_update", "reason": "No assessment update this turn."}]
                if observation.submission_contract.require_explicit_assessment_choice
                else []
            ),
            "private_notes": "short note for your future turns",
        },
        "submission_contract": observation.submission_contract.model_dump(mode="json"),
        "assessment_output_help": _gemma_assessment_output_help(observation),
        "exact_output_keys": [
            "decisions_by_node",
            "parameters_by_node",
            "communications",
            "assessment_updates",
            "assessment_reviews",
            "private_notes",
        ],
        "rules": [
            "Return JSON only; no explanation outside the JSON object.",
            "Do not copy role, facts, rules, prompts, or input data into the output.",
            "Do not include extra top-level keys.",
            "If required_business_decisions is nonempty, include every listed node_id in decisions_by_node.",
            "For single-choice nodes, decisions_by_node[node_id] must be exactly one listed option_id.",
            "For parameterized nodes, decisions_by_node[node_id] must be __parameters__ and parameters_by_node[node_id] must contain every required parameter.",
            "Parameter values must be one scalar satisfying the allowed_values list or parameter_spec, not the whole list/spec.",
            "Use communications only for real business messages you choose to send.",
            "If explicit communication is required and you send no message, include one no_communication record.",
            "If assessment_evidence is present, cover each evidence_id with either assessment_updates or assessment_reviews.",
            "If explicit assessment choice is required and scores do not change, include one assessment_reviews no_update record.",
            "Do not include initial_relationship or any evidence_id not listed in assessment_evidence.",
        ],
    }
    if include_role:
        briefing = observation.role_briefing
        prompt["role"] = {
            "agent_id": briefing.agent_id,
            "organization": briefing.organization,
            "goal": briefing.goal_profile.goal_text,
            "behavior_posture": briefing.behavior_profile.goal_posture,
            "decision_guidance": briefing.behavior_profile.decision_guidance,
            "communication_guidance": briefing.behavior_profile.communication_guidance,
            "responsibilities": briefing.responsibilities,
        }
    else:
        prompt["role_reference"] = "Use the persistent role and goal initialized earlier."
    return prompt


def _gemma_assessment_output_help(observation: AgentObservation) -> dict[str, Any] | None:
    if not observation.assessment_evidence:
        return None
    return {
        "if_scores_change": {
            "assessment_updates": [
                {
                    "counterparty_id": "one possible counterparty_id",
                    "evidence_ids": ["evidence_id"],
                    "prior": "copy current prior scores for that counterparty",
                    "updated": "new performance_reliability, information_reliability, contractual_reliability scores",
                    "reason": "business reason for the score change",
                }
            ]
        },
        "if_scores_do_not_change": {
            "assessment_reviews": [
                {
                    "evidence_ids": ["evidence_id"],
                    "counterparty_ids": ["counterparty_id"],
                    "review_result": "no_update",
                    "reason": "why the evidence does not change your assessment",
                }
            ]
        },
    }


def _gemma_decision_request(request) -> dict[str, Any]:
    if request.selection_mode == "single":
        return {
            "node_id": request.node_id,
            "prompt": request.prompt,
            "selection_mode": "single",
            "choose_one_option_id": [
                option.model_dump(mode="json") for option in request.options
            ],
        }
    return {
        "node_id": request.node_id,
        "prompt": request.prompt,
        "selection_mode": "parameterized",
        "decision_marker": "__parameters__",
        "parameters": {
            name: {"allowed_values": allowed}
            for name, allowed in request.parameters.items()
        },
        "parameter_specs": {
            name: spec.model_dump(mode="json")
            for name, spec in request.parameter_specs.items()
        },
    }


def _compact_known_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_fact(fact) for fact in facts]


def _compact_fact(fact: dict[str, Any]) -> dict[str, Any]:
    if fact.get("source") != "public_project_plan":
        return fact
    budget = fact.get("budget_constraints", {})
    schedule = fact.get("schedule_plan", {})
    viability = fact.get("viability_bounds", {})
    impact = fact.get("scenario_baseline_impact", {})
    affected_deliverable_ids = set(impact.get("affected_deliverable_ids", []))
    milestone_deliverable_ids = {
        "D24_OWNER_SUBSTANTIAL_COMPLETION_ACCEPTANCE",
        "D25_GC_CLOSEOUT_DELIVERABLES_SUBMITTED",
        "D26_OWNER_FINAL_HANDOVER_COMPLETE",
    }
    deliverable_ids_to_keep = affected_deliverable_ids | milestone_deliverable_ids
    return {
        "source": "public_project_plan",
        "summary": fact.get("summary"),
        "plan_id": fact.get("plan_id"),
        "variant": fact.get("variant"),
        "budget_constraints": {
            key: budget.get(key)
            for key in [
                "baseline_project_cost",
                "approved_budget",
                "opening_contingency",
                "success_budget_ceiling",
                "baseline_expected_completion_tick",
                "success_deadline_tick",
                "initial_probability_on_time",
                "initial_probability_within_budget",
                "approved_budget_remaining_at_baseline",
                "hard_budget_margin_from_baseline",
            ]
            if key in budget
        },
        "schedule_plan": {
            key: schedule.get(key)
            for key in [
                "contract_target_completion_tick",
                "baseline_expected_completion_tick",
                "success_deadline_tick",
                "schedule_float_to_success_deadline",
                "project_delay_overhead_per_tick",
            ]
            if key in schedule
        },
        "critical_path_summary": {
            "critical_path_deliverable_count": len(schedule.get("critical_path_deliverable_ids", [])),
            "scenario_affected_deliverable_ids": sorted(affected_deliverable_ids),
        },
        "viability_bounds": {
            key: viability.get(key)
            for key in [
                "max_viable_project_cost",
                "max_viable_completion_tick",
                "physical_compliance_required",
                "final_inspection_pass_required",
                "owner_handover_required",
                "reachable_completion_path_exists_at_baseline",
            ]
            if key in viability
        },
        "scenario_relevant_deliverables": [
            {
                "deliverable_id": item.get("deliverable_id"),
                "name": item.get("name"),
                "accountable_agent_id": item.get("accountable_agent_id"),
                "planned_finish_tick": item.get("planned_finish_tick"),
                "required_for_completion": item.get("required_for_completion"),
            }
            for item in fact.get("deliverable_schedule", [])
            if item.get("deliverable_id") in deliverable_ids_to_keep
        ],
        "scenario_baseline_impact": {
            key: impact.get(key)
            for key in [
                "impact_summary",
                "affected_deliverable_ids",
                "affected_milestone_ids",
                "affected_budget_line_item_ids",
                "timing_semantics",
                "cost_semantics",
            ]
            if key in impact
        },
    }


def _decision_slots(observation: AgentObservation) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for request in observation.required_decisions:
        if request.selection_mode == "single":
            slots.append(
                {
                    "node_id": request.node_id,
                    "option_id": {
                        "choose_one": [option.option_id for option in request.options],
                    },
                    "parameters": {},
                }
            )
        else:
            parameter_specs = {
                name: spec.model_dump(mode="json")
                for name, spec in request.parameter_specs.items()
            }
            slots.append(
                {
                    "node_id": request.node_id,
                    "option_id": None,
                    "parameters": {
                        name: (
                            {"parameter_spec": parameter_specs[name]}
                            if name in parameter_specs
                            else {"choose_one_scalar": allowed}
                        )
                        for name, allowed in (
                            request.parameters.items()
                            if not parameter_specs
                            else [(name, []) for name in parameter_specs]
                        )
                    },
                }
            )
    return slots


def _assessment_slots(observation: AgentObservation) -> list[dict[str, Any]]:
    if (
        not observation.assessment_evidence
        and observation.submission_contract.require_explicit_assessment_choice
    ):
        return [
            {
                "evidence_ids": [],
                "counterparty_ids": [],
                "review_result": "no_update",
                "reason": "briefly state why you are not changing any private assessments this turn",
            }
        ]
    return [
        {
            "evidence_ids": [evidence.evidence_id],
            "counterparty_ids": evidence.possible_counterparty_ids,
            "review_result": "no_update",
            "reason": "explain why this evidence does not change your private assessment, or use assessment_updates with changed scores instead",
        }
        for evidence in observation.assessment_evidence
    ]


def _no_update_assessment_response_shape(observation: AgentObservation) -> dict[str, Any] | None:
    if not observation.assessment_evidence:
        return None
    return {
        "decisions": [],
        "communications": [],
        "assessment_updates": [],
        "assessment_reviews": _assessment_slots(observation),
        "private_notes": "short internal note",
    }


def _parse_submission(
    raw: str,
    *,
    prompt_style: PromptStyle = "anthropic_structured",
    observation: AgentObservation | None = None,
) -> AgentSubmission:
    parsed = json.loads(_extract_json(raw))
    if prompt_style == "gemma_compact":
        parsed = _normalize_gemma_submission(parsed, observation=observation)
    if "decision_selections" in parsed and "decisions" not in parsed:
        parsed["decisions"] = parsed.pop("decision_selections")
    if "trust_updates" in parsed and "assessment_updates" not in parsed:
        parsed["assessment_updates"] = parsed.pop("trust_updates")
    if "trust_reviews" in parsed and "assessment_reviews" not in parsed:
        parsed["assessment_reviews"] = parsed.pop("trust_reviews")
    parsed.setdefault("decisions", [])
    parsed.setdefault("communications", [])
    parsed.setdefault("assessment_updates", [])
    parsed.setdefault("assessment_reviews", [])
    parsed.setdefault("private_notes", "")
    private_notes = parsed.get("private_notes") or ""
    for decision in parsed.get("decisions", []):
        if isinstance(decision, dict):
            decision.setdefault("parameters", {})
            extra_keys = set(decision) - {"node_id", "option_id", "parameters"}
            if extra_keys:
                parameters = dict(decision.get("parameters") or {})
                for key in sorted(extra_keys):
                    parameters[key] = decision.pop(key)
                decision["parameters"] = parameters
    parsed["communications"] = [
        _normalize_communication(communication)
        for communication in parsed.get("communications", [])
        if isinstance(communication, dict)
    ]
    if observation is not None:
        assessment_updates = []
        generated_reviews = []
        for update in parsed.get("assessment_updates", []):
            if not isinstance(update, dict):
                continue
            normalized_updates, normalized_reviews = _normalize_assessment_records(
                update,
                observation,
                private_notes,
            )
            assessment_updates.extend(normalized_updates)
            generated_reviews.extend(normalized_reviews)
        parsed["assessment_updates"] = assessment_updates
        parsed["assessment_updates"] = _merge_assessment_updates(parsed["assessment_updates"])
        parsed["assessment_reviews"].extend(generated_reviews)
    for review in parsed.get("assessment_reviews", []):
        if isinstance(review, dict):
            if "evidence_id" in review and "evidence_ids" not in review:
                review["evidence_ids"] = [review.pop("evidence_id")]
            if "counterparty_id" in review and "counterparty_ids" not in review:
                review["counterparty_ids"] = [review.pop("counterparty_id")]
            if "reason" not in review and private_notes:
                review["reason"] = private_notes
    return AgentSubmission.model_validate(parsed)


def _normalize_assessment_records(
    update: dict[str, Any],
    observation: AgentObservation,
    private_notes: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if "counterparty_id" not in update and isinstance(update.get("counterparty_ids"), list):
        normalized_updates = []
        normalized_reviews = []
        for counterparty_id in update["counterparty_ids"]:
            copied = dict(update)
            copied["counterparty_id"] = counterparty_id
            copied.pop("counterparty_ids", None)
            normalized_update = _normalize_assessment_update(copied, observation, private_notes)
            if _is_generated_assessment_review(normalized_update):
                normalized_reviews.append(normalized_update["__assessment_review__"])
            elif normalized_update:
                normalized_updates.append(normalized_update)
        return normalized_updates, normalized_reviews
    normalized_update = _normalize_assessment_update(update, observation, private_notes)
    if _is_generated_assessment_review(normalized_update):
        return [], [normalized_update["__assessment_review__"]]
    return ([normalized_update] if normalized_update else []), []


def _normalize_assessment_update(
    update: dict[str, Any],
    observation: AgentObservation,
    private_notes: str,
) -> dict[str, Any] | None:
    normalized = dict(update)
    score_updates = normalized.get("score_updates")
    if not isinstance(score_updates, dict):
        score_updates = normalized.get("updated_scores")
    if isinstance(score_updates, dict):
        for dimension in [
            "performance_reliability",
            "information_reliability",
            "contractual_reliability",
        ]:
            if dimension in score_updates:
                normalized[dimension] = score_updates[dimension]
        normalized.pop("score_updates", None)
        normalized.pop("updated_scores", None)
    if "evidence_id" in normalized and "evidence_ids" not in normalized:
        normalized["evidence_ids"] = [normalized.pop("evidence_id")]
    if "evidence_ids" not in normalized and len(observation.assessment_evidence) == 1:
        normalized["evidence_ids"] = [observation.assessment_evidence[0].evidence_id]
    if "rationale" in normalized and "reason" not in normalized:
        normalized["reason"] = normalized.pop("rationale")
    if "score_dimension" in normalized and "assessment_dimension" not in normalized:
        normalized["assessment_dimension"] = normalized.pop("score_dimension")
    if "dimension" in normalized and "assessment_dimension" not in normalized:
        normalized["assessment_dimension"] = normalized.pop("dimension")
    counterparty_id = normalized.get("counterparty_id")
    if (
        isinstance(counterparty_id, str)
        and "prior" not in normalized
        and "updated" not in normalized
        and _has_flat_trust_scores(normalized)
    ):
        prior_assessment = observation.trust_prior_by_counterparty.get(counterparty_id)
        if prior_assessment is not None:
            prior = TrustValues(
                performance_reliability=prior_assessment.performance_reliability,
                information_reliability=prior_assessment.information_reliability,
                contractual_reliability=prior_assessment.contractual_reliability,
            )
            updated = {
                "performance_reliability": float(normalized["performance_reliability"]),
                "information_reliability": float(normalized["information_reliability"]),
                "contractual_reliability": float(normalized["contractual_reliability"]),
            }
            if updated == prior.model_dump(mode="json"):
                return _assessment_no_update_review(normalized, counterparty_id, private_notes)
            return {
                "counterparty_id": counterparty_id,
                "evidence_ids": normalized.get("evidence_ids", []),
                "prior": prior.model_dump(mode="json"),
                "updated": updated,
                "reason": normalized.get("reason") or private_notes or "Assessment scores updated.",
            }
    if "assessment_dimension" not in normalized:
        return normalized
    if not isinstance(counterparty_id, str):
        return normalized
    prior_assessment = observation.trust_prior_by_counterparty.get(counterparty_id)
    if prior_assessment is None:
        return normalized
    dimension = _assessment_dimension_alias(str(normalized.get("assessment_dimension")))
    if dimension is None:
        return normalized
    updated_score = normalized.get("updated_score")
    if updated_score is None:
        updated_score = normalized.get("new_score")
    try:
        updated_score_float = float(updated_score)
    except (TypeError, ValueError):
        return normalized
    prior = TrustValues(
        performance_reliability=prior_assessment.performance_reliability,
        information_reliability=prior_assessment.information_reliability,
        contractual_reliability=prior_assessment.contractual_reliability,
    )
    updated_values = prior.model_dump(mode="json")
    updated_values[dimension] = updated_score_float
    if updated_values == prior.model_dump(mode="json"):
        return _assessment_no_update_review(normalized, counterparty_id, private_notes)
    return {
        "counterparty_id": counterparty_id,
        "evidence_ids": normalized.get("evidence_ids", []),
        "prior": prior.model_dump(mode="json"),
        "updated": updated_values,
        "reason": normalized.get("reason") or private_notes or "Dimension-specific assessment update.",
    }


def _is_generated_assessment_review(update: dict[str, Any] | None) -> bool:
    return isinstance(update, dict) and "__assessment_review__" in update


def _assessment_no_update_review(
    normalized: dict[str, Any],
    counterparty_id: str,
    private_notes: str,
) -> dict[str, Any]:
    return {
        "__assessment_review__": {
            "evidence_ids": normalized.get("evidence_ids", []),
            "counterparty_ids": [counterparty_id],
            "review_result": "no_update",
            "reason": (
                normalized.get("reason")
                or private_notes
                or "Submitted assessment scores match the current prior."
            ),
        }
    }


def _merge_assessment_updates(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, tuple[str, ...], str], dict[str, Any]] = {}
    passthrough = []
    for update in updates:
        if not all(key in update for key in ["counterparty_id", "evidence_ids", "prior", "updated"]):
            passthrough.append(update)
            continue
        key = (
            update["counterparty_id"],
            tuple(update["evidence_ids"]),
            json.dumps(update["prior"], sort_keys=True),
        )
        if key not in merged:
            merged[key] = dict(update)
            continue
        combined = merged[key]
        prior = combined["prior"]
        for dimension, value in update["updated"].items():
            if value != prior.get(dimension):
                combined["updated"][dimension] = value
        combined["reason"] = f"{combined.get('reason', '')} {update.get('reason', '')}".strip()
    return list(merged.values()) + passthrough


def _has_flat_trust_scores(update: dict[str, Any]) -> bool:
    return all(
        key in update
        for key in [
            "performance_reliability",
            "information_reliability",
            "contractual_reliability",
        ]
    )


def _assessment_dimension_alias(value: str) -> str | None:
    normalized = value.strip().lower()
    aliases = {
        "performance_reliability": "performance_reliability",
        "delivery_reliability": "performance_reliability",
        "delivery_performance": "performance_reliability",
        "information_reliability": "information_reliability",
        "reporting_integrity": "information_reliability",
        "claim_accuracy": "information_reliability",
        "contractual_reliability": "contractual_reliability",
        "contract_process_reliability": "contractual_reliability",
    }
    return aliases.get(normalized)


def _normalize_communication(communication: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(communication)
    if "type" in normalized and "communication_type" not in normalized:
        normalized["communication_type"] = normalized.pop("type")
    communication_type = normalized.get("communication_type")
    type_aliases = {
        "private": "private_message",
        "direct": "private_message",
        "direct_message": "private_message",
        "public": "public_message",
        "broadcast": "public_message",
    }
    if isinstance(communication_type, str):
        normalized["communication_type"] = type_aliases.get(communication_type, communication_type)
    if "recipients" in normalized and "recipient_ids" not in normalized:
        normalized["recipient_ids"] = normalized.pop("recipients")
    if "recipient_agent_ids" in normalized and "recipient_ids" not in normalized:
        normalized["recipient_ids"] = normalized.pop("recipient_agent_ids")
    if "recipient_id" in normalized and "recipient_ids" not in normalized:
        normalized["recipient_ids"] = [normalized.pop("recipient_id")]
    if "message" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.pop("message")
    if "message_body" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.pop("message_body")
    if "body" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.pop("body")
    if "content" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.pop("content")
    if "text" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.pop("text")
    if normalized.get("communication_type") == "public_message":
        normalized["recipient_ids"] = []
    allowed = {
        "communication_type",
        "recipient_ids",
        "summary",
        "claims",
        "required_proposition_ids",
        "withheld_proposition_ids",
        "decision_record_id",
    }
    return {key: value for key, value in normalized.items() if key in allowed}


def _normalize_gemma_submission(
    parsed: Any,
    *,
    observation: AgentObservation | None = None,
) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return parsed
    normalized = dict(parsed)
    decisions_by_node = normalized.pop("decisions_by_node", None)
    parameters_by_node = normalized.pop("parameters_by_node", {}) or {}
    if decisions_by_node is not None and "decisions" not in normalized:
        decisions = []
        if isinstance(decisions_by_node, dict):
            parameter_node_ids = set(parameters_by_node) if isinstance(parameters_by_node, dict) else set()
            for node_id in sorted(set(decisions_by_node) | parameter_node_ids):
                value = decisions_by_node.get(
                    node_id,
                    "__parameters__" if node_id in parameter_node_ids else None,
                )
                option_id: str | None
                parameters = parameters_by_node.get(node_id, {}) if isinstance(parameters_by_node, dict) else {}
                if isinstance(value, dict):
                    if "option_id" in value or "parameters" in value:
                        option_id = value.get("option_id")
                        parameters = value.get("parameters", parameters)
                    else:
                        option_id = None
                        parameters = value
                else:
                    option_id = value
                if option_id in {"__parameters__", "parameters", "parameterized", "null"}:
                    option_id = None
                decisions.append(
                    {
                        "node_id": node_id,
                        "option_id": option_id,
                        "parameters": parameters or {},
                    }
                )
        normalized["decisions"] = decisions
    if "assessment_no_updates" in normalized and "assessment_reviews" not in normalized:
        normalized["assessment_reviews"] = normalized.pop("assessment_no_updates")
    if observation is not None:
        _normalize_gemma_assessments(normalized, observation)
    allowed_top_level = {
        "decisions",
        "communications",
        "assessment_updates",
        "assessment_reviews",
        "private_notes",
    }
    return {key: value for key, value in normalized.items() if key in allowed_top_level}


def _normalize_gemma_assessments(
    normalized: dict[str, Any],
    observation: AgentObservation,
) -> None:
    private_notes = str(normalized.get("private_notes") or "")
    updates: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for item in _gemma_assessment_records(normalized.get("assessment_updates", [])):
        _append_gemma_assessment_record(
            updates,
            reviews,
            item,
            observation,
            private_notes,
            prefer_review=False,
        )
    for item in _gemma_assessment_records(normalized.get("assessment_reviews", [])):
        _append_gemma_assessment_record(
            updates,
            reviews,
            item,
            observation,
            private_notes,
            prefer_review=True,
        )
    if updates or reviews:
        normalized["assessment_updates"] = updates
        normalized["assessment_reviews"] = _dedupe_reviews(reviews)


def _gemma_assessment_records(raw_records: Any) -> list[dict[str, Any]]:
    if isinstance(raw_records, list):
        return [record for record in raw_records if isinstance(record, dict)]
    if isinstance(raw_records, dict):
        records = []
        for counterparty_id, value in raw_records.items():
            if isinstance(value, dict):
                record = dict(value)
            else:
                record = {"reason": str(value)}
            record.setdefault("counterparty_id", counterparty_id)
            records.append(record)
        return records
    return []


def _append_gemma_assessment_record(
    updates: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    item: dict[str, Any],
    observation: AgentObservation,
    private_notes: str,
    *,
    prefer_review: bool,
) -> None:
    evidence_ids = _gemma_evidence_ids(item, observation)
    if not evidence_ids:
        return
    counterparty_ids = _gemma_counterparty_ids(item, observation)
    if not counterparty_ids:
        return
    reason = str(item.get("reason") or item.get("update") or private_notes or "No score change submitted.")
    for counterparty_id in counterparty_ids:
        prior_assessment = observation.trust_prior_by_counterparty.get(counterparty_id)
        if prior_assessment is None:
            continue
        prior = TrustValues(
            performance_reliability=prior_assessment.performance_reliability,
            information_reliability=prior_assessment.information_reliability,
            contractual_reliability=prior_assessment.contractual_reliability,
        )
        updated = _gemma_updated_scores(item)
        if prefer_review or updated is None or updated == prior:
            reviews.append(
                {
                    "evidence_ids": evidence_ids,
                    "counterparty_ids": [counterparty_id],
                    "review_result": "no_update",
                    "reason": reason,
                }
            )
        else:
            updates.append(
                {
                    "counterparty_id": counterparty_id,
                    "evidence_ids": evidence_ids,
                    "prior": prior.model_dump(mode="json"),
                    "updated": updated.model_dump(mode="json"),
                    "reason": reason,
                }
            )


def _gemma_evidence_ids(item: dict[str, Any], observation: AgentObservation) -> list[str]:
    available = {evidence.evidence_id for evidence in observation.assessment_evidence}
    if isinstance(item.get("evidence_ids"), list):
        return [
            str(evidence_id)
            for evidence_id in item["evidence_ids"]
            if str(evidence_id) in available
        ]
    if item.get("evidence_id"):
        evidence_id = str(item["evidence_id"])
        return [evidence_id] if evidence_id in available else []
    if len(observation.assessment_evidence) == 1:
        return [observation.assessment_evidence[0].evidence_id]
    return []


def _gemma_counterparty_ids(item: dict[str, Any], observation: AgentObservation) -> list[str]:
    if isinstance(item.get("counterparty_ids"), list):
        return [str(counterparty_id) for counterparty_id in item["counterparty_ids"]]
    if item.get("counterparty_id"):
        return [str(item["counterparty_id"])]
    if len(observation.assessment_evidence) == 1:
        possible = observation.assessment_evidence[0].possible_counterparty_ids
        return possible[:1]
    return []


def _gemma_updated_scores(item: dict[str, Any]) -> TrustValues | None:
    raw_updated = item.get("updated")
    if isinstance(raw_updated, dict):
        source = raw_updated
    else:
        source = item
    required = [
        "performance_reliability",
        "information_reliability",
        "contractual_reliability",
    ]
    if not all(key in source for key in required):
        return None
    try:
        return TrustValues(
            performance_reliability=float(source["performance_reliability"]),
            information_reliability=float(source["information_reliability"]),
            contractual_reliability=float(source["contractual_reliability"]),
        )
    except (TypeError, ValueError):
        return None


def _dedupe_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    deduped = []
    for review in reviews:
        key = (tuple(review["evidence_ids"]), tuple(review["counterparty_ids"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(review)
    return deduped


def _extract_json(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    if stripped.startswith("{"):
        return stripped
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError("model response did not contain JSON object")
    return match.group(0)


def make_ollama_policies(model: str = DEFAULT_OLLAMA_MODEL) -> dict[str, AgentPolicy]:
    assert_ollama_model_available(model)
    adapter = OllamaModelAdapter(model, json_format=False)
    return {
        agent_id: LLMPolicy(adapter, agent_id, prompt_style="gemma_compact")
        for agent_id in [
            "owner",
            "gc",
            "steel_supplier",
            "labor_subcontractor",
            "lender",
            "inspector",
        ]
    }


def make_anthropic_policies(model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL) -> dict[str, AgentPolicy]:
    adapter = AnthropicModelAdapter(model=model)
    return {
        agent_id: LLMPolicy(adapter, agent_id, prompt_style="anthropic_structured")
        for agent_id in [
            "owner",
            "gc",
            "steel_supplier",
            "labor_subcontractor",
            "lender",
            "inspector",
        ]
    }
