"""Lambda handler for the API: API Gateway proxy events for POST /jobs and GET /jobs/{id}."""

import json
from collections.abc import Callable
from typing import Any

from invoice_extraction.application.jobs import JobService

Handler = Callable[[dict[str, Any], Any], dict[str, Any]]


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def make_api_handler(service: JobService) -> Handler:
    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        method = event.get("httpMethod")
        if method == "POST" and event.get("path") == "/jobs":
            headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
            job = service.create(headers.get("idempotency-key") or None)
            return _response(200 if job.pop("replayed", False) else 201, job)
        job_id = (event.get("pathParameters") or {}).get("job_id")
        if method == "GET" and job_id:
            job = service.get(job_id)
            return _response(200, job) if job else _response(404, {"error": "job not found"})
        return _response(404, {"error": "not found"})

    return handler


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point; dependencies are wired from environment variables."""
    from invoice_extraction.composition.runtime import build_job_service

    return make_api_handler(build_job_service())(event, context)
