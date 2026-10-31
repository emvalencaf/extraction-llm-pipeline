# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Happy path against the running local stack: create job, presigned PUT, fetch result."""

import json
import os
import sys
import time
import urllib.request

API = "http://localhost:8080"


def call(url: str, method: str = "GET", data: bytes | None = None) -> bytes:
    headers = {"Content-Type": "application/pdf"} if data else {}
    if url.startswith(API):
        headers["x-api-key"] = os.environ.get("API_KEY", "local-dev-key")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


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
    job = json.loads(call(f"{API}/jobs", "POST"))
    print("created", job["job_id"], job["status"])
    call(job["upload_url"], "PUT", minimal_pdf())
    print("uploaded")
    for _ in range(60):
        body = json.loads(call(f"{API}/jobs/{job['job_id']}"))
        if body["status"] not in {"awaiting_upload", "queued", "processing"}:
            print(json.dumps(body, indent=2))
            return 0 if body["status"] == "succeeded" else 1
        time.sleep(1)
    print("timed out waiting for the job")
    return 1


if __name__ == "__main__":
    sys.exit(main())
