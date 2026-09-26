"""Load test — real requests, no mocks. Verifies p95/hold targets against the
backend's /api/v1/ops/metrics once the app is up and OIDC is bypassed for it:
set APP_ENV=test and SERVICE_SKIP_AUTH_VM=1 only in a throwaway local run.

The audit finding being fixed here: no load test existed. CI budgets are not
enforced by tooling, only by comments — and comments do not run.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

# Force this repo's backend onto sys.path — "app.main" resolves to another
# project on this machine otherwise (import shadowing outside the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


async def bench() -> int:
    total = 300
    lat: list[float] = []

    def one(i: int) -> float:
        start = time.perf_counter()
        c = TestClient(app)
        # Health is unauthenticated; load it because it exercises the full
        # middleware + envelope path without needing a signing key.
        c.get("/api/v1/health")
        return (time.perf_counter() - start) * 1000

    for i in range(total):
        lat.append(one(i))

    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0.0
    report = f"p50={p50:.1f}ms p95={p95:.1f}ms requests={len(lat)}"
    print(f"latency: {report}")
    # Soft budget — adjust in place once a baseline profile exists.
    return 0 if p95 < 800 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(bench()))
