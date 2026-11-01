"""The observability module's alarms and dashboard name only metrics the app emits (#37)."""

import re
from pathlib import Path

from invoice_extraction.adapters.json_events import NAMESPACE, to_record
from invoice_extraction.application.observability import JobEvent, LlmCallEvent

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "infra" / "modules" / "observability"
RUNBOOK = ROOT / "docs" / "runbook.md"


def emitted_metrics() -> set[str]:
    """Metric names declared by the real EMF record of both event kinds."""
    llm_call = LlmCallEvent(
        model="m",
        tier="primary",
        attempt=1,
        repair=False,
        outcome="ok",
        latency_ms=1.0,
        prompt_version="v",
        input_tokens=1,
        output_tokens=1,
    )
    job = JobEvent(outcome="succeeded", duration_ms=1.0, prompt_version="v", grounding_rate=1.0)
    names: set[str] = set()
    for event in (llm_call, job):
        (block,) = to_record(event)["_aws"]["CloudWatchMetrics"]
        assert block["Namespace"] == NAMESPACE
        assert block["Dimensions"] == [[]]
        names |= {m["Name"] for m in block["Metrics"]}
    return names


def referenced_app_metrics() -> set[str]:
    alarms = (MODULE / "app_alarms.tf").read_text()
    dashboard = (MODULE / "dashboard.tf").read_text()
    in_dashboard = re.findall(rf'"{NAMESPACE}",\s*"(\w+)"', dashboard)
    in_alarms = re.findall(r'metric_name\s*=\s*"(\w+)"', alarms)
    return set(in_dashboard) | set(in_alarms)


def alarm_names() -> list[str]:
    text = "".join(p.read_text() for p in MODULE.glob("*alarms.tf"))
    return re.findall(r'^\s*alarm_name\s*=\s*"\$\{var\.prefix\}-([a-z0-9-]+)"', text, re.M)


def test_app_alarms_and_dashboard_use_only_emitted_metrics():
    used = referenced_app_metrics()
    assert used, "no application metrics referenced"
    assert used <= emitted_metrics(), used - emitted_metrics()


def test_there_are_eight_alarms():
    assert len(alarm_names()) == 8


def test_every_alarm_has_a_runbook_entry():
    runbook = RUNBOOK.read_text()
    assert [n for n in alarm_names() if f"## `{n}`" not in runbook] == []
