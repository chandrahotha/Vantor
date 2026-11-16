# Base image pinned by digest — a tag is a mutable name. Refresh with
# `python scripts/pin_digests.py`; `scripts/pin_digests.py --check` enforces it.
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/api

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini alembic.ini
COPY alembic alembic
COPY app app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
