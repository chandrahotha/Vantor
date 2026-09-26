"""Enqueue helper: python enqueue.py roll_expiry|spend_snapshot."""
from __future__ import annotations

import os
import sys

from redis import Redis
from rq import Queue

from jobs import JOB_MAP

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in JOB_MAP:
        raise SystemExit(f"usage: enqueue.py {{{'|'.join(sorted(JOB_MAP))}}}")
    q = Queue("default", connection=Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0")))
    # String path keeps the payload unpickle-robust across deploys.
    job = q.enqueue(f"jobs.{name}")
    print(job.id)
