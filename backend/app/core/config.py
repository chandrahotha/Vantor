"""Central configuration — single source of truth, env-driven, fail-closed.

All secrets come from environment (see .env.example). No defaults for
production secrets are accepted: app refuses to start in prod without them.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_url: str = Field(default="http://localhost:3000", alias="APP_URL")
    api_url: str = Field(default="http://localhost:8000", alias="API_URL")
    log_level: str = Field(default="info", alias="LOG_LEVEL")

    database_url: str = Field(default="postgresql://vantor:change-me-in-env@postgres:5432/vantor", alias="DATABASE_URL")

    @property
    def database_url_resolved(self) -> str:
        """DATABASE_URL with the driver pinned.

        SQLAlchemy's default for a bare `postgresql://` URL is psycopg2, which
        is not in `requirements.txt`. We ship psycopg3. Prescribe it here so the
        app, Alembic, and any script reading the URL all use the same driver.
        """
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    # OIDC / Keycloak — required in prod/staging, optional for unit tests only.
    keycloak_url: str = Field(default="http://keycloak:8080", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="vantor", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="vantor-web", alias="KEYCLOAK_CLIENT_ID")
    oidc_issuer: str = Field(default="http://keycloak:8080/realms/vantor", alias="OIDC_ISSUER")
    jwt_audience: str = Field(default="vantor-web", alias="JWT_AUDIENCE")

    # AI gateway — free-first; all optional, `disabled` is the deterministic mode.
    # `ai_provider` picks the default; every provider is also selectable per
    # request, and every provider accepts a per-request BYOK key. A provider is
    # "configured" when it has a base URL and a model (see ai_gateway).
    ai_provider: str = Field(default="ollama", alias="AI_PROVIDER")
    ai_default_model: str = Field(default="", alias="AI_DEFAULT_MODEL")  # empty = the provider's own default
    # empty = VANTOR_VOICE in ai_gateway. Set it to pin a house style.
    ai_system_prompt: str = Field(default="", alias="AI_SYSTEM_PROMPT")

    # Self-hosted.
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    opencode_base_url: str = Field(default="", alias="OPENCODE_BASE_URL")
    opencode_model: str = Field(default="", alias="OPENCODE_MODEL")
    opencode_api_key: str = Field(default="", alias="OPENCODE_API_KEY")

    # Free online endpoints (BYO free key; nothing is stored server side).
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="meta-llama/llama-3.3-70b-instruct:free", alias="OPENROUTER_MODEL")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    opencode_zen_base_url: str = Field(default="https://opencode.ai/zen/v1", alias="OPENCODE_ZEN_BASE_URL")
    opencode_zen_model: str = Field(default="gpt-5-nano", alias="OPENCODE_ZEN_MODEL")
    opencode_zen_api_key: str = Field(default="", alias="OPENCODE_ZEN_API_KEY")
    omnirouter_base_url: str = Field(default="", alias="OMNIROUTER_BASE_URL")
    omnirouter_model: str = Field(default="", alias="OMNIROUTER_MODEL")
    omnirouter_api_key: str = Field(default="", alias="OMNIROUTER_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="", alias="NVIDIA_MODEL")
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")

    # Paid BYOK — same contract, you bring a paid key if you want these voices.
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_base_url: str = Field(default="https://api.anthropic.com", alias="ANTHROPIC_BASE_URL")
    anthropic_model: str = Field(default="claude-haiku-4-5", alias="ANTHROPIC_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta", alias="GEMINI_BASE_URL")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    @field_validator("app_env")
    @classmethod
    def _env_known(cls, v: str) -> str:
        allowed = {"development", "test", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}")
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"

    @property
    def jwks_url(self) -> str:
        return f"{self.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"

    def require_prod_secrets(self) -> None:
        """Fail-closed: production must not run on placeholder secrets."""
        if not self.is_prod:
            return
        placeholders = ("change-me", "generate-32-bytes-min", "")
        for name in ("DATABASE_URL", "OIDC_ISSUER", "JWT_AUDIENCE", "POSTGRES_PASSWORD",
                     "JWT_SECRET", "REFRESH_TOKEN_SECRET", "ENCRYPTION_KEY",
                     "KEYCLOAK_CLIENT_SECRET", "S3_SECRET_KEY"):
            val = os.getenv(name, "")
            if any(p in val for p in placeholders):
                raise RuntimeError(f"Refusing production start: {name} is missing or placeholder")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.require_prod_secrets()
    return s
