#!/usr/bin/env python3
"""Post the gate report as one sticky PR comment: find it by its hidden marker, update it.

Usage (CI):
    GITHUB_TOKEN=... python3 scripts/sticky_comment.py --repo owner/name --pr 12 \
        --report gate-report.md [--run-url URL]

The comment is found by the marker on the first line of the report (`REPORT_MARKER` in
`invoice_extraction.domain.gate`) among comments written by a bot, so a user quoting the
marker can neither hijack nor block the sticky comment. A missing report (the gate crashed
before writing one) still produces a comment: an INCONCLUSIVE notice pointing at the run.
Standard library only, so the comment job needs no dependency install.
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Protocol

MARKER = "<!-- regression-gate -->"  # must equal domain.gate.REPORT_MARKER (a test checks)
MAX_BODY = 65_000  # GitHub rejects comment bodies over 65536 characters
API = "https://api.github.com"


class CommentApi(Protocol):
    def list_comments(self) -> list[dict[str, Any]]: ...
    def create(self, body: str) -> None: ...
    def update(self, comment_id: int, body: str) -> None: ...


def _is_bot(comment: dict[str, Any]) -> bool:
    return (comment.get("user") or {}).get("type") == "Bot"


def find_sticky(comments: list[dict[str, Any]], marker: str) -> dict[str, Any] | None:
    """The newest bot comment carrying the marker, or None."""
    marked = [c for c in comments if _is_bot(c) and marker in (c.get("body") or "")]
    return max(marked, key=lambda c: c["id"], default=None)


def _prepare(body: str, marker: str) -> str:
    if marker not in body:
        body = f"{marker}\n{body}"
    if len(body) > MAX_BODY:
        body = body[: MAX_BODY - 40] + "\n\n_(report truncated)_\n"
    return body


def upsert(api: CommentApi, body: str, marker: str) -> str:
    """Create the sticky comment, or update the existing one. Returns 'created' or 'updated'."""
    body = _prepare(body, marker)
    existing = find_sticky(api.list_comments(), marker)
    if existing is None:
        api.create(body)
        return "created"
    api.update(existing["id"], body)
    return "updated"


def read_report(path: Path, marker: str, run_url: str = "") -> str:
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return path.read_text(encoding="utf-8")
    where = f" See the [workflow run]({run_url})." if run_url else ""
    return (
        f"{marker}\n## Regression gate: INCONCLUSIVE\n\n"
        f"- The gate produced no report (it crashed or was cancelled), which counts as a "
        f"failure.{where}\n"
    )


class GitHubApi:
    def __init__(self, repo: str, pr: int, token: str) -> None:
        self._repo, self._pr, self._token = repo, pr, token

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            url,
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or "null")

    def list_comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            url = f"{API}/repos/{self._repo}/issues/{self._pr}/comments?per_page=100&page={page}"
            batch = self._request("GET", url)
            comments += batch
            if len(batch) < 100:
                return comments
            page += 1

    def create(self, body: str) -> None:
        url = f"{API}/repos/{self._repo}/issues/{self._pr}/comments"
        self._request("POST", url, {"body": body})

    def update(self, comment_id: int, body: str) -> None:
        url = f"{API}/repos/{self._repo}/issues/comments/{comment_id}"
        self._request("PATCH", url, {"body": body})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--report", type=Path, default=Path("gate-report.md"))
    parser.add_argument("--run-url", default="")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        return 2
    body = read_report(args.report, MARKER, args.run_url)
    print(f"sticky comment {upsert(GitHubApi(args.repo, args.pr, token), body, MARKER)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
