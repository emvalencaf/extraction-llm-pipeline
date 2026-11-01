"""API Gateway proxy-event shape shared by the API handler and the local API shim."""

from typing import Any


def lowercase_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Header names are case-insensitive; the handler and the shim both look them up lowercase."""
    return {name.lower(): value for name, value in (headers or {}).items()}


def proxy_event(
    method: str,
    path: str,
    path_parameters: dict[str, str] | None,
    headers: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "httpMethod": method,
        "path": path,
        "pathParameters": path_parameters,
        "headers": lowercase_headers(headers),
    }


def idempotency_key(event: dict[str, Any]) -> str | None:
    return lowercase_headers(event.get("headers")).get("idempotency-key") or None


def path_job_id(event: dict[str, Any]) -> str | None:
    return (event.get("pathParameters") or {}).get("job_id")
