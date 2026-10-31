# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Watch the pipeline survive injected failures (`make demo-resilience`, stack must be up).

Runs failure-injection scenarios 1, 2, 4 and 5 in order and prints, for each, a timeline of
the job's state transitions, its `llm_call` and `job` wide events and the DLQ depth. The
faults are injected through fake-gemini only; timings are compressed in compose.yaml.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_client as stack

BAR = "=" * 78


class Timeline:
    def __init__(self) -> None:
        self.started = time.monotonic()

    def say(self, text: str) -> None:
        print(f"  [{time.monotonic() - self.started:6.1f}s] {text}", flush=True)


def watch(job_id: str, timeline: Timeline, until: set[str], timeout: float = 150) -> dict:
    """Print every status change of the job until it reaches one of `until`."""
    last, deadline = None, time.time() + timeout
    while True:
        job = stack.get_job(job_id)
        if job["status"] != last:
            timeline.say(f"job {job_id[:8]} -> {job['status']}")
            last = job["status"]
        if job["status"] in until:
            return job
        if time.time() > deadline:
            raise SystemExit(f"timed out waiting for {sorted(until)}, job is {job['status']}")
        time.sleep(0.5)


def show_events(job_id: str, timeline: Timeline) -> None:
    for event in stack.worker_events(job_id):
        if event["event"] == "llm_call":
            timeline.say(
                f"llm_call  {event['model']:<24} {event['tier']:<10} "
                f"attempt={event['attempt']} repair={event['repair']} -> {event['outcome']}"
            )
        else:
            timeline.say(
                f"job event outcome={event['outcome']} llm_calls={event['llm_calls']} "
                f"fell_back={event['fell_back']} model={event.get('model')}"
            )


def scenario(title: str, what: str) -> Timeline:
    print(f"\n{BAR}\n{title}\n  injected: {what}\n{BAR}", flush=True)
    return Timeline()


def transient_errors() -> None:
    timeline = scenario(
        "1. Transient 429s on the primary model",
        f"{stack.PRIMARY} answers 429 twice, then recovers",
    )
    stack.inject("error", status=429, model=stack.PRIMARY, times=2)
    job_id = stack.submit()
    watch(job_id, timeline, {"succeeded", "failed", "failed_validation"})
    show_events(job_id, timeline)
    stack.clear_injections()


def fallback() -> None:
    timeline = scenario(
        "2. Primary model exhausted, fallback takes over",
        f"{stack.PRIMARY} answers 503 on every call",
    )
    stack.inject("error", status=503, model=stack.PRIMARY)
    job_id = stack.submit()
    watch(job_id, timeline, {"succeeded", "failed", "failed_validation"})
    show_events(job_id, timeline)
    stack.clear_injections()


def exhaustion_and_redrive() -> None:
    timeline = scenario(
        "4. Quota exhaustion: growing backoff, then the DLQ",
        "every model answers 429 on every call",
    )
    dlq_before = stack.queue_depth("jobs-dlq")
    stack.inject("error", status=429)
    job_id = stack.submit()
    watch(job_id, timeline, {"failed"})
    stack.wait_for_depth("jobs-dlq", dlq_before + 1, timeout=120)
    timeline.say(f"DLQ depth {dlq_before} -> {stack.queue_depth('jobs-dlq')}")
    receives = stack.job_events(job_id)
    timeline.say(f"{len(receives)} receives, every one ended 'unavailable'; job marked failed")

    print(f"\n{BAR}\n5. Redrive after recovery\n  injected: nothing, the quota is back\n{BAR}")
    timeline = Timeline()
    stack.clear_injections()
    stack.redrive()
    timeline.say("replayed the DLQ with native SQS redrive")
    watch(job_id, timeline, {"succeeded", "failed", "failed_validation"})
    stack.wait_for_depth("jobs-dlq", 0, timeout=60)  # redrive replays the whole DLQ
    timeline.say(f"DLQ depth back to {stack.queue_depth('jobs-dlq')}")
    stack.clear_injections()


def main() -> int:
    print("waiting for the stack and warming the workers ...", flush=True)
    stack.wait_until_up()
    stack.clear_injections()
    for job_id in [stack.submit(), stack.submit()]:
        stack.wait_for(job_id, {"succeeded"}, timeout=180)
    transient_errors()
    fallback()
    exhaustion_and_redrive()
    print(f"\n{BAR}\nall resilience scenarios ended as designed\n{BAR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
