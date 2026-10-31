"""Local stand-in for API Gateway: plain HTTP in, Lambda proxy event to RIE out.

Emulates the API key (`x-api-key`, 403) and the usage plan (token bucket per method class,
daily POST quota, 429), both answered with JSON bodies. Configured by environment
variables: API_KEY (unset disables the check), RATE_PER_SECOND, BURST, DAILY_POST_LIMIT,
GET_RATE_PER_SECOND, GET_BURST. The 29 s timeout and the 10 MB limit are not emulated; the
post-deploy smoke test covers them.
"""

import json
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response

Invoke = Callable[[dict[str, Any]], dict[str, Any]]

_DAY = 24 * 3600


def rie_invoker(url: str) -> Invoke:
    def invoke(event: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(event).encode(), method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    return invoke


class TokenBucket:
    def __init__(self, rate: float, burst: int, clock: Callable[[], float]) -> None:
        self._rate, self._burst, self._clock = rate, burst, clock
        self._tokens = float(burst)
        self._last = clock()

    def take(self) -> bool:
        now = self._clock()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True


def _json(status: int, message: str) -> Response:
    return Response(
        content=json.dumps({"message": message}), status_code=status, media_type="application/json"
    )


def create_app(
    invoke: Invoke,
    *,
    api_key: str | None = None,
    rate_per_second: float = 1000,
    burst: int = 1000,
    daily_post_limit: int = 1_000_000,
    get_rate_per_second: float = 1000,
    get_burst: int = 1000,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    app = FastAPI(title="API shim")
    lock = threading.Lock()  # one RIE container handles one invocation at a time
    buckets = {
        "POST": TokenBucket(rate_per_second, burst, clock),
        "GET": TokenBucket(get_rate_per_second, get_burst, clock),
    }
    quota = {"day_start": clock(), "posts": 0}

    def throttled(method: str) -> bool:
        with lock:
            if clock() - quota["day_start"] >= _DAY:
                quota.update(day_start=clock(), posts=0)
            if not buckets[method].take():
                return True
            if method == "POST":
                if quota["posts"] >= daily_post_limit:
                    return True
                quota["posts"] += 1
        return False

    def call(
        request: Request, method: str, path: str, path_parameters: dict[str, str] | None
    ) -> Response:
        if api_key is not None and request.headers.get("x-api-key") != api_key:
            return _json(403, "Forbidden")
        if throttled(method):
            return _json(429, "Too Many Requests")
        event = {
            "httpMethod": method,
            "path": path,
            "pathParameters": path_parameters,
            "headers": {k.lower(): v for k, v in request.headers.items()},
        }
        with lock:
            result = invoke(event)
        return Response(
            content=result.get("body", ""),
            status_code=result["statusCode"],
            media_type="application/json",
        )

    @app.post("/jobs")
    def create_job(request: Request) -> Response:
        return call(request, "POST", "/jobs", None)

    @app.get("/jobs/{job_id}")
    def get_job(request: Request, job_id: str) -> Response:
        return call(request, "GET", f"/jobs/{job_id}", {"job_id": job_id})

    return app


def app() -> FastAPI:
    """uvicorn factory: `uvicorn --factory invoice_extraction.entrypoints.api_shim:app`."""
    env = os.environ.get
    return create_app(
        rie_invoker(os.environ["API_LAMBDA_URL"]),
        api_key=env("API_KEY") or None,
        rate_per_second=float(env("RATE_PER_SECOND", 1000)),
        burst=int(env("BURST", 1000)),
        daily_post_limit=int(env("DAILY_POST_LIMIT", 1_000_000)),
        get_rate_per_second=float(env("GET_RATE_PER_SECOND", 1000)),
        get_burst=int(env("GET_BURST", 1000)),
    )
