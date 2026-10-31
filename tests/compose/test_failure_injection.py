"""The 11 failure-injection scenarios (#23) against the local compose stack.

Each scenario injects its fault through fake-gemini (model-targeted rules, plus `crash`) or
an environment variable of the stack (compressed timings in compose.yaml), never through
test hooks in the Lambda code. Each asserts the final job status and the wide events.
Scenarios 4 and 5 share one exhausted job; scenario 9 is last because it leaves the
workers restarting after a Lambda timeout.
"""

import time

import pytest
import stack_client as stack

GOOD_REPLY_BROKEN = {"invoice_no": "51109301"}  # valid JSON, but most required fields are missing


def outcomes(job_id):
    return [(e["model"], e["outcome"]) for e in stack.llm_calls(job_id)]


def test_1_transient_errors_on_the_primary_are_retried_and_the_job_succeeds():
    stack.inject("error", status=429, model=stack.PRIMARY, times=2)

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "succeeded"
    assert outcomes(job_id) == [
        (stack.PRIMARY, "transient_error"),
        (stack.PRIMARY, "transient_error"),
        (stack.PRIMARY, "ok"),
    ]
    (event,) = stack.job_events(job_id)
    assert (event["outcome"], event["fell_back"], event["model"]) == (
        "succeeded",
        False,
        stack.PRIMARY,
    )


def test_2_an_exhausted_primary_falls_back_to_the_second_model():
    stack.inject("error", status=503, model=stack.PRIMARY)

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "succeeded"
    assert outcomes(job_id)[-1] == (stack.FALLBACK, "ok")
    assert {m for m, o in outcomes(job_id) if o == "transient_error"} == {stack.PRIMARY}
    (event,) = stack.job_events(job_id)
    assert (event["fell_back"], event["model"]) == (True, stack.FALLBACK)


def test_3a_an_invalid_reply_is_repaired_once_and_the_job_succeeds():
    stack.inject("reply", reply=GOOD_REPLY_BROKEN, times=1)

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "succeeded"
    calls = stack.llm_calls(job_id)
    assert [c["repair"] for c in calls] == [False, True]
    (event,) = stack.job_events(job_id)
    assert (event["repairs"], event["escalated"]) == (1, False)


def test_3b_a_failed_repair_ends_failed_validation_without_the_dlq():
    dlq_before = stack.queue_depth("jobs-dlq")
    stack.inject("reply", reply=GOOD_REPLY_BROKEN)

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "failed_validation"
    assert job["reason"] == "schema_invalid"
    assert job["errors"]  # the validation errors of the last attempt
    # The best attempt itself is not preserved: a failed_validation result carries only the
    # errors (PipelineResult.extraction is None and the job record has no field for a partial
    # extraction), so the API has nothing to expose. Only the absence can be asserted.
    assert "result" not in job
    (event,) = stack.job_events(job_id)
    assert (event["outcome"], event["repairs"], event["escalated"]) == (
        "failed_validation",
        4,  # two repairs on the primary tier, then two more after escalating
        True,
    )
    stack.wait_for_depth("jobs", 0)
    assert stack.queue_depth("jobs-dlq") == dlq_before


@pytest.fixture(scope="module")
def exhausted_job():
    """Scenario 4's job: every model out of quota until the message reaches the DLQ."""
    dlq_before = stack.queue_depth("jobs-dlq")
    stack.clear_injections()
    stack.inject("error", status=429)
    job_id = stack.submit()
    job = stack.wait_for(job_id, {"failed"}, timeout=120)
    stack.wait_for_depth("jobs-dlq", dlq_before + 1, timeout=120)
    stack.clear_injections()  # quota recovered
    return job_id, job


def test_4_quota_exhaustion_backs_off_then_dead_letters_with_the_job_failed(exhausted_job):
    job_id, job = exhausted_job

    assert job["status"] == "failed"
    assert job["errors"] == ["retries_exhausted"]
    receives = stack.job_events(job_id)
    assert [e["outcome"] for e in receives] == ["unavailable"] * 5  # MAX_RECEIVES
    assert all(e["llm_calls"] == 6 for e in receives)  # 3 attempts on each of 2 models
    assert stack.queue_depth("jobs") == 0


def test_5_redriving_the_dlq_after_recovery_completes_the_job(exhausted_job):
    job_id, _ = exhausted_job

    stack.redrive()
    job = stack.wait_for(job_id, {"succeeded"}, timeout=120)

    assert job["result"]["invoice_no"] == "51109301"
    stack.wait_for_depth("jobs-dlq", 0, timeout=60)
    assert stack.job_events(job_id)[-1]["outcome"] == "succeeded"


def test_6_redelivery_of_a_finished_job_is_dropped():
    job_id = stack.submit()
    first = stack.wait_for(job_id, {"succeeded"})
    calls_before = len(stack.model_calls())
    events_before = len(stack.worker_events(job_id))

    stack.redeliver(job_id)
    stack.wait_for_depth("jobs", 0, timeout=30)
    time.sleep(2)  # let a late handler finish if it would write

    assert stack.get_job(job_id) == first
    assert len(stack.model_calls()) == calls_before  # no second LLM call
    assert len(stack.worker_events(job_id)) == events_before  # nothing else was processed


def test_7_the_same_idempotency_key_returns_the_same_job():
    key = f"scenario-7-{time.time_ns()}"

    first_status, first = stack.post_job(key)
    second_status, second = stack.post_job(key)

    assert (first_status, second_status) == (201, 200)
    assert second["job_id"] == first["job_id"]


def test_8_a_job_whose_upload_never_arrives_expires():
    _, job = stack.post_job()  # UPLOAD_TTL_SECONDS is 20 in the stack

    assert stack.get_job(job["job_id"])["status"] == "awaiting_upload"
    expired = stack.wait_for(job["job_id"], {"expired"}, timeout=60)

    assert expired["status"] == "expired"
    assert "result" not in expired


def test_10_a_placeholder_violation_ends_failed_validation_without_repair():
    stack.inject("reply", patch={"seller": {"name": "[NAME_99]"}})

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "failed_validation"
    assert job["reason"] == "output_rejected"
    assert "result" not in job
    assert len(stack.llm_calls(job_id)) == 1  # a guardrail rejection is not repaired
    (event,) = stack.job_events(job_id)
    assert event["reason"] == "output_rejected"


def test_11_an_ungrounded_value_is_flagged_but_the_job_still_succeeds():
    stack.inject("reply", patch={"invoice_no": "99999999"})

    job_id = stack.submit()
    job = stack.wait_for_end(job_id)

    assert job["status"] == "succeeded"
    assert job["result"]["invoice_no"] == "99999999"
    (event,) = stack.job_events(job_id)
    assert "invoice_no" in event["ungrounded_fields"]
    assert event["grounding_rate"] < 1.0
    assert event["grounded_fields"] > 0  # the other fields are still found in the text


def test_9_a_timeout_on_the_last_receive_leaves_the_job_processing_in_the_dlq():
    """The known gap, shown on purpose: a hard Lambda timeout cannot be caught, so the job
    stays `processing` while its message goes to the DLQ."""
    dlq_before = stack.queue_depth("jobs-dlq")
    stack.inject("crash", hang_seconds=60)  # outlives the 12 s Lambda timeout

    job_id = stack.submit()
    stack.wait_for_depth("jobs-dlq", dlq_before + 1, timeout=240)

    assert stack.get_job(job_id)["status"] == "processing"
    assert stack.queue_depth("jobs") == 0
