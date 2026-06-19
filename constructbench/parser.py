"""Structured model-output parsing."""

from __future__ import annotations

import json

from pydantic import ValidationError

from constructbench.models import AgentSubmission


class StructuredOutputParser:
    """Parse raw JSON text into an AgentSubmission."""

    def __init__(self) -> None:
        self.last_error = ""

    def parse(self, raw_output: str) -> AgentSubmission | None:
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            self.last_error = f"invalid_json: {exc.msg}"
            return None

        try:
            return AgentSubmission.model_validate(payload)
        except ValidationError as exc:
            self.last_error = f"schema_validation_failed: {exc.errors()}"
            return None

