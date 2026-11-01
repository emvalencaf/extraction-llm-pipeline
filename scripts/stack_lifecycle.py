# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Job lifecycle scenarios against the running local stack (`make stack-up` first).

Idempotency, JSON 403/429, a poison message that ends in the DLQ with the job `failed`, and
a redrive that then completes it. Failures are injected only through fake-gemini.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8080"
FAKE = "http://localhost:8001"
KEY = os.environ.get("API_KEY", "local-dev-key")

sys.path.insert(0, os.path.dirname(__file__))
from stack_smoke import minimal_pdf  # noqa: E402


def call(url, method="GET", data=None, headers=None):
    headers = dict(headers or {})
    if url.startswith(API):
        headers.setdefault("x-api-key", KEY)
    if isinstance(data, bytes):
        headers["Content-Type"] = "application/pdf"
    elif data is not None:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def post_job(headers=None):
    time.sleep(1.1)  # stay under the 1 req/s usage plan
    status, _, body = call(f"{API}/jobs", "POST", headers=headers)
    return status, json.loads(body)


def status_of(job_id):
    return json.loads(call(f"{API}/jobs/{job_id}")[2])["status"]


def wait_for(job_id, wanted, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if status_of(job_id) in wanted:
            return status_of(job_id)
        time.sleep(1)
    raise SystemExit(f"timed out waiting for {wanted}, job is {status_of(job_id)}")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not ok:
        sys.exit(1)


def main() -> None:
    call(f"{FAKE}/control/fail", "DELETE")

    key = {"Idempotency-Key": f"demo-{int(time.time())}"}
    first_status, first = post_job(key)
    second_status, second = post_job(key)
    check(
        "repeated Idempotency-Key returns the same job",
        (first_status, second_status) == (201, 200) and first["job_id"] == second["job_id"],
    )

    status, headers, body = call(f"{API}/jobs", "POST", headers={"x-api-key": "wrong"})
    check(
        "bad API key is a JSON 403",
        status == 403
        and headers["content-type"] == "application/json"
        and "message" in json.loads(body),
    )

    time.sleep(2)
    codes = [call(f"{API}/jobs", "POST")[0] for _ in range(6)]
    status, headers, body = call(f"{API}/jobs", "POST")
    check(
        "burst past the usage plan is a JSON 429",
        429 in codes and status == 429 and "message" in json.loads(body),
        str(codes),
    )

    print("poison message: making the model unavailable", flush=True)
    call(f"{FAKE}/control/fail", "PUT", {"status": 503})
    _, job = post_job()
    call(job["upload_url"], "PUT", minimal_pdf())
    final = wait_for(job["job_id"], {"failed"})
    check("poison job is marked failed on the last receive", final == "failed")

    print("redrive: model recovered, replaying the DLQ", flush=True)
    call(f"{FAKE}/control/fail", "DELETE")
    # The queue moves the message to the DLQ on the receive after the 5th, once the 15 s
    # visibility timeout lapses.
    time.sleep(20)
    subprocess.run(["make", "redrive"], check=True)
    final = wait_for(job["job_id"], {"succeeded", "failed", "failed_validation"})
    check("redriven job succeeds", final == "succeeded", final)
    print("all lifecycle scenarios passed")


if __name__ == "__main__":
    main()
