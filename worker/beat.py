"""Scheduled jobs — run recurring work automatically.

Without this, "roll expiry daily at 6am" existed only as documentation: no
backend code enqueued and `enqueue.py` had to be typed by a human. Ships as its
own compose service so Ops can see the worker and the scheduler independently.

Schedules (all UTC, all honest: they only ever delegate to the API). Every
interval is configurable and every default is derived from the constant it
replaces, so tuning one does not require reading this file:
- `roll_expiry`       daily 06:00  — contracts drift active -> expiring within 90d
- `drain_webhooks`    every 30s    — the durable delivery queue (VNT-008)
- `spend_snapshot`    hourly       — validates ledgers are queryable

The webhook drain is frequent because a delivery's `next_attempt_at` is a
database column: the scheduler only has to notice that something is due, and a
once-a-minute tick would add up to a minute of latency to every webhook for no
reason.
"""
from __future__ import annotations

import os

from redis import Redis
from rq.scheduler import RQScheduler

DAY_S = 60 * 60 * 24
HOUR_S = 60 * 60

#: (job name, default interval seconds, environment variable)
SCHEDULES: tuple[tuple[str, int, str], ...] = (
    ("roll_expiry", DAY_S, "ROLL_EXPIRY_INTERVAL_S"),
    ("drain_webhooks", 30, "WEBHOOK_DRAIN_INTERVAL_S"),
    ("spend_snapshot", HOUR_S, "SPEND_SNAPSHOT_INTERVAL_S"),
)


def _interval(default: int, env_name: str) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    # A non-positive interval would make the scheduler spin. Ignore it rather
    # than turning a typo into a busy loop against the database.
    return value if value > 0 else default


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    scheduler = RQScheduler(queue_name="default", connection=redis)
    for name, default, env_name in SCHEDULES:
        scheduler.schedule(
            scheduled_time=None,
            func=f"jobs.{name}",
            interval=_interval(default, env_name),
            repeat=None,
        )
    scheduler.run()


if __name__ == "__main__":
    main()
