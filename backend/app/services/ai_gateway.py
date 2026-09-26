"""AI gateway — one evidence-first envelope, many providers, BYOK everywhere.

Contract (ADR-003):
- Every answer carries `answer`, `confidence`, `evidence[]`, `data_timestamp`
  and `requires_human_review`. Nothing the model says is ever auto-approved.
- Failures raise `AIGatewayError` naming the provider. We never silently swap
  providers mid-request, and we never present a baked answer as analysis.
- `disabled` is the deterministic mode and the honesty anchor: it returns
  UNKNOWN with confidence 0.0.

Providers, all selectable per request via `provider`:
- self-hosted: `ollama`, `opencode`
- free online (BYO free key): `openrouter`, `opencode-zen`, `omnirouter`, `nvidia`
- paid BYOK: `openai`, `anthropic`, `gemini`

Keys resolve in a fixed order — per-request `provider_key` (or the
`X-Vantor-Provider-Key` header), then the server environment, then fail closed
with a message naming the env var. Keys are never persisted and never logged.
Streaming is provider-side for every vendor; the SSE endpoint relays the deltas
as they arrive.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, NamedTuple

import httpx

TIMEOUT_S = 30.0
MAX_TOKENS = 2048

VANTOR_VOICE = (
    "You are Vantor's procurement analyst. Talk like a colleague at the same desk. "
    "Short sentences. One idea per sentence. No em dashes and no dashes used as emphasis. "
    "No 'furthermore', 'moreover', 'in conclusion', 'it is important to note', or summary "
    "openers. If data is missing, say what you would check next. End with what you would do, "
    "not a recap."
)


class AIGatewayError(RuntimeError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Provider registry — one table so `complete`, `stream` and `/ai/providers`
# can never drift apart again.
# ---------------------------------------------------------------------------

#: Wire format families. Each has a `chat` and a `stream` implementation.
OPENAI_COMPATIBLE = "openai-compatible"
ANTHROPIC = "anthropic"
GEMINI = "gemini"
OLLAMA = "ollama"


class Provider(NamedTuple):
    name: str
    kind: str
    key_env: str
    #: True when the provider talks HTTP over the network and needs a key.
    needs_key: bool


PROVIDERS: dict[str, Provider] = {
    p.name: p
    for p in (
        Provider("disabled", OLLAMA, "", False),
        Provider("ollama", OLLAMA, "", False),
        Provider("opencode", OPENAI_COMPATIBLE, "OPENCODE_API_KEY", True),
        Provider("openrouter", OPENAI_COMPATIBLE, "OPENROUTER_API_KEY", True),
        Provider("opencode-zen", OPENAI_COMPATIBLE, "OPENCODE_ZEN_API_KEY", True),
        Provider("omnirouter", OPENAI_COMPATIBLE, "OMNIROUTER_API_KEY", True),
        Provider("nvidia", OPENAI_COMPATIBLE, "NVIDIA_API_KEY", True),
        Provider("openai", OPENAI_COMPATIBLE, "OPENAI_API_KEY", True),
        Provider("anthropic", ANTHROPIC, "ANTHROPIC_API_KEY", True),
        Provider("gemini", GEMINI, "GEMINI_API_KEY", True),
    )
}


def _known(name: str) -> Provider:
    p = PROVIDERS.get(name)
    if p is None:
        raise AIGatewayError(
            name or "unknown",
            f"unknown provider {name!r} — choose one of: {', '.join(sorted(PROVIDERS))}",
        )
    return p


def _env(name: str, default: str = "") -> str:
    import os

    return os.getenv(name, default).strip()


def _base_url(p: Provider, s: Any) -> str:
    return {
        "ollama": s.ollama_base_url,
        "opencode": s.opencode_base_url,
        "openrouter": s.openrouter_base_url,
        "opencode-zen": s.opencode_zen_base_url,
        "omnirouter": s.omnirouter_base_url,
        "nvidia": s.nvidia_base_url,
        "openai": s.openai_base_url,
        "anthropic": s.anthropic_base_url,
        "gemini": s.gemini_base_url,
    }.get(p.name, "")


def _default_model(p: Provider, s: Any) -> str:
    return {
        "ollama": s.ollama_model,
        "opencode": s.opencode_model,
        "openrouter": s.openrouter_model,
        "opencode-zen": s.opencode_zen_model,
        "omnirouter": s.omnirouter_model,
        "nvidia": s.nvidia_model,
        "openai": s.openai_model,
        "anthropic": s.anthropic_model,
        "gemini": s.gemini_model,
    }.get(p.name, "")


def _env_key(p: Provider, s: Any) -> str:
    """The server-side key for this provider, from settings then raw env.

    Settings first (they are the documented surface and are what
    `providers_catalog` probes), raw env as a fallback so a container that
    only exports the variable still works.
    """
    if not p.needs_key:
        return ""
    from_settings = {
        "opencode": s.opencode_api_key,
        "openrouter": s.openrouter_api_key,
        "opencode-zen": s.opencode_zen_api_key,
        "omnirouter": s.omnirouter_api_key,
        "nvidia": s.nvidia_api_key,
        "openai": s.openai_api_key,
        "anthropic": s.anthropic_api_key,
        "gemini": s.gemini_api_key,
    }.get(p.name, "")
    return (from_settings or "").strip() or _env(p.key_env)


class Target(NamedTuple):
    provider: str
    kind: str
    base_url: str
    model: str
    key: str


def resolve(provider: str, *, request_key: str = "", model: str = "") -> Target:
    """Resolve everything one request needs, or raise a named error.

    Fails closed with an actionable message rather than making a doomed HTTP
    call, so the caller and the UI get one clear sentence instead of a
    provider-specific 401 from a third party.
    """
    from ..core.config import get_settings

    s = get_settings()
    requested = (provider or "").strip().lower()
    name = requested or (s.ai_provider or "ollama").strip().lower()
    p = _known(name)
    if p.name == "disabled":
        return Target("disabled", OLLAMA, "", model or "none", "")

    base = _base_url(p, s).strip()
    if not base:
        raise AIGatewayError(p.name, f"base url is not configured (set the {p.name.upper()}_BASE_URL value)")

    key = request_key.strip() or _env_key(p, s)
    if p.needs_key and not key:
        raise AIGatewayError(
            p.name,
            f"no API key for {p.name} — set {p.key_env} in the environment, "
            "or send one per request (never stored server side)",
        )

    # Per-request model wins, then the server-wide default, then the provider's own.
    resolved_model = (model or "").strip() or s.ai_default_model.strip() or _default_model(p, s).strip()
    if not resolved_model:
        raise AIGatewayError(p.name, f"no model configured (set the model for {p.name})")
    return Target(p.name, p.kind, base, resolved_model, key)


def _system_prompt(caller: str) -> str:
    """The house voice unless the environment pins its own or the caller does."""
    from ..core.config import get_settings

    s = get_settings()
    return (caller or s.ai_system_prompt or VANTOR_VOICE).strip()


def _active_provider(provider: str) -> str:
    from ..core.config import get_settings

    return (provider or "").strip().lower() or get_settings().ai_provider.strip().lower() or "ollama"


def providers_catalog() -> list[dict]:
    """Every provider this build knows, with whether it is callable right now.

    `configured` means "the server can complete a request with this provider
    using only its own environment". `needsKey` means a caller must supply a
    BYOK key per request. Nothing here reveals a key.
    """
    from ..core.config import get_settings

    s = get_settings()
    active = _active_provider("")
    out: list[dict] = []
    for name, p in PROVIDERS.items():
        if p.name == "disabled":
            out.append({"name": name, "configured": True, "needsKey": False, "active": name == active})
            continue
        ready = bool(_base_url(p, s).strip()) and bool(_default_model(p, s).strip())
        if p.needs_key:
            ready = ready and bool(_env_key(p, s))
        out.append({"name": name, "configured": ready, "needsKey": p.needs_key, "active": name == active})
    return out


def providers_configured() -> list[str]:
    """Names of the providers callable from the environment alone."""
    return [p["name"] for p in providers_catalog() if p["configured"]]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def complete(*, prompt: str, system: str = "", provider: str = "", provider_key: str = "", model: str = "") -> dict:
    """Run one completion and return the evidence envelope.

    Raises `AIGatewayError` naming the provider on any failure — the caller
    must surface it rather than retry elsewhere.
    """
    name = _active_provider(provider)
    if name == "disabled":
        return {"answer": "UNKNOWN — AI provider is disabled in this environment.",
                "confidence": 0.0, "evidence": [], "data_timestamp": _utcnow_iso(),
                "requires_human_review": True, "provider": "disabled",
                "model": (model or "").strip() or "none"}

    t = resolve(name, request_key=provider_key, model=model)
    voice = _system_prompt(system)
    if t.kind == OLLAMA:
        text = _ollama_chat(t, prompt, voice)
    elif t.kind == ANTHROPIC:
        text = _anthropic_chat(t, prompt, voice)
    elif t.kind == GEMINI:
        text = _gemini_chat(t, prompt, voice)
    else:
        text = _openai_chat(t, prompt, voice)
    return {"answer": text, "confidence": 0.55, "evidence": [], "data_timestamp": _utcnow_iso(),
            "requires_human_review": True, "provider": t.provider, "model": t.model}


def stream(*, prompt: str, system: str = "", provider: str = "", provider_key: str = "", model: str = "") -> Iterator[str]:
    """Yield provider-side deltas as the vendor emits them.

    Any failure raises `AIGatewayError`; the SSE endpoint turns it into an
    explicit error frame. Never a baked answer.
    """
    name = _active_provider(provider)
    if name == "disabled":
        yield "UNKNOWN — this environment has no AI provider configured."
        return

    t = resolve(name, request_key=provider_key, model=model)
    voice = _system_prompt(system)
    if t.kind == OLLAMA:
        yield from _ollama_stream(t, prompt, voice)
    elif t.kind == ANTHROPIC:
        yield from _anthropic_stream(t, prompt, voice)
    elif t.kind == GEMINI:
        yield from _gemini_stream(t, prompt, voice)
    else:
        yield from _openai_stream(t, prompt, voice)


# ---------------------------------------------------------------------------
# Ollama (native /api/generate, newline-delimited JSON)
# ---------------------------------------------------------------------------


def _ollama_body(t: Target, prompt: str, voice: str) -> dict:
    return {"model": t.model, "prompt": (voice + "\n\n" + prompt) if voice else prompt, "stream": False}


def _ollama_chat(t: Target, prompt: str, voice: str) -> str:
    try:
        r = httpx.post(t.base_url.rstrip("/") + "/api/generate", json=_ollama_body(t, prompt, voice), timeout=TIMEOUT_S)
        r.raise_for_status()
        text = str(r.json().get("response", ""))
    except httpx.HTTPError as exc:
        raise AIGatewayError(t.provider, f"generate failed: {exc}") from exc
    if not text.strip():
        raise AIGatewayError(t.provider, "empty response — refusing to present nothing as analysis")
    return text


def _ollama_stream(t: Target, prompt: str, voice: str) -> Iterator[str]:
    try:
        with httpx.stream("POST", t.base_url.rstrip("/") + "/api/generate",
                          json={**_ollama_body(t, prompt, voice), "stream": True}, timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                piece = chunk.get("response")
                if piece:
                    yield str(piece)
                if chunk.get("done"):
                    return
    except httpx.HTTPError as exc:
        raise AIGatewayError(t.provider, f"stream failed: {exc}") from exc


# ---------------------------------------------------------------------------
# OpenAI-compatible (/chat/completions, SSE)
# ---------------------------------------------------------------------------


def _openai_messages(prompt: str, voice: str) -> list[dict]:
    msgs = [{"role": "system", "content": voice}] if voice else []
    return [*msgs, {"role": "user", "content": prompt}]


def _openai_chat(t: Target, prompt: str, voice: str) -> str:
    try:
        r = httpx.post(
            t.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {t.key}"},
            json={"model": t.model, "messages": _openai_messages(prompt, voice),
                  "temperature": 0.2, "max_tokens": MAX_TOKENS},
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        return str(r.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        raise AIGatewayError(t.provider, f"chat call failed: {type(exc).__name__}: {exc}") from exc


def _openai_stream(t: Target, prompt: str, voice: str) -> Iterator[str]:
    try:
        with httpx.stream(
            "POST", t.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {t.key}"},
            json={"model": t.model, "messages": _openai_messages(prompt, voice),
                  "stream": True, "temperature": 0.2, "max_tokens": MAX_TOKENS},
            timeout=None,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    return
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                for choice in obj.get("choices") or []:
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        yield str(piece)
    except httpx.HTTPError as exc:
        raise AIGatewayError(t.provider, f"stream failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Anthropic (x-api-key, typed content blocks)
# ---------------------------------------------------------------------------


def _anthropic_headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def _anthropic_chat(t: Target, prompt: str, voice: str) -> str:
    try:
        r = httpx.post(t.base_url.rstrip("/") + "/v1/messages",
                       headers=_anthropic_headers(t.key),
                       json={"model": t.model, "max_tokens": MAX_TOKENS,
                             "system": voice, "messages": [{"role": "user", "content": prompt}]},
                       timeout=TIMEOUT_S)
        r.raise_for_status()
        parts = r.json().get("content") or []
        return "".join(str(p.get("text", "")) for p in parts if p.get("type") == "text")
    except (httpx.HTTPError, TypeError, AttributeError) as exc:
        raise AIGatewayError(t.provider, f"messages call failed: {type(exc).__name__}: {exc}") from exc


def _anthropic_stream(t: Target, prompt: str, voice: str) -> Iterator[str]:
    try:
        with httpx.stream("POST", t.base_url.rstrip("/") + "/v1/messages",
                          headers=_anthropic_headers(t.key),
                          json={"model": t.model, "max_tokens": MAX_TOKENS, "stream": True,
                                "system": voice, "messages": [{"role": "user", "content": prompt}]},
                          timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if obj.get("type") == "content_block_delta":
                    piece = (obj.get("delta") or {}).get("text")
                    if piece:
                        yield str(piece)
                elif obj.get("type") == "message_stop":
                    return
    except httpx.HTTPError as exc:
        raise AIGatewayError(t.provider, f"stream failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Google Gemini (key as a query param, SSE via alt=sse)
# ---------------------------------------------------------------------------


def _gemini_body(prompt: str, voice: str) -> dict:
    return {"systemInstruction": {"parts": [{"text": voice}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}]}


def _gemini_chat(t: Target, prompt: str, voice: str) -> str:
    url = f"{t.base_url.rstrip('/')}/models/{t.model}:generateContent"
    try:
        r = httpx.post(url, params={"key": t.key}, json=_gemini_body(prompt, voice), timeout=TIMEOUT_S)
        r.raise_for_status()
        parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(str(p.get("text", "")) for p in parts)
    except (httpx.HTTPError, IndexError, TypeError, AttributeError) as exc:
        raise AIGatewayError(t.provider, f"generateContent failed: {type(exc).__name__}: {exc}") from exc


def _gemini_stream(t: Target, prompt: str, voice: str) -> Iterator[str]:
    url = f"{t.base_url.rstrip('/')}/models/{t.model}:streamGenerateContent"
    try:
        with httpx.stream("POST", url, params={"key": t.key, "alt": "sse"},
                          json=_gemini_body(prompt, voice), timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except ValueError:
                    continue
                parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                for p in parts:
                    if p.get("text"):
                        yield str(p["text"])
    except httpx.HTTPError as exc:
        raise AIGatewayError(t.provider, f"stream failed: {exc}") from exc
