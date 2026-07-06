from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Literal, Protocol

from constructbench.agents import AgentPolicy
from constructbench.state import AgentBriefing, AgentObservation, AgentSubmission, TrustValues

DEFAULT_ANTHROPIC_HAIKU_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_VERSION = "2023-06-01"
PromptStyle = Literal["anthropic_structured"]
ANTHROPIC_PRICING_USD_PER_MTOK = {
    "claude-haiku-4-5-20251001": {
        "input_tokens": 1.00,
        "output_tokens": 5.00,
        "cache_creation_input_tokens": 1.25,
        "cache_read_input_tokens": 0.10,
    },
    "claude-sonnet-5": {
        "input_tokens": 3.00,
        "output_tokens": 15.00,
        "cache_creation_input_tokens": 3.75,
        "cache_read_input_tokens": 0.30,
    },
}

# Models that reject non-default sampling parameters (temperature/top_p/top_k)
# and run adaptive thinking; the temperature field must be omitted for them.
_NO_SAMPLING_PARAM_MODEL_MARKERS = ("sonnet-5", "opus-4-7", "opus-4-8", "fable-5")


def model_rejects_sampling_params(model: str) -> bool:
    lowered = model.lower()
    return any(marker in lowered for marker in _NO_SAMPLING_PARAM_MODEL_MARKERS)


class ChatAdapter(Protocol):
    model: str

    def chat(self, messages: list[dict[str, str]]) -> str:
        ...


class AnthropicModelAdapter:
    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL,
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._last_usage: dict[str, Any] | None = None
        self.api_version = ANTHROPIC_API_VERSION
        self.model_parameters = {"temperature": temperature, "max_tokens": max_tokens}

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload_body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.model_parameters["max_tokens"],
            "system": "\n\n".join(
                message["content"] for message in messages if message["role"] == "system"
            ),
            "messages": [
                {"role": message["role"], "content": message["content"]}
                for message in messages
                if message["role"] in {"user", "assistant"}
            ],
        }
        if not model_rejects_sampling_params(self.model):
            payload_body["temperature"] = self.model_parameters["temperature"]
        payload = json.dumps(payload_body).encode()
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
        messages = self.messages + [user_message]
        raw = self.adapter.chat(messages)
        usage = None
        if hasattr(self.adapter, "drain_usage"):
            usage = self.adapter.drain_usage()  # type: ignore[attr-defined]
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
    return (
        "You are a persistent business organization in ConstructSim. "
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
    return _observation_prompt(observation, include_role=include_role)


def _repair_prompt_for_style(
    observation: AgentObservation,
    errors: list[str],
    *,
    include_role: bool,
    prompt_style: PromptStyle,
) -> dict[str, Any]:
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


def make_anthropic_policies(
    model: str = DEFAULT_ANTHROPIC_HAIKU_MODEL,
    *,
    temperature: float = 0.0,
) -> dict[str, AgentPolicy]:
    adapter = AnthropicModelAdapter(model=model, temperature=temperature)
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
