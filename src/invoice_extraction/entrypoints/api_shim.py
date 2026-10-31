"""Local stand-in for API Gateway: plain HTTP in, Lambda proxy event to RIE out.

API keys, usage plans, the 29 s timeout and the 10 MB limit are not emulated; the
post-deploy smoke test covers them.
"""

import json
import os
import threading
import urllib.request
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Response

Invoke = Callable[[dict[str, Any]], dict[str, Any]]


def rie_invoker(url: str) -> Invoke:
    def invoke(event: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(event).encode(), method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    return invoke


def create_app(invoke: Invoke) -> FastAPI:
    app = FastAPI(title="API shim")
    lock = threading.Lock()  # one RIE container handles one invocation at a time

    def call(method: str, path: str, path_parameters: dict[str, str] | None) -> Response:
        event = {"httpMethod": method, "path": path, "pathParameters": path_parameters}
        with lock:
            result = invoke(event)
        return Response(
            content=result.get("body", ""),
            status_code=result["statusCode"],
            media_type="application/json",
        )

    @app.post("/jobs")
    def create_job() -> Response:
        return call("POST", "/jobs", None)

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> Response:
        return call("GET", f"/jobs/{job_id}", {"job_id": job_id})

    return app


def app() -> FastAPI:
    """uvicorn factory: `uvicorn --factory invoice_extraction.entrypoints.api_shim:app`."""
    return create_app(rie_invoker(os.environ["API_LAMBDA_URL"]))
