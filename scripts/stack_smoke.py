# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Happy path against a running stack: create job, presigned PUT, fetch result.

Local by default. For a deployed stack set API_URL, API_KEY and optionally SMOKE_TIMEOUT_S.
Set SMOKE_ACCEPT_VALIDATION_FAILURE=1 against the real model: the one-line PDF below makes it
invent a seller and client, so the output is rejected as `failed_validation`. That still proves
upload, queue, worker, model call and validation all ran; extraction quality is the gate's job.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8080").rstrip("/")


def call(url: str, method: str = "GET", data: bytes | None = None) -> bytes:
    headers = {"Content-Type": "application/pdf"} if data else {}
    if url.startswith(API):
        headers["x-api-key"] = os.environ.get("API_KEY", "local-dev-key")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def create_job() -> dict:
    """POST /jobs, retrying 403: a fresh API key takes a while to reach its usage plan."""
    deadline = time.monotonic() + int(os.environ.get("SMOKE_TIMEOUT_S", "60"))
    while True:
        try:
            return json.loads(call(f"{API}/jobs", "POST"))
        except urllib.error.HTTPError as error:
            if error.code != 403 or time.monotonic() >= deadline:
                raise
            print("403 from the API (key not propagated yet?), retrying in 5 s")
            time.sleep(5)


def minimal_pdf() -> bytes:
    stream = b"BT /F1 10 Tf 40 800 Td (Invoice no: 51109301) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def main() -> int:
    job = create_job()
    print("created", job["job_id"], job["status"])
    call(job["upload_url"], "PUT", minimal_pdf())
    print("uploaded")
    for _ in range(int(os.environ.get("SMOKE_TIMEOUT_S", "60"))):
        body = json.loads(call(f"{API}/jobs/{job['job_id']}"))
        if body["status"] not in {"awaiting_upload", "queued", "processing"}:
            print(json.dumps(body, indent=2))
            accepted = {"succeeded"}
            if os.environ.get("SMOKE_ACCEPT_VALIDATION_FAILURE") == "1":
                accepted.add("failed_validation")
            return 0 if body["status"] in accepted else 1
        time.sleep(1)
    print("timed out waiting for the job")
    return 1


if __name__ == "__main__":
    sys.exit(main())
