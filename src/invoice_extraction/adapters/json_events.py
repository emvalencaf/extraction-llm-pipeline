"""EventSink writing one JSON object per line, with CloudWatch EMF metrics embedded.

In Lambda, stdout lines go to CloudWatch Logs; a line carrying an `_aws` block is also
read as Embedded Metric Format. Metrics have no dimensions (free tier): `Dimensions`
is a single empty set, so each metric is one account-wide series.
"""

import json
import sys
import time
from dataclasses import asdict
from typing import Any, TextIO

from invoice_extraction.application.observability import LlmCallEvent, WideEvent
from invoice_extraction.domain.status import JobStatus

NAMESPACE = "InvoiceExtraction"
_NOT_INFRA_FAILURE = {JobStatus.SUCCEEDED, JobStatus.FAILED_VALIDATION}


def _metrics(event: WideEvent) -> dict[str, tuple[str, float | None]]:
    """Metric name -> (EMF unit, value); a None value is skipped."""
    if isinstance(event, LlmCallEvent):
        return {
            "LlmLatencyMs": ("Milliseconds", event.latency_ms),
            "LlmInputTokens": ("Count", event.input_tokens),
            "LlmOutputTokens": ("Count", event.output_tokens),
            "LlmCallError": ("Count", 0 if event.outcome == "ok" else 1),
        }
    return {
        "JobSucceeded": ("Count", 1 if event.outcome == "succeeded" else 0),
        "JobFailed": ("Count", 0 if event.outcome == "succeeded" else 1),
        # Outages only: a failed_validation (bad document) is a business outcome, not a page.
        "JobInfraFailed": ("Count", 0 if event.outcome in _NOT_INFRA_FAILURE else 1),
        "JobDurationMs": ("Milliseconds", event.duration_ms),
        "GroundingRate": ("None", event.grounding_rate),
    }


def to_record(event: WideEvent, now_ms: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event": "llm_call" if isinstance(event, LlmCallEvent) else "job",
        **{k: v for k, v in asdict(event).items() if v is not None},
    }
    metrics = {k: v for k, v in _metrics(event).items() if v[1] is not None}
    for name, (_, value) in metrics.items():
        record[name] = value
    record["_aws"] = {
        "Timestamp": now_ms if now_ms is not None else int(time.time() * 1000),
        "CloudWatchMetrics": [
            {
                "Namespace": NAMESPACE,
                "Dimensions": [[]],
                "Metrics": [{"Name": n, "Unit": unit} for n, (unit, _) in metrics.items()],
            }
        ],
    }
    return record


class JsonEventSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def emit(self, event: WideEvent) -> None:
        try:
            self._stream.write(json.dumps(to_record(event), separators=(",", ":")) + "\n")
            self._stream.flush()
        except (OSError, ValueError, TypeError):
            pass  # logging must never fail a job
