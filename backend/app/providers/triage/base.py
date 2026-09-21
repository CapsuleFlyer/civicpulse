"""The triage contract.

`TriageResult` is the only shape the rest of the system knows about. Whatever a
provider does internally — an HTTP call to Groq, a local Ollama container, a
keyword table — it either returns this model or raises a `TriageError`.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, ValidationError

from app.domain import Category, Priority


class TriageResult(BaseModel):
    category: Category
    priority: Priority
    summary: str = Field(max_length=140)
    confidence: float = Field(ge=0.0, le=1.0)


class TriageError(Exception):
    """Base class for every way triage can fail."""

    retryable = False


class TriageTimeout(TriageError):
    retryable = True


class TriageRateLimited(TriageError):
    retryable = True


class TriageUpstreamError(TriageError):
    """5xx from the provider."""

    retryable = True


class TriageBadRequest(TriageError):
    """4xx that is our fault. Retrying sends the same wrong request again."""

    retryable = False


class TriageFormatError(TriageError):
    """The model answered, but not with something our schema accepts."""

    retryable = False


@runtime_checkable
class TriageProvider(Protocol):
    name: str

    async def triage(self, text: str, location: str) -> TriageResult: ...


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_triage_payload(raw: str) -> TriageResult:
    """Parse *and validate* model output.

    Requesting JSON mode is a request, not a guarantee. Models return prose, a
    code fence, a category that is not in our enum, or a 400-character
    "one-line" summary. This function is the only door into the domain, and it
    never evals, never builds SQL, and never widens the enum to fit the answer.
    """
    candidate = _FENCE.sub("", raw.strip())
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise TriageFormatError("model output contained no JSON object")
    try:
        data = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise TriageFormatError(f"model output was not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise TriageFormatError("model output was not a JSON object")
    # Truncating the summary is a deliberate kindness; widening the enum would
    # not be, so category/priority are left to fail validation.
    if isinstance(data.get("summary"), str):
        data["summary"] = data["summary"].strip().replace("\n", " ")[:140]
    try:
        return TriageResult.model_validate(data)
    except ValidationError as exc:
        raise TriageFormatError(f"model output failed schema validation: {exc.error_count()} errors") from exc
