"""Worker wiring — the B-41 regression needs no Redis; the rest wants one.

B-41: `worker.py` ended with `Worker(queues).work()` and no connection, which is
an immediate `AttributeError` in the pinned rq 1.16.2 rather than a default:

    rq/worker.py:147  connection = self._set_connection(connection)
    rq/worker.py:298  if connection is None: connection = get_current_connection()
    rq/worker.py:300  current_socket_timeout = connection.connection_pool...

`get_current_connection()` resolves inside rq's fork-based work-horse. In the
parent process — which is where the entrypoint runs — there is no current fork,
so it answers `None` and the next line dereferences it. The `worker` container
exited on boot, and everything `beat.py` scheduled piled up in `rq:queue:default`
with no consumer. `test_beat.py` could not have caught it: it never builds a
Worker.

The two halves below are split on purpose.

* `TestTheDefectThisFileExistsFor` needs nothing. The crash happens on line 300,
  before rq opens a socket, so it is reproduced in any environment — this is the
  regression and it runs everywhere, including in CI's worker job.
* `TestWorkerConstruction` builds a real `rq.Worker`, and `Worker.__init__` calls
  `connection.client_setname(...)` at `rq/worker.py:205`, so it needs a reachable
  Redis. It skips without `RQ_TEST_REDIS_URL`; CI's worker job provides one.

A test that only ever runs where a dependency happens to be present is the B-07
shape, which is why the no-Redis half carries the regression on its own.
"""
from __future__ import annotations

import os
import sys

import pytest
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Worker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker  # noqa: E402

RQ_TEST_REDIS_URL = os.getenv("RQ_TEST_REDIS_URL", "").strip()


def live_connection() -> Redis:
    """A connection to a Redis that is actually there, or skip."""
    if not RQ_TEST_REDIS_URL:
        pytest.skip("RQ_TEST_REDIS_URL is not set — point it at a Redis instance")
    try:
        Redis.from_url(RQ_TEST_REDIS_URL).ping()
    except RedisError as exc:
        pytest.skip(f"Redis unusable at {RQ_TEST_REDIS_URL} ({exc})")
    return Redis.from_url(RQ_TEST_REDIS_URL)


class TestTheDefectThisFileExistsFor:
    def test_the_omitted_connection_is_a_crash_not_a_default(self):
        # Pinned so a future refactor cannot quietly go back to the form that
        # looks idiomatic and crash-loops the container.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(AttributeError):
                Worker([Queue("default", connection=Redis.from_url("redis://127.0.0.1:1/0"))])

    def test_build_worker_hands_rq_a_connection_argument(self, monkeypatch):
        # Behavioural, not a source scan: the fix is that `Worker` is *called*
        # with a connection, and rq's default is the crash above. Recorded here
        # so the call itself is pinned, not just the outcome. A lazy client is
        # enough — nothing here opens a socket.
        seen: dict[str, object] = {}

        class Recorder:
            def __init__(self, queues, **kwargs):
                seen["queues"] = queues
                seen["connection"] = kwargs.get("connection")

        monkeypatch.setattr(worker, "Worker", Recorder)
        connection = Redis.from_url("redis://127.0.0.1:1/0")
        worker.build_worker(connection)
        assert seen["connection"] is connection
        assert {q.name for q in seen["queues"]} == set(worker.QUEUE_NAMES)


class TestWorkerConstruction:
    def test_build_worker_returns_a_real_rq_worker(self):
        assert isinstance(worker.build_worker(live_connection()), Worker)

    def test_the_worker_is_given_the_connection_it_was_built_with(self):
        connection = live_connection()
        assert worker.build_worker(connection).connection is connection

    def test_listens_on_both_documented_queues(self):
        w = worker.build_worker(live_connection())
        assert {q.name for q in w.queues} == set(worker.QUEUE_NAMES)

    def test_every_queue_shares_the_one_connection(self):
        connection = live_connection()
        queues = worker.build_queues(connection)
        assert [q.connection for q in queues] == [connection] * len(queues)
        assert all(isinstance(q, Queue) for q in queues)


class TestQueueNames:
    def test_documents_is_still_listed_even_though_it_is_empty(self):
        # `documents` is a reserved queue with no producers. Dropping it would
        # silently change where a future OCR job has to be sent.
        assert worker.QUEUE_NAMES == ("default", "documents")
