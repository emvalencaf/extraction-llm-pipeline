"""Recaps (`away_summary` entries) are read from a transcript and rendered per session."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / ".agents/skills/usage-report/scripts"))

import usage_report
import views


def _transcript(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "abcdef12-0000-0000-0000-000000000000.jsonl"
    turn = {  # parse_session skips sessions without any token usage
        "type": "assistant",
        "timestamp": "2026-10-11T09:00:00Z",
        "message": {
            "id": "msg_1",
            "model": "test-model",
            "content": [],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    lines = [json.dumps(r) for r in (turn, *records)]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _recap(text: str, ts: str) -> dict:
    return {"type": "system", "subtype": "away_summary", "content": text, "timestamp": ts}


def test_recaps_are_collected_in_order_without_the_config_hint(tmp_path):
    path = _transcript(
        tmp_path,
        _recap("Primeiro recap. (disable recaps in /config)", "2026-10-11T10:00:00Z"),
        _recap("Segundo recap.", "2026-10-11T11:00:00Z"),
    )
    session = usage_report.parse_session(path, tmp_path)
    assert [r["text"] for r in session["recaps"]] == ["Primeiro recap.", "Segundo recap."]


def test_session_without_recaps_renders_no_row(tmp_path):
    session = usage_report.parse_session(
        _transcript(tmp_path, _recap("", "2026-10-11T10:00:00Z")), tmp_path
    )
    assert session["recaps"] == []
    assert views.recap_row(session, 11) == ""


def test_recap_row_lists_every_recap_escaped(tmp_path):
    path = _transcript(
        tmp_path,
        _recap("Feito <b>tudo</b>.", "2026-10-11T10:00:00Z"),
        _recap("Próximo passo.", "2026-10-11T11:00:00Z"),
    )
    session = usage_report.parse_session(path, tmp_path)
    row = views.recap_row(session, 11)
    assert "2 recaps" in row and "&lt;b&gt;tudo" in row and "Próximo passo." in row
