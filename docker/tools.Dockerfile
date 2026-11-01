# Local-only helper services: API shim, poller, init and fake-gemini.
FROM python:3.12-slim

RUN pip install --no-cache-dir "boto3>=1.43" "fastapi>=0.100" "uvicorn>=0.30" \
    "pydantic>=2.14" "pypdf>=6.21"
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
WORKDIR /app
COPY src ./src
