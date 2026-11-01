# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3"]
# ///
"""Markdown report of the deployed pipeline, from CloudWatch Logs Insights queries.

    uv run scripts/insights_report.py [--hours 24] [--output report.md]

Runs the queries below against the API and worker log groups of the stack, through boto3
and the AWS credentials in the environment, and renders the answers as Markdown. The queries
read the two wide events the app logs (`job` and `llm_call`), which hold counts, timings and
labels only, never invoice content, so the report is safe to share.
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLL_SECONDS = 1.0
MAX_POLLS = 300  # five minutes at one poll per second


@dataclass(frozen=True)
class Query:
    title: str
    text: str
    description: str
    function: str = "worker"  # which Lambda's log group to search
    event: str | None = None  # wide event the query reads, to check its fields exist
    fields: tuple[str, ...] = ()


QUERIES: tuple[Query, ...] = (
    Query(
        "Jobs by outcome",
        'filter event = "job" | stats count() as jobs by outcome | sort jobs desc',
        "How every processed job ended (`unavailable` and `error` are infrastructure failures).",
        event="job",
        fields=("outcome",),
    ),
    Query(
        "Job duration",
        'filter event = "job" | stats count() as jobs, avg(duration_ms) as avg_ms, '
        "pct(duration_ms, 50) as p50_ms, pct(duration_ms, 95) as p95_ms, "
        "max(duration_ms) as max_ms",
        "End-to-end time of a job inside the worker, in milliseconds.",
        event="job",
        fields=("duration_ms",),
    ),
    Query(
        "Failure reasons",
        'filter event = "job" and outcome != "succeeded" '
        "| stats count() as jobs by outcome, reason | sort jobs desc",
        "Why jobs did not succeed. A `failed_validation` is a bad document, not an outage.",
        event="job",
        fields=("outcome", "reason"),
    ),
    Query(
        "Model calls by model and outcome",
        'filter event = "llm_call" | stats count() as calls, avg(latency_ms) as avg_ms, '
        "pct(latency_ms, 95) as p95_ms by model, tier, outcome | sort calls desc",
        "Every Gemini call. `rejected` and `transient_error` feed the fallback and the retries.",
        event="llm_call",
        fields=("model", "tier", "outcome", "latency_ms"),
    ),
    Query(
        "Token usage",
        'filter event = "llm_call" | stats sum(input_tokens) as tokens_in, '
        "sum(output_tokens) as tokens_out, count() as calls by model | sort calls desc",
        "Tokens sent to and returned by each model, for cost tracking.",
        event="llm_call",
        fields=("input_tokens", "output_tokens", "model"),
    ),
    Query(
        "Repairs, fallback and escalation",
        'filter event = "job" | stats count() as jobs, sum(llm_calls) as total_llm_calls, '
        "sum(repairs) as total_repairs by fell_back, escalated | sort jobs desc",
        "How often the graph repaired a response, fell back to the second model or escalated.",
        event="job",
        fields=("llm_calls", "repairs", "fell_back", "escalated"),
    ),
    Query(
        "Grounding Rate",
        'filter event = "job" and ispresent(grounding_rate) | stats count() as jobs, '
        "avg(grounding_rate) as avg_rate, min(grounding_rate) as min_rate",
        "Share of extracted fields found in the document text. Informational; never blocks.",
        event="job",
        fields=("grounding_rate",),
    ),
    Query(
        "Jobs per hour",
        'filter event = "job" | stats count() as jobs, sum(JobSucceeded) as succeeded, '
        "sum(JobFailed) as failed, sum(JobInfraFailed) as infra_failed by bin(1h) as hour "
        "| sort hour desc",
        "Throughput and failures over time.",
        event="job",
        fields=("JobSucceeded", "JobFailed", "JobInfraFailed"),
    ),
    Query(
        "Slowest jobs",
        'filter event = "job" | fields job_id, outcome, duration_ms, llm_calls '
        "| sort duration_ms desc | limit 5",
        "The five slowest jobs, to look up by id in the logs.",
        event="job",
        fields=("job_id", "outcome", "duration_ms", "llm_calls"),
    ),
    Query(
        "Worker invocations",
        'filter @type = "REPORT" | stats count() as invocations, avg(@duration) as avg_ms, '
        "max(@duration) as max_ms, max(@maxMemoryUsed / 1024 / 1024) as max_memory_mb, "
        "count(@initDuration) as cold_starts, avg(@initDuration) as avg_cold_start_ms",
        "Lambda REPORT lines of the worker: duration, memory and cold starts.",
    ),
    Query(
        "API invocations",
        'filter @type = "REPORT" | stats count() as invocations, avg(@duration) as avg_ms, '
        "max(@duration) as max_ms, max(@maxMemoryUsed / 1024 / 1024) as max_memory_mb, "
        "count(@initDuration) as cold_starts, avg(@initDuration) as avg_cold_start_ms",
        "Lambda REPORT lines of the API. A max near 29000 ms means API Gateway timeouts.",
        function="api",
    ),
    Query(
        "Timeouts and errors",
        "filter @message like /Task timed out|Status: timeout|Traceback|ERROR/ "
        "| stats count() as occurrences by bin(1h) as hour | sort hour desc",
        "Lambda timeouts and logged errors in the worker, per hour.",
    ),
)


def run_query(
    logs: Any,
    log_groups: list[str],
    text: str,
    start: int,
    end: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    max_polls: int = MAX_POLLS,
) -> list[dict[str, str]]:
    """Run one Insights query to completion and return its rows as dicts."""
    query_id = logs.start_query(
        logGroupNames=log_groups, startTime=start, endTime=end, queryString=text
    )["queryId"]
    for _ in range(max_polls):
        answer = logs.get_query_results(queryId=query_id)
        status = answer["status"]
        if status == "Complete":
            return [
                {c["field"]: c["value"] for c in row if c["field"] != "@ptr"}
                for row in answer["results"]
            ]
        if status in {"Failed", "Cancelled", "Timeout"}:
            raise RuntimeError(f"Insights query {status}: {text}")
        sleep(POLL_SECONDS)
    raise RuntimeError(f"Insights query did not finish: {text}")


def to_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_No data in this window._"
    columns = list(rows[0])
    for row in rows:
        columns += [c for c in row if c not in columns]

    def fmt(value: str) -> str:
        return _round(value).replace("|", "\\|")

    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines += ["| " + " | ".join(fmt(row.get(c, "")) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def _round(value: str) -> str:
    """Trim long floats from Insights (`1234.56789`) to two decimals; leave other text alone."""
    try:
        number = float(value)
    except ValueError:
        return value
    return value if number.is_integer() and "." not in value else f"{number:.2f}"


def render_report(
    results: dict[str, list[dict[str, str]]], *, hours: int, region: str, prefix: str
) -> str:
    parts = [
        "# Pipeline report",
        "",
        f"Stack `{prefix}` in `{region}`, last {hours} hours, from CloudWatch Logs Insights.",
        "",
    ]
    for query in QUERIES:
        parts += [
            f"## {query.title}",
            "",
            query.description,
            "",
            to_table(results[query.title]),
            "",
        ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=int, default=24, help="window size (default 24)")
    parser.add_argument("--prefix", default="invoice-extraction-prod", help="stack name prefix")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--output", type=Path, help="write here instead of stdout")
    args = parser.parse_args(argv)

    import boto3  # imported late so the pure functions need no AWS setup

    logs = boto3.client("logs", region_name=args.region)
    groups = {name: f"/aws/lambda/{args.prefix}-{name}" for name in ("api", "worker")}
    end = int(time.time())
    start = end - args.hours * 3600
    results: dict[str, list[dict[str, str]]] = {}
    for query in QUERIES:
        print(f"running: {query.title}", file=sys.stderr)
        results[query.title] = run_query(logs, [groups[query.function]], query.text, start, end)

    text = render_report(results, hours=args.hours, region=args.region, prefix=args.prefix)
    if args.output:
        args.output.write_text(text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
