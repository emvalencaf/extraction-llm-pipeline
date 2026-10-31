"""Job lifecycle use cases: create, fetch, and process an uploaded invoice.

Every status change goes through `JobRepository.transition`, a conditional write checked
against the domain transition table, so duplicate deliveries cannot corrupt a job.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from invoice_extraction.application.pipeline import PipelineResult
from invoice_extraction.application.ports import (
    BlobStore,
    JobRepository,
)
from invoice_extraction.domain.job import Job, JobUpdate
from invoice_extraction.domain.status import (
    MAX_PDF_BYTES,
    RETRIES_EXHAUSTED,
    UPLOAD_TTL_SECONDS,
    IllegalTransitionError,
    JobStatus,
    RetryPolicy,
    TerminalReason,
    claim_for,
)

logger = logging.getLogger(__name__)


def upload_key(job_id: str) -> str:
    return f"uploads/{job_id}.pdf"


def job_id_from_key(key: str) -> str:
    return key.rsplit("/", 1)[-1].removesuffix(".pdf")


class RetryLaterError(Exception):
    """The delivery failed for an infrastructure reason; hide the message for `delay` seconds."""

    def __init__(self, delay: int) -> None:
        super().__init__(f"retry in {delay}s")
        self.delay = delay


class JobService:
    def __init__(
        self,
        jobs: JobRepository,
        blobs: BlobStore,
        extract: Callable[..., PipelineResult],
        *,
        clock: Callable[[], float] = time.time,
        upload_ttl: int = UPLOAD_TTL_SECONDS,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._jobs = jobs
        self._blobs = blobs
        self._extract = extract
        self._clock = clock
        self._upload_ttl = upload_ttl
        self._retry = retry or RetryPolicy()

    def create(self, idempotency_key: str | None = None) -> dict[str, Any]:
        """Create a job and its upload URL. A repeated Idempotency-Key returns the first job
        (marked `replayed`)."""
        job_id = uuid.uuid4().hex
        key = upload_key(job_id)
        self._jobs.create(
            Job(
                job_id=job_id,
                status=JobStatus.AWAITING_UPLOAD,
                key=key,
                created_at=int(self._clock()),
            )
        )
        if idempotency_key is not None:
            winner = self._jobs.claim_idempotency_key(idempotency_key, job_id)
            if winner != job_id:
                self._jobs.discard(job_id)
                existing = self._jobs.get(winner)
                if existing is None:  # cannot happen: the job is written before its key
                    raise LookupError(f"idempotency key points at missing job {winner}")
                existing = self._expire_if_due(existing)
                view = {**self._view(existing), "replayed": True}
                if existing.status == JobStatus.AWAITING_UPLOAD:
                    view["upload_url"] = self._blobs.presign_put(existing.key)
                return view
        return {
            "job_id": job_id,
            "status": JobStatus.AWAITING_UPLOAD,
            "upload_url": self._blobs.presign_put(key),
        }

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return self._view(self._expire_if_due(job))

    @staticmethod
    def _view(job: Job) -> dict[str, Any]:
        view: dict[str, Any] = {"job_id": job.job_id, "status": job.status}
        if job.result is not None:
            view["result"] = job.result
        if job.errors:
            view["errors"] = job.errors
        if job.reason:
            view["reason"] = job.reason
        return view

    def _expire_if_due(self, job: Job) -> Job:
        """An upload that never arrived turns the job `expired` (a conditional write)."""
        if job.status != JobStatus.AWAITING_UPLOAD:
            return job
        if self._clock() - job.created_at <= self._upload_ttl:
            return job
        try:
            self._jobs.transition(
                job.job_id, JobStatus.EXPIRED, expected={JobStatus.AWAITING_UPLOAD}
            )
        except IllegalTransitionError:  # the upload won the race; show the current state
            return self._jobs.get(job.job_id) or job
        return replace(job, status=JobStatus.EXPIRED)

    def process(self, job_id: str, receive_count: int = 1) -> None:
        """Handle one delivery of an uploaded PDF.

        Returns normally when the delivery is done (including duplicates and jobs that no
        longer accept work). Raises RetryLaterError for a transient infrastructure failure and
        any other exception for a failure to retry. Any exception hides the message for a
        growing delay; on the last receive the job is marked `failed` first, because the queue
        is about to move the message to the DLQ. (A hard Lambda timeout cannot be caught, so
        a job that times out on its last receive stays `processing`.)
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"unknown job {job_id}")
        job = self._expire_if_due(job)
        if not self._claim(job):
            return
        try:
            result = self._run(job)
        except Exception as error:
            self._on_error(job_id, receive_count, error)
            raise
        if result is not None:
            self._finish(job_id, result)

    def _claim(self, job: Job) -> bool:
        claim = claim_for(job.status)
        if claim is None:
            return False
        reset = JobUpdate(errors=[], failure_cause="") if claim.reset else None
        try:
            self._jobs.transition(
                job.job_id,
                JobStatus.PROCESSING,
                expected=claim.expected,
                requires=claim.requires,
                update=reset,
            )
        except IllegalTransitionError:
            logger.info("claim skipped job_id=%s", job.job_id)
            return False  # a duplicate delivery, or a business failure: nothing to do
        return True

    def _run(self, job: Job) -> PipelineResult | None:
        """Fetch and extract. Returns None when the job was already finished here."""
        key = job.key
        # Worker-side check backing the presigned PUT, which cannot cap the upload size.
        if self._blobs.size(key) > MAX_PDF_BYTES:
            self._finish(
                job.job_id,
                PipelineResult(
                    JobStatus.FAILED,
                    errors=[f"PDF exceeds {MAX_PDF_BYTES} bytes"],
                    reason=TerminalReason.PDF_TOO_LARGE,
                ),
            )
            return None
        return self._extract(self._blobs.get(key), job.job_id)

    def _finish(self, job_id: str, result: PipelineResult) -> None:
        update = JobUpdate(
            errors=result.errors,
            reason=None if result.reason is None else str(result.reason),
            result=(
                None if result.extraction is None else result.extraction.model_dump(mode="json")
            ),
        )
        self._jobs.transition(job_id, result.status, expected={JobStatus.PROCESSING}, update=update)

    def _on_error(self, job_id: str, receive_count: int, error: Exception) -> None:
        try:
            if self._retry.is_last(receive_count):
                self._jobs.transition(
                    job_id,
                    JobStatus.FAILED,
                    expected={JobStatus.PROCESSING},
                    update=JobUpdate(failure_cause=RETRIES_EXHAUSTED, errors=[RETRIES_EXHAUSTED]),
                )
                return
            self._jobs.transition(job_id, JobStatus.QUEUED, expected={JobStatus.PROCESSING})
        except IllegalTransitionError:
            logger.info("error handling skipped, job moved on job_id=%s", job_id)
            return
        raise RetryLaterError(self._retry.delay(receive_count)) from error
