"""Scheduler tests — structural, no Redis and no network.

B-34 was not a subtle bug: `beat.py` called `RQScheduler(queue_name=...)` and
`scheduler.schedule(...)`, and neither exists in the pinned rq 1.16.2, so the
service died on boot. The tests below pin the properties that actually matter
and that a fake can prove:

- the constructors and methods called are the ones the installed rq exposes
  (asserted against `rq.scheduler.RQScheduler` / `rq.Queue` themselves, so a
  future pin bump fails here rather than in production);
- every schedule is armed exactly once per bucket, so a restart or a second
  instance cannot double-run a job;
- a bucket is only ever armed while it is in the future.

They deliberately do not try to prove RQ's own promotion logic — that belongs to
the library and is covered by its tests against a real Redis.
"""
from __future__ import annotations

import inspect
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from rq import Queue
from rq.scheduler import RQScheduler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beat  # noqa: E402

NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)


class FakeQueue:
    """Records what would have been written to Redis."""

    def __init__(self) -> None:
        self.name = "default"
        self.scheduled: list[dict] = []

    def enqueue_at(self, datetime_, f, *args, **kwargs):  # noqa: A002 - mirrors rq's signature
        self.scheduled.append({"at": datetime_, "func": f, **kwargs})
        return kwargs.get("job_id")

    def get_job_ids(self, start: int = 0, end: int = -1) -> list[str]:
        return []


class FakeRegistry:
    def __init__(self, ids: list[str] | None = None) -> None:
        self.ids = list(ids or [])

    def get_job_ids(self, start: int = 0, end: int = -1) -> list[str]:
        return self.ids

    def add(self, jid: str) -> None:
        self.ids.append(jid)


def env(**overrides: str) -> None:
    for key in ("ROLL_EXPIRY_INTERVAL_S", "WEBHOOK_DRAIN_INTERVAL_S", "SPEND_SNAPSHOT_INTERVAL_S"):
        os.environ.pop(key, None)
    os.environ.update(overrides)


class TestInstalledRqApi:
    """The contract this module is written against."""

    def test_constructor_takes_queues_and_connection(self):
        params = inspect.signature(RQScheduler.__init__).parameters
        assert "queues" in params
        assert "connection" in params
        # The call that used to crash the service on boot.
        assert "queue_name" not in params

    def test_scheduler_has_no_schedule_method(self):
        assert not hasattr(RQScheduler, "schedule")

    def test_enqueue_takes_no_repeat(self):
        # `repeat=` was also passed to `schedule()` here; rq 1.16.2's `enqueue`
        # has no such parameter, so a recurring schedule must be re-armed.
        assert "repeat" not in inspect.signature(Queue.enqueue).parameters

    def test_enqueue_at_is_the_documented_entry_point(self):
        assert "datetime" in inspect.signature(Queue.enqueue_at).parameters


class TestNextDue:
    @pytest.mark.parametrize("interval", [30, 3600, beat.DAY_S])
    def test_is_strictly_in_the_future(self, interval: int):
        fire = beat.next_due(NOW, interval)
        assert fire > NOW

    def test_snaps_to_the_interval_grid(self):
        # 12:00:00 exactly: the next fire is the following boundary, never 12:00
        # itself, which would be immediately due and could re-run a just-promoted
        # job.
        assert beat.next_due(NOW, 30) == datetime(2026, 3, 14, 12, 0, 30, tzinfo=timezone.utc)

    def test_mid_bucket_snaps_forward(self):
        # 17s into the 12:00:00-12:00:30 window, so 12:00:30 is the next
        # boundary — not 12:01:00, and not 12:00:47.
        mid = NOW + timedelta(seconds=17)
        assert beat.next_due(mid, 30) == datetime(2026, 3, 14, 12, 0, 30, tzinfo=timezone.utc)

    def test_is_drift_free_after_downtime(self):
        # Beat was down for an hour and came back mid-bucket. Re-arming must
        # land on the absolute grid (…12:00, 13:00, 14:00…), not on
        # "restart time + interval", which would shift every future fire time by
        # the length of the outage.
        late = NOW + timedelta(hours=1, seconds=17)
        assert beat.next_due(late, 3600) == datetime(2026, 3, 14, 14, 0, 0, tzinfo=timezone.utc)

    def test_rejects_non_positive_interval(self):
        with pytest.raises(ZeroDivisionError):
            beat.next_due(NOW, 0)


class TestJobIds:
    def test_is_stable_within_a_bucket(self):
        a = beat.job_id_for("roll_expiry", NOW, 3600)
        b = beat.job_id_for("roll_expiry", NOW + timedelta(seconds=5), 3600)
        assert a == b

    def test_differs_across_buckets(self):
        a = beat.job_id_for("roll_expiry", NOW, 3600)
        b = beat.job_id_for("roll_expiry", NOW + timedelta(hours=1), 3600)
        assert a != b

    def test_is_namespaced_by_job(self):
        a = beat.job_id_for("roll_expiry", NOW, 3600)
        b = beat.job_id_for("spend_snapshot", NOW, 3600)
        assert a != b


class TestArming:
    def setup_method(self):
        env()

    def test_arms_every_schedule_exactly_once(self):
        q, r = FakeQueue(), FakeRegistry()
        beat.arm_jobs(q, r, beat.SCHEDULES, NOW)
        assert len(q.scheduled) == len(beat.SCHEDULES)
        funcs = sorted(s["func"] for s in q.scheduled)
        assert funcs == ["jobs.drain_webhooks", "jobs.roll_expiry", "jobs.spend_snapshot"]

    def test_a_restart_arms_nothing(self):
        # First pass arms everything and records the ids.
        q, r = FakeQueue(), FakeRegistry()
        armed = beat.arm_jobs(q, r, beat.SCHEDULES, NOW)
        r.ids.extend(armed)

        # Restart: new process, same Redis. Nothing new may be queued.
        q2 = FakeQueue()
        again = beat.arm_jobs(q2, r, beat.SCHEDULES, NOW)
        assert again == []
        assert q2.scheduled == []

    def test_only_arms_the_next_bucket_never_the_past(self):
        q, _ = FakeQueue(), FakeRegistry()
        beat.arm_jobs(q, FakeRegistry(), beat.SCHEDULES, NOW)
        assert all(s["at"] > NOW for s in q.scheduled)

    def test_reschedules_a_missing_bucket_without_touching_the_others(self):
        r = FakeRegistry()
        roll = beat.job_id_for("roll_expiry", beat.next_due(NOW, beat.DAY_S), beat.DAY_S)
        drain = beat.job_id_for("drain_webhooks", beat.next_due(NOW, 30), 30)
        r.ids.extend([roll, drain])

        q = FakeQueue()
        armed = beat.arm_jobs(q, r, beat.SCHEDULES, NOW)
        # Only the one that was genuinely missing gets re-armed.
        assert len(armed) == 1
        assert armed[0].startswith("beat:spend_snapshot:")

    def test_every_armed_job_is_immediately_due_free(self):
        # A job armed for its own bucket time would be promoted on the next tick
        # and could run twice; assert the two are never equal.
        q, _ = FakeQueue(), FakeRegistry()
        beat.arm_jobs(q, FakeRegistry(), beat.SCHEDULES, NOW)
        for s in q.scheduled:
            assert s["at"] > NOW

    def test_sets_a_bounded_job_timeout(self):
        q, _ = FakeQueue(), FakeRegistry()
        beat.arm_jobs(q, FakeRegistry(), beat.SCHEDULES, NOW)
        for s in q.scheduled:
            assert beat.JOB_TIMEOUT_FLOOR_S <= s["job_timeout"] <= beat.JOB_TIMEOUT_CEILING_S


class TestIntervalConfig:
    def setup_method(self):
        env()

    def test_default_used_when_unset(self):
        assert beat._interval(30, "WEBHOOK_DRAIN_INTERVAL_S") == 30

    def test_env_override(self):
        os.environ["WEBHOOK_DRAIN_INTERVAL_S"] = "45"
        assert beat._interval(30, "WEBHOOK_DRAIN_INTERVAL_S") == 45

    @pytest.mark.parametrize("raw", ["0", "-5", "abc", "", "   "])
    def test_bad_values_fall_back_instead_of_spinning(self, raw: str):
        os.environ["WEBHOOK_DRAIN_INTERVAL_S"] = raw
        assert beat._interval(30, "WEBHOOK_DRAIN_INTERVAL_S") == 30

    def test_arm_uses_the_configured_interval(self):
        os.environ["WEBHOOK_DRAIN_INTERVAL_S"] = "600"
        q, _ = FakeQueue(), FakeRegistry()
        beat.arm_jobs(q, FakeRegistry(), beat.SCHEDULES, NOW)
        drain = next(s for s in q.scheduled if s["func"] == "jobs.drain_webhooks")
        assert drain["at"] == datetime(2026, 3, 14, 12, 10, 0, tzinfo=timezone.utc)


class TestBeatScheduler:
    def test_is_a_real_rq_scheduler(self):
        assert issubclass(beat.BeatScheduler, RQScheduler)

    def test_constructs_with_a_queue_list_not_a_name(self):
        # The original crash, pinned as a test.
        params = inspect.signature(beat.BeatScheduler.__init__).parameters
        assert "queue" in params
        assert "queue_name" not in params

    def test_arming_failure_does_not_stop_promotion(self, monkeypatch):
        # A Redis blip while re-arming must not stop due jobs from being moved
        # off the scheduled registry, and must not kill the loop.
        def boom(*_a, **_k):
            raise RuntimeError("redis down")

        promoted = []
        monkeypatch.setattr(beat, "arm_jobs", boom)
        monkeypatch.setattr(
            RQScheduler, "enqueue_scheduled_jobs", lambda self: promoted.append(True)
        )
        sched = beat.BeatScheduler.__new__(beat.BeatScheduler)
        sched._queue = FakeQueue()
        sched._registry = FakeRegistry()
        sched._schedules = beat.SCHEDULES
        sched.enqueue_scheduled_jobs()
        assert promoted == [True]
