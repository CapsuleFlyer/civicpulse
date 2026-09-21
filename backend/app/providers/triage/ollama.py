"""Fully offline triage against a local Ollama container.

Same interface, different trade-off: no key, no quota, no rate limit, and no
citizen data leaving the machine — paid for in latency and accuracy on CPU.
Measuring that difference yourself is the buy-versus-host lesson.
"""

from __future__ import annotations

import httpx

from app.providers.triage.base import (
    TriageResult,
    TriageTimeout,
    TriageUpstreamError,
    parse_triage_payload,
)
from app.providers.triage.prompt import SYSTEM_PROMPT, build_user_prompt


class OllamaTriage:
    name = "llm:ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def triage(self, text: str, location: str) -> TriageResult:
        payload = {
            "model": self._model,
            "stream": False,
            # Ollama accepts a JSON schema here; we still validate the reply,
            # because "the server promised" is not a guarantee either.
            "format": TriageResult.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(text, location)},
            ],
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat", json=payload, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise TriageTimeout(f"{self.name} timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise TriageUpstreamError(f"{self.name} transport error: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            raise TriageUpstreamError(f"{self.name} returned {response.status_code}")
        body = response.json()
        return parse_triage_payload(body.get("message", {}).get("content", ""))
