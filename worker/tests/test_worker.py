"""Worker wiring — the B-41 regression needs no Redis; the rest wants one.

B-41: `worker.py` ended with `Worker(queues).work()` and no connection, which is
an immediate crash rather than a default:

    rq 1.16.2  rq/worker.py:147  connection = self._set_connection(connection)
               rq/worker.py:298  if connection is None: connection = get_current_connection()
               rq/worker.py:300  current_socket_timeout = connection.connection_pool...
               -> AttributeError: 'NoneType' object has no attribute 'connection_pool'

    rq 3.0.0   the worker resolves a default connection first and then talks to
               Redis, so the missing connection surfaces as
               `redis.exceptions.ConnectionError` when the server cannot be reached.

`get_current_connection()` resolves inside rq's fork-based work-horse. In the
parent process — which is where the entrypoint runs — there is no current fork,
so it answers `None` and the next line dereferences it. The `worker` container
exited on boot, and everything `beat.py` scheduled piled up in `rq:queue:default`
with no consumer. `test_beat.py` could not have caught it: it never builds a
Worker.

The two halves below are split on purpose.

* `TestTheDefectThisFileExistsFor` needs nothing but a port nothing listens on.
  rq 1.16.2 crashed before it opened a socket; rq 3.0.0 fails when it cannot
  reach Redis, so the test points the worker at a closed port. Either way the
  crash is reproduced in any environment — this is the regression and it runs
  everywhere, including in CI's worker job.
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
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from rq import Queue, Worker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker  # noqa: E402

RQ_TEST_REDIS_URL = os.getenv("RQ_TEST_REDIS_URL", "").strip()


def live_connection() -> Redis:
    """A connection to a Redis that is there, or skip when none was ever asked for.

    Unset means "this environment is not the Redis tier" and a skip is honest.
    Set-but-unreachable is a failure: the CI job that exists to exercise real
    queue delivery used to turn a dead Redis into four skips and report green.
    """
    if not RQ_TEST_REDIS_URL:
        pytest.skip("RQ_TEST_REDIS_URL is not set — point it at a Redis instance")
    try:
        Redis.from_url(RQ_TEST_REDIS_URL).ping()
    except RedisError as exc:
        pytest.fail(
            f"RQ_TEST_REDIS_URL is set to {RQ_TEST_REDIS_URL!r} but Redis is not "
            f"usable there: {exc}\n"
            "    Start Redis, or unset RQ_TEST_REDIS_URL to say this environment is "
            "not the Redis tier.",
            pytrace=False,
        )
    return Redis.from_url(RQ_TEST_REDIS_URL)


class TestTheDefectThisFileExistsFor:
    def test_the_omitted_connection_is_a_crash_not_a_default(self):
        # Pinned so a future refactor cannot quietly go back to the form that
        # looks idiomatic and crash-loops the container.
        #
        # The exception type moved with the rq major: rq 1.16.2 dereferenced a
        # `None` connection and raised `AttributeError`, while rq 3.0.0 resolves
        # a default connection and fails when it cannot reach Redis. Both are
        # the same crash — a worker that is *constructed* is the bug, and which
        # exception rq raises about it is rq's business, not ours.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises((AttributeError, RedisConnectionError)):
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
