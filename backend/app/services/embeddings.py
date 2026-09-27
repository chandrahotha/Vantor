"""Chunk embeddings and retrieval.

Providers:
- `disabled` (default) — writes no vectors; `/documents/search` falls back to
  keyword matching and says so. Never fakes semantic behaviour.
- `ollama` — real vectors from the local Ollama instance
  (`OLLAMA_EMBEDDING_MODEL`, default `nomic-embed-text`).
- `toy` — deterministic character-n-gram hashing into 384 dims, no network.
  Real cosine geometry on real stored vectors, but **not semantic**. Marked
  `mode: toy-rank` in search output so nobody mistakes it for meaning.

Storage is a JSON list in `DocumentChunk.embedding`, so the same schema works on
SQLite (tests) and Postgres. Chunks carry vectors only once they are computed —
scanned/failed docs keep an empty mapping and are excluded from ranking, not
given zero vectors and ranked as if they matched.
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Sequence

from ..models.vectortype import embedding_dims

# The vector width, from the one place that defines it. This used to be a literal
# here and a different literal in the column declaration, so the two could
# disagree - and a `vector(N)` column rejects a vector of any other width, from a
# background job, with no context. One source of truth.
DIMS = embedding_dims()


class EmbeddingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "disabled").strip().lower()


def _toy(text: str) -> list[float]:
    vec = [0.0] * DIMS
    words = text.lower().split()
    if not words:
        return vec
    for w in words:
        bucket = int.from_bytes(hashlib.sha256(w.encode()).digest()[:4], "big") % DIMS
        vec[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float] | None:
    """Return a vector, or None when the configured provider is disabled.

    A None return is a designed outcome (`mode: keyword`), never a silent 500.
    Provider failures raise EmbeddingError so the caller can choose to proceed
    with keyword-only rather than store nothing and lie about it later.
    """
    p = provider()
    if p == "disabled":
        return None
    if p == "toy":
        return _toy(text)
    if p == "ollama":
        import httpx

        base = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
        model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        try:
            with httpx.Client(timeout=30.0) as c:
                r = c.post(f"{base}/api/embeddings", json={"model": model, "input": text[:8000]})
                r.raise_for_status()
                body = r.json()
        except Exception as exc:
            raise EmbeddingError("EMBEDDING_PROVIDER_FAILED", f"ollama embeddings failed: {exc}") from exc
        vec = (body.get("embeddings") or [None])[0]
        if not isinstance(vec, list) or len(vec) != DIMS:
            raise EmbeddingError("EMBEDDING_SHAPE", f"ollama returned {0 if vec is None else len(vec)} dims, expected {DIMS}")
        return [float(v) for v in vec]
    raise EmbeddingError("EMBEDDING_PROVIDER_UNKNOWN", f"unknown EMBEDDING_PROVIDER {p!r}")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


def rank(query: str, candidates: list[dict]) -> tuple[list[dict], str]:
    """Re-order ILIKE-filtered candidates by cosine over stored vectors.

    Candidates without a vector keep their keyword order — they are not
    assigned 0.0 and penalised for lacking a vector. Returns `(rows, mode)`
    where mode tells the caller which ranking actually ran: `keyword`,
    `toy-rank` or `semantic`.
    """
    qv = embed(query)
    if qv is None:
        return candidates, "keyword"
    mode = "toy-rank" if provider() == "toy" else "semantic"

    def key(item: dict) -> float:
        emb = item.get("embedding")
        return cosine(qv, emb) if isinstance(emb, list) and emb else -1.0

    ranked = sorted(candidates, key=lambda c: (key(c), -c.get("chunk_no", 0)), reverse=True)
    have_vectors = any(isinstance(c.get("embedding"), list) and c["embedding"] for c in candidates)
    return (ranked, mode) if have_vectors else (candidates, "keyword")
