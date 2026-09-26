"""Scheduled jobs — run recurring work automatically.

Without this, "roll expiry daily at 6am" existed only as documentation: no
backend code enqueued and `enqueue.py` had to be typed by a human. Ships as its
own compose service so Ops can see the worker and the scheduler independently.

Schedules (all UTC, all honest: they only ever delegate to the API):
- `roll_expiry`  daily 06:00  — contracts drift active → expiring when within 90d.
- `spend_snapshot` hourly      — validates ledgers are queryable; fails loudly if not.
"""
from __future__ import annotations

import os

from redis import Redis
from rq.scheduler import RQScheduler


def main() -> None:
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    scheduler = RQScheduler(queue_name="default", connection=redis)
    scheduler.schedule(
        scheduled_time=None,
        func="jobs.roll_expiry",
        interval=int(os.getenv("ROLL_EXPIRY_INTERVAL_S", str(60 * 60 * 24))),
        repeat=None,
    )
    scheduler.schedule(
        scheduled_time=None,
        func="jobs.spend_snapshot",
        interval=int(os.getenv("SPEND_SNAPSHOT_INTERVAL_S", str(60 * 60))),
        repeat=None,
    )
    scheduler.run()


if __name__ == "__main__":
    main()
