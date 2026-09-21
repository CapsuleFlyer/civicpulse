"""Hosted LLM triage over an OpenAI-compatible endpoint.

Groq by default (free tier, no card, OpenAI-compatible, fast enough that a
citizen watching a spinner does not give up). Any OpenAI-compatible base URL
works by changing LLM_BASE_URL — that is the whole reason this provider talks
to a URL rather than to a vendor SDK.

Transport errors are translated into the domain's error taxonomy here, because
the retry policy upstream reasons about *retryability*, not about HTTP.
"""

from __future__ import annotations

import logging

import httpx

from app.providers.triage.base import (
    TriageBadRequest,
    TriageFormatError,
    TriageRateLimited,
    TriageResult,
    TriageTimeout,
    TriageUpstreamError,
    parse_triage_payload,
)
from app.providers.triage.prompt import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger("civicpulse.triage.llm")


class LLMTriage:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        name: str = "llm:groq",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # The key is held only in memory, sourced from the environment, and is
        # never logged: no log line in this module formats `self._headers`.
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def triage(self, text: str, location: str) -> TriageResult:
        payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(text, location)},
            ],
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise TriageTimeout(f"{self.name} timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise TriageUpstreamError(f"{self.name} transport error: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise TriageRateLimited(f"{self.name} rate limited")
        if 400 <= response.status_code < 500:
            raise TriageBadRequest(f"{self.name} rejected the request with {response.status_code}")
        if response.status_code >= 500:
            raise TriageUpstreamError(f"{self.name} returned {response.status_code}")

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TriageFormatError(f"{self.name} returned an unexpected envelope") from exc
        return parse_triage_payload(content)
