"""`stack_client.worker_events` orders the workers' wide events by emit time."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stack_client


def _line(worker: str, event: str, timestamp: int, job_id: str = "j1") -> str:
    record = {"event": event, "job_id": job_id, "_aws": {"Timestamp": timestamp}}
    return f"{worker}  | {json.dumps(record)}"


def test_worker_events_are_ordered_by_emit_time_across_workers(monkeypatch):
    # `compose logs` prints all of worker-1's lines before worker-2's.
    logs = "\n".join(
        [
            _line("worker-1", "job", 300),
            _line("worker-1", "llm_call", 100),
            _line("worker-2", "llm_call", 200),
            _line("worker-2", "job", 400, job_id="other"),
            'worker-2  | "event" not json {',
        ]
    )
    monkeypatch.setattr(stack_client, "compose_command", lambda: ["compose"])
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=logs),
    )

    events = stack_client.worker_events("j1")

    assert [(e["event"], e["_aws"]["Timestamp"]) for e in events] == [
        ("llm_call", 100),
        ("llm_call", 200),
        ("job", 300),
    ]
