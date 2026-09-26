"""RQ worker entrypoint — listens on default + documents queues."""
from __future__ import annotations

import os

from redis import Redis
from rq import Queue, Worker

if __name__ == "__main__":
    redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    queues = [Queue("default", connection=redis), Queue("documents", connection=redis)]
    Worker(queues).work()
