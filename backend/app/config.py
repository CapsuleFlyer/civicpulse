"""Application configuration.

Every knob is an environment variable. Nothing is read from a file in the
repository, and no default here is a credential: `llm_api_key` defaults to None
so that a missing key degrades to the rule-based provider instead of leaking a
placeholder into logs.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- identity -------------------------------------------------------
    app_name: str = "civicpulse"
    environment: str = "development"
    log_level: str = "INFO"
    git_sha: str = "dev"

    # --- dependencies ---------------------------------------------------
    database_url: str = "postgresql+asyncpg://civic:civic@database:5432/civicpulse"
    redis_url: str = "redis://cache:6379/0"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # --- triage ---------------------------------------------------------
    triage_provider: str = "rules"
    triage_timeout_seconds: float = 10.0
    triage_cache_ttl_seconds: int = 86_400
    triage_max_retries: int = 1

    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.1-8b-instant"
    llm_api_key: SecretStr | None = None
    llm_provider_label: str = "llm:groq"

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:1b"

    # Deterministic fake used by CI. `simulated_failure_mode` is how the test
    # suite exercises the fallback path without a network.
    simulated_seed: int = 1337
    simulated_failure_mode: str = "none"  # none | raise | malformed | timeout
    simulated_latency_ms: int = 5

    # --- cache / rate limit ---------------------------------------------
    stats_cache_ttl_seconds: int = 30
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60

    # --- http -----------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=list)
    max_page_size: int = 100
    meta_history_size: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
