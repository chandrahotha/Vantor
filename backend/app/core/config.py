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

    # The defaults are the *host* names, because the default case is running the
    # API on the developer machine. Compose overrides all three per service
    # (see docker-compose.yml), because inside that network the right answers are
    # `postgres`, `redis` and `keycloak`.
    #
    # These used to default to the Compose service names, which is the same
    # inversion: a native `uvicorn app.main:app` picked them up, failed to
    # resolve `keycloak` or `postgres`, and answered `503 Identity provider
    # unavailable` on every authenticated request while `/health` — which touches
    # no dependency — stayed green. A default should work when nothing is set.
    database_url: str = Field(default="postgresql://vantor:vagrant@127.0.0.1:5432/vantor", alias="DATABASE_URL")

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
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")

    # Document ingestion and storage — VNT-009/010/012.
    max_upload_mb: int = Field(default=50, alias="MAX_UPLOAD_MB", ge=1, le=1024)
    allowed_upload_ext: str = Field(
        default="pdf,docx,xlsx,csv,txt,md,png,jpg,jpeg,tiff",
        alias="ALLOWED_UPLOAD_EXT")
    upload_dir: str = Field(default="uploads", alias="UPLOAD_DIR")
    # Object storage. When S3_ENDPOINT and S3_BUCKET are both set they are used;
    # otherwise the filesystem driver is selected, which `get_storage()` refuses
    # in production rather than writing into a container layer.
    s3_endpoint: str = Field(default="", alias="S3_ENDPOINT")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_access_key: str = Field(default="", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_prefix: str = Field(default="", alias="S3_PREFIX")
    # Explicit opt-in for local-disk storage in production (see get_storage()).
    # Empty means "decide automatically": S3 if configured, otherwise refuse in
    # production. A deployment with no object storage and no second node — the
    # single-container image — sets this to accept the single-node limit
    # instead of losing uploads to a refusal with no documented way out.
    storage_driver: str = Field(default="", alias="STORAGE_DRIVER")

    # Archive-bomb limits — VNT-011. A 50 MB upload that decompresses to 50 GB is
    # a one-request denial of service, so the parse is bounded independently of
    # the upload size.
    max_archive_entries: int = Field(default=10_000, alias="MAX_ARCHIVE_ENTRIES", ge=1)
    max_archive_bytes: int = Field(
        default=200 * 1024 * 1024, alias="MAX_ARCHIVE_BYTES", ge=1024)
    max_entry_bytes: int = Field(
        default=32 * 1024 * 1024, alias="MAX_ENTRY_BYTES", ge=1024)
    max_compression_ratio: int = Field(
        default=200, alias="MAX_COMPRESSION_RATIO", ge=1)

    # Rate limiting — VNT-032. These were read straight from `os.environ` at
    # import time, which meant they could not be overridden by a test, were not
    # visible in the settings dump used by /ready, and could not be changed
    # without a restart of the module graph. As fields they are validated,
    # discoverable, and cache-clearable.
    rate_limit_write_per_min: int = Field(default=120, alias="RATE_LIMIT_WRITE_PER_MIN", ge=1)
    rate_limit_read_per_min: int = Field(default=600, alias="RATE_LIMIT_READ_PER_MIN", ge=1)
    # AI and upload are priced separately: a completion costs a provider call and
    # an upload costs disk plus (later) a parse. Sharing the write budget with a
    # catalogue edit means a chatty copilot can lock a buyer out of their data.
    rate_limit_ai_per_min: int = Field(default=30, alias="RATE_LIMIT_AI_PER_MIN", ge=1)
    rate_limit_upload_per_min: int = Field(default=20, alias="RATE_LIMIT_UPLOAD_PER_MIN", ge=1)

    # OIDC / Keycloak — required in prod/staging, optional for unit tests only.
    keycloak_url: str = Field(default="http://keycloak:8080", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="vantor", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="vantor-web", alias="KEYCLOAK_CLIENT_ID")
    # `127.0.0.1`, not `keycloak`. See the note on `database_url`: the default is
    # the host-network case, and compose sets the container name explicitly.
    # The issuer must be byte-identical to the `iss` claim Keycloak puts in the
    # token, and `jwt.decode(issuer=...)` compares it exactly. The realm's issuer
    # comes from KC_HOSTNAME, which docker-compose pins to `http://localhost:8080`
    # (KC_HOSTNAME_STRICT is false so host-reachable and in-network callers can
    # both work), so the token says `localhost` — not `127.0.0.1`, which is the
    # same server and a *different* string. Defaulting to `127.0.0.1` made every
    # real token fail `Invalid token` with 401 while `/health` stayed green, which
    # is the same class of quiet total failure the Compose-service default caused.
    # `tests/test_config.py::test_default_oidc_issuer_matches_env_example` pins this
    # to .env.example so the two cannot drift.
    oidc_issuer: str = Field(default="http://localhost:8080/realms/vantor", alias="OIDC_ISSUER")
    jwt_audience: str = Field(default="vantor-web", alias="JWT_AUDIENCE")

    # ---- Local (passwordless) sign-in ------------------------------------
    # `local` makes the API its own identity provider: it holds an RSA keypair,
    # mints its own RS256 tokens, and verifies them on the same code path a
    # Keycloak token takes. Nothing downstream changes — tenancy, roles, the
    # audit actor and RLS all read the same claims.
    #
    # This exists because requiring Keycloak meant requiring a second Java
    # service before the product would open at all: with it down, clicking
    # "Sign in" navigated to `localhost:8080` and the browser showed a
    # connection error, which is not a sign-in screen.
    #
    # It is deliberately passwordless. `POST /auth/session` issues a session to
    # whoever asks, so *anyone who can reach the API is the local operator*.
    # That is the documented trade for a single-container deployment with no
    # identity service; it is not a bug and it is not an accident. Set
    # `AUTH_MODE=oidc` to require a real IdP again — the verification path is
    # unchanged and both modes can be enabled at once.
    auth_mode: str = Field(default="local", alias="AUTH_MODE")
    local_tenant: str = Field(default="vantor-corp", alias="LOCAL_TENANT")
    local_user_name: str = Field(default="Administrator", alias="LOCAL_USER_NAME")
    local_user_email: str = Field(default="operator@vantor.local", alias="LOCAL_USER_EMAIL")
    local_roles: str = Field(
        default="Super Admin,Organization Admin,Procurement Admin,Procurement Manager,Buyer,Approver,Compliance Reviewer",
        alias="LOCAL_ROLES",
    )
    local_session_hours: int = Field(default=12, alias="LOCAL_SESSION_HOURS", ge=1, le=720)
    # Where the signing key is persisted. It is generated on first use. If the
    # file is lost every existing session is invalidated, which is the correct
    # behaviour — a token signed by a key the server no longer has is not a
    # session the server can vouch for.
    local_key_path: str = Field(default="data/session-signing-key.pem", alias="LOCAL_KEY_PATH")

    # AI gateway — free-first; all optional, `disabled` is the deterministic mode.
    # `ai_provider` picks the default; every provider is also selectable per
    # request, and every provider accepts a per-request BYOK key. A provider is
    # "configured" when it has a base URL and a model (see ai_gateway).
    ai_provider: str = Field(default="ollama", alias="AI_PROVIDER")
    ai_default_model: str = Field(default="", alias="AI_DEFAULT_MODEL")  # empty = the provider's own default
    # empty = VANTOR_VOICE in ai_gateway. Set it to pin a house style.
    ai_system_prompt: str = Field(default="", alias="AI_SYSTEM_PROMPT")

    # Contract expiry is a business judgement made in the buyer's working day, not
    # the server's (VNT-041). IANA zone name; an unknown value falls back to UTC and
    # the roll reports the zone it actually used.
    contract_timezone: str = Field(default="UTC", alias="CONTRACT_TIMEZONE")

    # B-20. What happens when a purchase order is approved against a category that
    # has no budget row for the period. `allow` is the historical reading of
    # "no ceiling set" — the approval proceeds. `block` turns the missing row into
    # a 422, which is the reading an operator who expects "no uncontrolled spend"
    # has. It is a field rather than a string compared at the call site so a
    # misconfiguration is refused here, at startup, instead of silently behaving
    # as whichever of the two the comparison happened to pick.
    budget_unset_policy: str = Field(default="allow", alias="BUDGET_UNSET_POLICY")

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

    @field_validator("budget_unset_policy")
    @classmethod
    def _budget_policy_known(cls, v: str) -> str:
        allowed = {"allow", "block"}
        if v not in allowed:
            raise ValueError(f"BUDGET_UNSET_POLICY must be one of {sorted(allowed)}")
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"

    @property
    def jwks_url(self) -> str:
        return f"{self.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"

    def require_prod_secrets(self) -> None:
        """Fail-closed: production must not run on placeholder secrets.

        The required set is deployment-mode aware rather than a fixed list,
        because a fixed list is either wrong for `AUTH_MODE=local` (which has
        no Keycloak and no Postgres to speak of) or silently stops checking
        anything real. Only variables this process actually reads are checked
        here — `JWT_SECRET`, `REFRESH_TOKEN_SECRET`, `ENCRYPTION_KEY` and
        `KEYCLOAK_CLIENT_SECRET` were checked here previously but are not read
        by any code in this app (the worker's credential is
        `SERVICE_CLIENT_SECRET`, checked separately where the worker starts),
        so requiring them blocked every production start without protecting
        anything.
        """
        if not self.is_prod:
            return
        placeholders = ("change-me", "generate-32-bytes-min")

        def _is_placeholder(val: str) -> bool:
            # A prior version used `any(p in val for p in placeholders + ("",))`,
            # which is `True` for every string: the empty string is a substring
            # of everything, so this refused to start in production no matter
            # what was configured. Checked for emptiness explicitly instead.
            return val == "" or any(p in val for p in placeholders)

        required = ["DATABASE_URL"]
        if self.auth_mode == "oidc":
            required += ["OIDC_ISSUER", "JWT_AUDIENCE"]
        if not self.database_url_resolved.startswith("sqlite"):
            required.append("POSTGRES_PASSWORD")
        if self.s3_endpoint or self.s3_bucket:
            required.append("S3_SECRET_KEY")

        for name in required:
            val = os.getenv(name, "")
            if _is_placeholder(val):
                raise RuntimeError(f"Refusing production start: {name} is missing or placeholder")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.require_prod_secrets()
    return s
