"""Provider selection — the only place that knows which implementations exist.

Adding a fine-tuned classifier next year means adding a module and one branch
here. Nothing in routes/, services/ or repositories/ changes, which is the
entire point of the interface.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.providers.triage.base import TriageProvider
from app.providers.triage.llm import LLMTriage
from app.providers.triage.ollama import OllamaTriage
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage.simulated import SimulatedTriage

logger = logging.getLogger("civicpulse.triage.factory")

KNOWN_PROVIDERS = ("llm", "ollama", "rules", "simulated")


def build_triage_provider(settings: Settings) -> TriageProvider:
    choice = settings.triage_provider.strip().lower()

    if choice == "llm":
        if not settings.llm_api_key:
            # Refusing to start would be worse: the fallback is a designed,
            # tested path, and a municipality with no key should still triage.
            logger.warning(
                "triage_provider_downgraded",
                extra={"requested": "llm", "reason": "LLM_API_KEY is not set", "using": "rules"},
            )
            return RuleBasedTriage()
        return LLMTriage(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_seconds=settings.triage_timeout_seconds,
            name=settings.llm_provider_label,
        )

    if choice == "ollama":
        return OllamaTriage(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.triage_timeout_seconds,
        )

    if choice == "simulated":
        return SimulatedTriage(
            seed=settings.simulated_seed,
            failure_mode=settings.simulated_failure_mode,
            latency_ms=settings.simulated_latency_ms,
        )

    if choice != "rules":
        logger.warning(
            "triage_provider_unknown",
            extra={"requested": choice, "known": list(KNOWN_PROVIDERS), "using": "rules"},
        )
    return RuleBasedTriage()
