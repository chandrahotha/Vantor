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

B-34 — this file previously crashed on boot. It called `RQScheduler(queue_name=...)`
and `scheduler.schedule(...)`, neither of which exists in the pinned rq 1.16.2:
the constructor takes `queues` + `connection`, and there is no `schedule` method
at all. The compose `beat` service therefore died instantly and no recurring job
had ever run. Verified against the installed library:
    RQScheduler(queues, connection, interval=1, ...)
    RQScheduler.work() -> acquire_locks() / enqueue_scheduled_jobs() / heartbeat()
and `Queue.enqueue` has no `repeat` parameter, so a recurring schedule cannot be
declared once and forgotten — it has to be re-armed. `BeatScheduler` does that
inside the scheduler's own tick, which keeps this one process, one loop, and one
signal handler rather than a second thread with a second lifecycle.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Protocol, Sequence

from redis import Redis
from rq import Queue
from rq.registry import ScheduledJobRegistry
from rq.scheduler import RQScheduler

log = logging.getLogger("vantor.beat")

DAY_S = 60 * 60 * 24
HOUR_S = 60 * 60

#: How often the scheduler wakes up to promote due jobs and re-arm the schedule.
TICK_S = 5

#: Job execution ceiling. A run that has not finished in this long has failed,
#: and an RQ job left running forever hides the fact that it stopped working.
JOB_TIMEOUT_FLOOR_S = 60
JOB_TIMEOUT_CEILING_S = 1800

#: (job name, default interval seconds, environment variable)
SCHEDULES: tuple[tuple[str, int, str], ...] = (
    ("roll_expiry", DAY_S, "ROLL_EXPIRY_INTERVAL_S"),
    ("drain_webhooks", 30, "WEBHOOK_DRAIN_INTERVAL_S"),
    ("spend_snapshot", HOUR_S, "SPEND_SNAPSHOT_INTERVAL_S"),
)


class SupportsSchedule(Protocol):
    """The two capabilities this module needs from a queue and a registry.

    Narrow on purpose: the test suite drives this with fakes, and a wide
    `Queue`/`ScheduledJobRegistry` type would only be satisfied by real Redis.
    """

    name: str

    def get_job_ids(self, start: int = 0, end: int = -1) -> list[str]: ...

    def enqueue_at(self, datetime: datetime, f, *args, **kwargs): ...


def _interval(default: int, env_name: str) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer; using %ss", env_name, raw, default)
        return default
    # A non-positive interval would make the scheduler spin. Ignore it rather
    # than turning a typo into a busy loop against the database.
    if value <= 0:
        log.warning("%s=%r must be positive; using %ss", env_name, raw, default)
        return default
    return value


def _timeout(interval: int) -> int:
    return max(JOB_TIMEOUT_FLOOR_S, min(interval, JOB_TIMEOUT_CEILING_S))


def next_due(now: datetime, interval: int) -> datetime:
    """The next interval boundary strictly after `now`, in UTC.

    Bucketing on absolute epoch time rather than on "now + interval" is what
    makes the schedule drift-free: a scheduler that was down for an hour re-arms
    onto the existing grid instead of shifting every future fire time.

    Strictly after `now` matters as much as the bucketing does. Arming the
    *current* bucket would re-schedule a job the scheduler may have just
    promoted, and that job would run a second time.
    """
    epoch = int(now.timestamp())
    return datetime.fromtimestamp((epoch // interval + 1) * interval, tz=timezone.utc)


def job_id_for(name: str, fire_at: datetime, interval: int) -> str:
    """Stable id per (job, bucket). Re-arming the same bucket is a no-op in
    Redis — `ScheduledJobRegistry.schedule` is a ZADD without NX, so the same
    member updates its score instead of adding a second entry."""
    bucket = int(fire_at.timestamp()) // interval
    return f"beat:{name}:{bucket}"


def arm_jobs(
    queue: SupportsSchedule,
    registry: SupportsSchedule,
    schedules: Sequence[tuple[str, int, str]] = SCHEDULES,
    now: datetime | None = None,
) -> list[str]:
    """Ensure exactly one pending job per schedule. Returns the ids armed.

    Idempotent by construction: a bucket already present in the scheduled
    registry is skipped, so restarting `beat` never queues a second copy of a
    job that is already pending, and a second `beat` instance racing the first
    converges on the same set rather than doubling it.
    """
    now = now or datetime.now(tz=timezone.utc)
    pending = set(registry.get_job_ids())
    armed: list[str] = []

    for name, default, env_name in schedules:
        interval = _interval(default, env_name)
        fire_at = next_due(now, interval)
        jid = job_id_for(name, fire_at, interval)
        if jid in pending:
            continue
        queue.enqueue_at(
            fire_at,
            f"jobs.{name}",
            job_id=jid,
            job_timeout=_timeout(interval),
            description=f"vantor {name} (every {interval}s)",
        )
        log.info("scheduled %s at %s (id=%s)", name, fire_at.isoformat(), jid)
        armed.append(jid)

    return armed


class BeatScheduler(RQScheduler):
    """`RQScheduler` that re-arms the recurring schedule on every tick.

    `work()` already calls `enqueue_scheduled_jobs()` once per interval; doing
    the arming in the same override means the schedule is topped up in the same
    breath that due jobs are promoted, with no second loop that could die on its
    own and leave the schedule silently decaying.
    """

    def __init__(
        self,
        queue: Queue,
        connection: Redis,
        schedules: Sequence[tuple[str, int, str]] = SCHEDULES,
        **kwargs: object,
    ) -> None:
        super().__init__([queue], connection=connection, **kwargs)  # type: ignore[arg-type]
        self._queue = queue
        # Same Redis key the scheduler promotes from; used only to read what is
        # already pending.
        self._registry = ScheduledJobRegistry(queue.name, connection=connection)
        self._schedules = schedules

    def enqueue_scheduled_jobs(self) -> None:
        try:
            armed = arm_jobs(self._queue, self._registry, self._schedules)
        except Exception:  # never let a Redis blip stop the promote step
            log.exception("could not re-arm the recurring schedule")
        else:
            if armed:
                log.debug("armed %d job(s)", len(armed))
        super().enqueue_scheduled_jobs()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    queue = Queue("default", connection=redis)

    # Seed before the first tick so a fresh stack has a pending job even if the
    # loop's first pass is delayed by a slow Redis.
    arm_jobs(queue, ScheduledJobRegistry(queue.name, connection=redis))

    scheduler = BeatScheduler(queue, redis, interval=TICK_S)
    log.info(
        "beat starting: queue=%s tick=%ss schedules=%s",
        queue.name,
        TICK_S,
        ", ".join(f"{n} every {_interval(d, e)}s" for n, d, e in SCHEDULES),
    )
    # `work()` installs SIGINT/SIGTERM handlers and releases its locks on stop,
    # which is the graceful shutdown this service needs.
    scheduler.work()


if __name__ == "__main__":
    main()
