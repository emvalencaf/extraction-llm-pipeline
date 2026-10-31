"""Job lifecycle use cases: create, fetch, and process an uploaded invoice."""

import uuid
from collections.abc import Callable
from typing import Any

from invoice_extraction.application.pipeline import PipelineResult
from invoice_extraction.application.ports import BlobStore, JobRepository
from invoice_extraction.domain.status import JobStatus


def upload_key(job_id: str) -> str:
    return f"uploads/{job_id}.pdf"


def job_id_from_key(key: str) -> str:
    return key.rsplit("/", 1)[-1].removesuffix(".pdf")


class JobService:
    def __init__(
        self,
        jobs: JobRepository,
        blobs: BlobStore,
        extract: Callable[[bytes], PipelineResult],
    ) -> None:
        self._jobs = jobs
        self._blobs = blobs
        self._extract = extract

    def create(self) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        key = upload_key(job_id)
        self._jobs.create({"job_id": job_id, "status": JobStatus.AWAITING_UPLOAD, "key": key})
        return {
            "job_id": job_id,
            "status": JobStatus.AWAITING_UPLOAD,
            "upload_url": self._blobs.presign_put(key),
        }

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        view = {"job_id": job["job_id"], "status": job["status"]}
        if "result" in job:
            view["result"] = job["result"]
        if job.get("errors"):
            view["errors"] = job["errors"]
        return view

    def process(self, job_id: str) -> None:
        """Run the pipeline for an uploaded PDF. Raises if the PDF cannot be fetched."""
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"unknown job {job_id}")
        pdf = self._blobs.get(job["key"])
        self._jobs.update(job_id, status=JobStatus.PROCESSING)
        result = self._extract(pdf)
        fields: dict[str, Any] = {"status": result.status, "errors": result.errors}
        if result.extraction is not None:
            fields["result"] = result.extraction.model_dump(mode="json")
        self._jobs.update(job_id, **fields)
