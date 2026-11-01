"""The sticky PR comment: one comment per marker, updated in place, never duplicated."""

import importlib.util
from pathlib import Path

from invoice_extraction.domain.gate import REPORT_MARKER

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sticky_comment", ROOT / "scripts/sticky_comment.py")
sticky = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sticky)

BOT = {"login": "github-actions[bot]", "type": "Bot"}


class FakeApi:
    def __init__(self, comments=()):
        self.comments = list(comments)
        self.calls = []

    def list_comments(self):
        return list(self.comments)

    def create(self, body):
        self.calls.append(("create", body))
        self.comments.append({"id": 100 + len(self.comments), "body": body, "user": BOT})

    def update(self, comment_id, body):
        self.calls.append(("update", comment_id, body))
        for comment in self.comments:
            if comment["id"] == comment_id:
                comment["body"] = body


def report(text="## Regression gate: PASS"):
    return f"{REPORT_MARKER}\n{text}\n"


def test_creates_the_comment_when_none_has_the_marker():
    api = FakeApi([{"id": 1, "body": "looks good", "user": {"login": "dev", "type": "User"}}])
    sticky.upsert(api, report(), REPORT_MARKER)
    assert [call[0] for call in api.calls] == ["create"]


def test_second_run_updates_instead_of_duplicating():
    api = FakeApi()
    sticky.upsert(api, report("first"), REPORT_MARKER)
    sticky.upsert(api, report("second"), REPORT_MARKER)
    assert [call[0] for call in api.calls] == ["create", "update"]
    assert len(api.comments) == 1
    assert "second" in api.comments[0]["body"]


def test_ignores_a_user_comment_that_quotes_the_marker():
    spoof = {"id": 5, "body": report("fake"), "user": {"login": "evil", "type": "User"}}
    api = FakeApi([spoof])
    sticky.upsert(api, report(), REPORT_MARKER)
    assert [call[0] for call in api.calls] == ["create"]


def test_updates_the_newest_marked_comment_when_there_are_several():
    old = {"id": 1, "body": report("old"), "user": BOT}
    new = {"id": 2, "body": report("new"), "user": BOT}
    api = FakeApi([old, new])
    sticky.upsert(api, report("latest"), REPORT_MARKER)
    assert api.calls[0][:2] == ("update", 2)


def test_body_always_carries_the_marker_and_fits_the_github_limit():
    api = FakeApi()
    sticky.upsert(api, "no marker here " + "x" * 70_000, REPORT_MARKER)
    body = api.comments[0]["body"]
    assert body.startswith(REPORT_MARKER)
    assert len(body) <= sticky.MAX_BODY


def test_missing_report_posts_a_failure_notice_with_the_marker(tmp_path):
    text = sticky.read_report(tmp_path / "absent.md", REPORT_MARKER, run_url="https://x/run/1")
    assert text.startswith(REPORT_MARKER)
    assert "INCONCLUSIVE" in text
    assert "https://x/run/1" in text


def test_script_marker_matches_the_report_marker():
    assert sticky.MARKER == REPORT_MARKER
