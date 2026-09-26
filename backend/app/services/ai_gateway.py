"""AI gateway — free-first, evidence-first, never silent.

Providers (ADR-003): ollama (local default) + opencode + nvidia as first-class,
openrouter-free / groq-free / huggingface as BYO-key fallbacks, disabled mode.
CostPilot NEG-004 pattern: real HTTP, explicit errors naming the provider,
no-silent-fallback (we never swap providers mid-request), quarantine-before-approve
(nothing the model says is ever marked validated — human confirms).

Every result carries the evidence contract: answer + confidence + evidence[] +
data_timestamp + requires_human_review. Confidence is heuristic and always < 1
unless the answer is a deterministic echo (disabled mode => 0.0 + UNKNOWN).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

TIMEOUT_S = 30.0


class AIGatewayError(RuntimeError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def providers_configured() -> list[str]:
    """Providers actually callable right now (env-probed, not hardcoded)."""
    from ..core.config import get_settings

    s = get_settings()
    out = ["ollama", "disabled"]
    if s.opencode_base_url and s.opencode_model:
        out.insert(1, "opencode")
    if s.nvidia_model:
        out.insert(2, "nvidia")
    return out


def _openai_chat(base_url: str, api_key: str, model: str, prompt: str, system: str) -> str:
    try:
        r = httpx.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        return str(r.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise AIGatewayError("openai-compatible", f"chat call failed: {type(exc).__name__}: {exc}") from exc


def complete(*, prompt: str, system: str = "", provider: str = "") -> dict:
    """Run one completion through the named (or configured) provider.

    Returns the evidence envelope. Raises AIGatewayError naming the provider on
    any failure — the caller (and UI) must surface it, never silently retry
    another provider.
    """
    _ = system  # noqa: F841 — reserved shape documented above
    from ..core.config import get_settings

    s = get_settings()
    name = (provider or s.ai_provider or "ollama").strip().lower()
    if name == "disabled":
        return {"answer": "UNKNOWN — AI provider is disabled in this environment.",
                "confidence": 0.0, "evidence": [], "data_timestamp": _utcnow_iso(),
                "requires_human_review": True, "provider": "disabled"}
    if name == "ollama":
        try:
            r = httpx.post(s.ollama_base_url.rstrip("/") + "/api/generate",
                           json={"model": s.ollama_model, "prompt": (system + "\n\n" + prompt) if system else prompt, "stream": False},
                           timeout=TIMEOUT_S)
            r.raise_for_status()
            text = str(r.json().get("response", ""))
        except httpx.HTTPError as exc:
            raise AIGatewayError("ollama", f"generate failed: {exc}") from exc
        if not text.strip():
            raise AIGatewayError("ollama", "empty response — refusing to present nothing as analysis")
        return {"answer": text, "confidence": 0.55, "evidence": [], "data_timestamp": _utcnow_iso(),
                "requires_human_review": True, "provider": "ollama"}
    if name == "opencode":
        if not s.opencode_base_url or not s.opencode_model:
            raise AIGatewayError("opencode", "OPENCODE_BASE_URL/OPENCODE_MODEL not configured")
        try:
            text = _openai_chat(s.opencode_base_url, _env("OPENCODE_API_KEY"), s.opencode_model, prompt, system or "You are a procurement analyst. Cite evidence; say UNKNOWN when unsure.")
        except AIGatewayError as exc:
            raise AIGatewayError("opencode", exc.message) from exc
        return {"answer": text, "confidence": 0.55, "evidence": [], "data_timestamp": _utcnow_iso(),
                "requires_human_review": True, "provider": "opencode"}
    if name == "nvidia":
        if not s.nvidia_model:
            raise AIGatewayError("nvidia", "NVIDIA_MODEL not configured (BYO key via NVIDIA_API_KEY)")
        try:
            text = _openai_chat(s.nvidia_base_url, _env("NVIDIA_API_KEY"), s.nvidia_model, prompt, system or "You are a procurement analyst. Cite evidence; say UNKNOWN when unsure.")
        except AIGatewayError as exc:
            raise AIGatewayError("nvidia", exc.message) from exc
        return {"answer": text, "confidence": 0.55, "evidence": [], "data_timestamp": _utcnow_iso(),
                "requires_human_review": True, "provider": "nvidia"}
    if name in {"openrouter-free", "groq-free", "huggingface"}:
        raise AIGatewayError(name, "fallback provider call not wired in this wave — configure primary (ollama|opencode|nvidia) or use disabled")
    raise AIGatewayError(name or "unknown", f"Unknown AI_PROVIDER {name!r} (ollama|opencode|nvidia|disabled)")


# ---------------------------------------------------------------------------
# Real streaming. Yields (delta_text) frames from the provider as they arrive;
# raises AIGatewayError on transport failure. `stream=False` browsers/platforms
# fall through to `complete()`.
# ---------------------------------------------------------------------------

def stream(*, prompt: str, system: str = "", provider: str = "") -> "Iterator[str]":  # noqa: F821
    from ..core.config import get_settings

    s = get_settings()
    name = (provider or s.ai_provider or "ollama").strip().lower()
    if name == "disabled":
        yield "UNKNOWN — AI provider is disabled in this environment."
        return
    if name == "ollama":
        # Ollama streams newline-delimited JSON: {"response": "..."}.
        try:
            with httpx.stream("POST", s.ollama_base_url.rstrip("/") + "/api/generate",
                              json={"model": s.ollama_model, "prompt": (system + "\n\n" + prompt) if system else prompt, "stream": True},
                              timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = httpx.Response(200, text=line).json()
                    except Exception:
                        continue
                    piece = chunk.get("response")
                    if piece:
                        yield str(piece)
                    if chunk.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise AIGatewayError("ollama", f"stream failed: {exc}") from exc
        return
    if name == "opencode":
        if not s.opencode_base_url or not s.opencode_model:
            raise AIGatewayError("opencode", "OPENCODE_BASE_URL/OPENCODE_MODEL not configured")
        yield from _openai_stream(s.opencode_base_url, _env("OPENCODE_API_KEY"), s.opencode_model, prompt, system, "opencode")
        return
    if name == "nvidia":
        if not s.nvidia_model:
            raise AIGatewayError("nvidia", "NVIDIA_MODEL not configured (BYO key via NVIDIA_API_KEY)")
        yield from _openai_stream(s.nvidia_base_url, _env("NVIDIA_API_KEY"), s.nvidia_model, prompt, system, "nvidia")
        return
    if name in {"openrouter-free", "groq-free", "huggingface"}:
        raise AIGatewayError(name, "fallback provider not wired — use a primary or disabled")
    raise AIGatewayError(name or "unknown", f"Unknown AI_PROVIDER {name!r} (ollama|opencode|nvidia|disabled)")


def _openai_stream(base_url: str, api_key: str, model: str, prompt: str, system: str, provider_name: str) -> "Iterator[str]":  # noqa: F821
    try:
        with httpx.stream("POST", base_url.rstrip("/") + "/chat/completions",
                          headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                          json={"model": model, "stream": True, "messages": [
                              {"role": "system", "content": system or "You are a procurement analyst. Cite evidence; say UNKNOWN when unsure."},
                              {"role": "user", "content": prompt}], "temperature": 0.2},
                          timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    return
                try:
                    obj = httpx.Response(200, text=payload).json()
                except Exception:
                    continue
                for choice in obj.get("choices", []):
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        yield str(piece)
    except httpx.HTTPError as exc:
        raise AIGatewayError(provider_name, f"stream failed: {exc}") from exc
