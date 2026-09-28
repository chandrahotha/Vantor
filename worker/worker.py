"""RQ worker entrypoint — listens on default + documents queues.

B-41: this file used to end with `Worker(queues).work()`, passing the queues but
not the connection. In the pinned rq 1.16.2 that is a crash on boot, not a
default:

    Worker._set_connection(None)  ->  get_current_connection()  ->  None
    ->  None.connection_pool      ->  AttributeError

`get_current_connection()` resolves inside rq's own fork-based work-horse; there
is no current fork in the parent process, so it answers `None` and the very next
line dereferences it. Verified against the installed library:

    rq/worker.py:147   connection = self._set_connection(connection)
    rq/worker.py:298   if connection is None: connection = get_current_connection()
    rq/worker.py:300   current_socket_timeout = connection.connection_pool...

So the `worker` container exited immediately, and everything `beat.py` had
scheduled piled up in `rq:queue:default` with no consumer. It is B-34's exact
shape, one file over: a scheduler that arms jobs nobody runs, discovered by
running the two of them against a real Redis and watching the queue length grow.

The connection is now passed explicitly, and the wiring is a function rather than
module-level code so `tests/test_worker.py` can construct the worker without
Redis and without a fork.
"""
from __future__ import annotations

import os

from redis import Redis
from rq import Queue, Worker

#: Queues the worker consumes. `documents` is deliberately empty — see
#: README.md — and is listed so a future enqueue has somewhere to land.
QUEUE_NAMES = ("default", "documents")


def build_queues(connection: Redis) -> list[Queue]:
    return [Queue(name, connection=connection) for name in QUEUE_NAMES]


def build_worker(connection: Redis) -> Worker:
    """The worker, wired the way rq 1.16.2 actually requires.

    `connection` is a positional-or-keyword argument with a real default; passing
    it is not optional, it is the difference between a worker and a traceback.
    """
    return Worker(build_queues(connection), connection=connection)


def main() -> None:
    connection = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    build_worker(connection).work()


if __name__ == "__main__":
    main()
