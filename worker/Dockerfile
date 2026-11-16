# Base image pinned by digest — a tag is a mutable name. Refresh with
# `python scripts/pin_digests.py`; `scripts/pin_digests.py --check` enforces it.
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
WORKDIR /srv/worker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobs.py worker.py enqueue.py beat.py .
CMD ["python", "worker.py"]
