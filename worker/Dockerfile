FROM python:3.13-slim
WORKDIR /srv/worker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobs.py worker.py enqueue.py beat.py .
CMD ["python", "worker.py"]
