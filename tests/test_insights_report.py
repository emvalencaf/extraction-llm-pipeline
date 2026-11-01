"""The CloudWatch Logs Insights report: queries, polling, and the Markdown it renders."""

import importlib.util
from pathlib import Path

import pytest

from invoice_extraction.adapters.json_events import to_record
from invoice_extraction.application.observability import JobEvent, LlmCallEvent

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "insights_report", ROOT / "scripts/insights_report.py"
)
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


class FakeLogs:
    """Stands in for the boto3 logs client: replays the given statuses, then the results."""

    def __init__(self, statuses=("Running", "Complete"), results=()):
        self.statuses = list(statuses)
        self.results = list(results)
        self.started = []

    def start_query(self, **kwargs):
        self.started.append(kwargs)
        return {"queryId": "q-1"}

    def get_query_results(self, queryId):  # noqa: N803  (boto3 keyword)
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"status": status, "results": self.results if status == "Complete" else []}


def cell(field, value):
    return {"field": field, "value": value}


def test_run_query_polls_until_complete_and_drops_the_pointer_column():
    logs = FakeLogs(results=[[cell("outcome", "succeeded"), cell("jobs", "3"), cell("@ptr", "x")]])

    rows = report.run_query(logs, ["/aws/lambda/w"], "stats count()", 0, 60, sleep=lambda s: None)

    assert rows == [{"outcome": "succeeded", "jobs": "3"}]
    assert logs.started[0]["logGroupNames"] == ["/aws/lambda/w"]
    assert logs.started[0]["startTime"] == 0 and logs.started[0]["endTime"] == 60


@pytest.mark.parametrize("status", ["Failed", "Cancelled", "Timeout"])
def test_run_query_fails_loudly_when_insights_does_not_complete(status):
    logs = FakeLogs(statuses=(status,))

    with pytest.raises(RuntimeError, match=status):
        report.run_query(logs, ["g"], "stats count()", 0, 60, sleep=lambda s: None)


def test_run_query_gives_up_when_the_query_never_finishes():
    logs = FakeLogs(statuses=("Running",))

    with pytest.raises(RuntimeError, match="did not finish"):
        report.run_query(logs, ["g"], "q", 0, 60, sleep=lambda s: None, max_polls=3)


def test_table_renders_rows_and_escapes_pipes():
    table = report.to_table([{"reason": "a|b", "jobs": "2"}])

    assert table.splitlines()[0] == "| reason | jobs |"
    assert table.splitlines()[1] == "| --- | --- |"
    assert "a\\|b" in table


def test_an_empty_result_says_so_instead_of_an_empty_table():
    assert "No data" in report.to_table([])


def test_report_has_one_section_per_query_and_states_the_window():
    results = {q.title: [{"jobs": "1"}] for q in report.QUERIES}

    text = report.render_report(
        results, hours=24, region="us-east-1", prefix="invoice-extraction-prod"
    )

    assert text.startswith("# ")
    assert text.count("\n## ") == len(report.QUERIES)
    assert "last 24 hours" in text
    assert text.endswith("\n")


def test_every_field_the_queries_use_is_emitted_by_the_app():
    job = to_record(
        JobEvent(
            outcome="failed_validation",
            duration_ms=1.0,
            prompt_version="v",
            reason="output_rejected",
            job_id="j1",
            grounding_rate=1.0,
        )
    )
    llm = to_record(
        LlmCallEvent(
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
    )
    emitted = {"job": set(job), "llm_call": set(llm)}

    for query in report.QUERIES:
        if query.event:
            assert set(query.fields) <= emitted[query.event], query.title


def test_no_stat_is_aliased_to_the_name_of_the_field_it_aggregates():
    """`sum(x) as x` makes Insights return null for the column; it must read a distinct name."""
    import re

    for query in report.QUERIES:
        for func, field, alias in re.findall(r"(\w+)\((\w+)\) as (\w+)", query.text):
            assert field != alias, f"{query.title}: {func}({field}) as {alias}"
