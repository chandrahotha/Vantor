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
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    # OIDC / Keycloak — required in prod/staging, optional for unit tests only.
    keycloak_url: str = Field(default="http://keycloak:8080", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="vantor", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="vantor-web", alias="KEYCLOAK_CLIENT_ID")
    oidc_issuer: str = Field(default="http://keycloak:8080/realms/vantor", alias="OIDC_ISSUER")
    jwt_audience: str = Field(default="vantor-web", alias="JWT_AUDIENCE")

    # AI gateway — free-first; all optional, `disabled` deterministic mode.
    ai_provider: str = Field(default="ollama", alias="AI_PROVIDER")
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    opencode_base_url: str = Field(default="", alias="OPENCODE_BASE_URL")
    opencode_model: str = Field(default="", alias="OPENCODE_MODEL")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="", alias="NVIDIA_MODEL")

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
