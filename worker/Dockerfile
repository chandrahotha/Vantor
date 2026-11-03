# Base image pinned by digest — a tag is a mutable name. Refresh with
# `python scripts/pin_digests.py`; `scripts/pin_digests.py --check` enforces it.
FROM python:3.14-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
WORKDIR /srv/worker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobs.py worker.py enqueue.py beat.py .
CMD ["python", "worker.py"]
