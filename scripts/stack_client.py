"""Client for the running local stack, shared by the failure-injection tests and the demo.

Standard library only. It drives the stack the way a caller does (HTTP API, presigned PUT)
and reads what the operator reads: the queue depth from ElasticMQ and the wide events the
workers print. Failures are injected through the fake-gemini control endpoint only.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("STACK_API_URL", "http://localhost:8080")
FAKE = os.environ.get("STACK_FAKE_GEMINI_URL", "http://localhost:8001")
SQS = os.environ.get("STACK_SQS_URL", "http://localhost:9324")
KEY = os.environ.get("API_KEY", "local-dev-key")
QUEUE_PREFIX = f"{SQS}/000000000000"  # ElasticMQ's fixed account id

# Model names from the Prompt Bundle (src/invoice_extraction/prompts/settings.json).
PRIMARY = "gemini-3.5-flash-lite"
FALLBACK = "gemini-3.1-flash-lite"
ESCALATION = "gemini-3.8-flash"

IN_PROGRESS = {"awaiting_upload", "queued", "processing"}

sys.path.insert(0, str(ROOT / "tests"))
from support.pdf import make_pdf  # noqa: E402


def invoice_pdf() -> bytes:
    """A text-native invoice whose values match fake-gemini's default reply."""
    return make_pdf(
        [
            "Invoice no: 51109301",
            "Date of issue: 03/07/2023",
            "Seller: TechVision Distributors Pvt Ltd, 1 Main Street, Mumbai",
            "Tax Id: 27AAAAA0000A1Z5",
            "Client: Jane Roe, 2 Side Road, Delhi",
            "Tax Id: 901-95-4704",
            "Widget 9.00 pcs 74,120.00 667,080.00 10% 733,788.00",
            "Total net 667,080.00 VAT 10% 66,708.00 gross 733,788.00 INR",
        ]
    )


def call(url, method="GET", data=None, headers=None, timeout=30):
    """One HTTP call. Returns (status, headers, body bytes); HTTP errors are not raised."""
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def compose_command() -> list[str]:
    """`docker compose` (v2 plugin) when present, else the standalone docker-compose."""
    plugin = subprocess.run(["docker", "compose", "version"], capture_output=True, check=False)
    if plugin.returncode == 0:
        return ["docker", "compose"]
    return [shutil.which("docker-compose") or "docker-compose"]


# --- fake-gemini -----------------------------------------------------------------------


def inject(mode, **rule):
    """Add a fake-gemini scenario rule: `inject("error", status=429, model=PRIMARY, times=2)`."""
    call(f"{FAKE}/control/scenario", "POST", {"mode": mode, **rule})


def clear_injections():
    call(f"{FAKE}/control/scenario", "DELETE")


def model_calls():
    """Every call fake-gemini has seen since the last clear, as [{model, outcome}]."""
    return json.loads(call(f"{FAKE}/control/calls")[2])


# --- jobs ------------------------------------------------------------------------------


def post_job(idempotency_key=None):
    """POST /jobs, spaced to stay under the 1 req/s usage plan. Returns (status, body)."""
    time.sleep(1.1)
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    status, _, body = call(f"{API}/jobs", "POST", headers=headers)
    return status, json.loads(body)


def upload(job, pdf=None):
    call(job["upload_url"], "PUT", pdf or invoice_pdf())


def submit(pdf=None):
    """Create a job and upload a PDF for it. Returns the job id."""
    _, job = post_job()
    upload(job, pdf)
    return job["job_id"]


def get_job(job_id):
    return json.loads(call(f"{API}/jobs/{job_id}")[2])


def wait_for(job_id, wanted, timeout=120):
    """Poll until the job's status is in `wanted`. Returns the job body."""
    deadline = time.time() + timeout
    while True:
        body = get_job(job_id)
        if body["status"] in wanted:
            return body
        if time.time() > deadline:
            raise TimeoutError(f"job {job_id} is {body['status']}, wanted {sorted(wanted)}")
        time.sleep(0.5)


def wait_for_end(job_id, timeout=120):
    """Wait until the job is no longer in progress."""
    deadline = time.time() + timeout
    while True:
        body = get_job(job_id)
        if body["status"] not in IN_PROGRESS:
            return body
        if time.time() > deadline:
            raise TimeoutError(f"job {job_id} is still {body['status']}")
        time.sleep(0.5)


# --- queues ----------------------------------------------------------------------------


def _sqs(**params):
    body = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(SQS, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return ET.fromstring(response.read())


def queue_depth(name):
    """Messages waiting, in flight or delayed on a queue ('jobs' or 'jobs-dlq')."""
    root = _sqs(
        Action="GetQueueAttributes", QueueUrl=f"{QUEUE_PREFIX}/{name}", **{"AttributeName.1": "All"}
    )
    counts = {}
    for attribute in root.iter():
        if attribute.tag.endswith("Attribute"):
            name_, value = None, None
            for child in attribute:
                if child.tag.endswith("Name"):
                    name_ = child.text
                elif child.tag.endswith("Value"):
                    value = child.text
            counts[name_] = value
    keys = (
        "ApproximateNumberOfMessages",
        "ApproximateNumberOfMessagesNotVisible",
        "ApproximateNumberOfMessagesDelayed",
    )
    return sum(int(counts.get(key, 0)) for key in keys)


def wait_for_depth(name, wanted, timeout=120):
    deadline = time.time() + timeout
    while queue_depth(name) != wanted:
        if time.time() > deadline:
            raise TimeoutError(f"queue {name} depth is {queue_depth(name)}, wanted {wanted}")
        time.sleep(1)


def redeliver(job_id):
    """Send the job's upload notification to the jobs queue again, as SQS may redeliver it."""
    notification = {"Records": [{"s3": {"object": {"key": f"uploads/{job_id}.pdf"}}}]}
    _sqs(
        Action="SendMessage",
        QueueUrl=f"{QUEUE_PREFIX}/jobs",
        MessageBody=json.dumps(notification),
    )


def redrive():
    """Replay the DLQ with native SQS redrive (the `make redrive` command)."""
    subprocess.run(
        [
            *compose_command(),
            "run",
            "--rm",
            "--no-deps",
            "init",
            "python",
            "-m",
            "invoice_extraction.entrypoints.redrive",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


# --- wide events -----------------------------------------------------------------------


def worker_events(job_id):
    """The `llm_call` and `job` wide events the workers printed for one job, in order."""
    logs = subprocess.run(
        [*compose_command(), "logs", "--no-color", "worker-1", "worker-2"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    events = []
    for line in logs.splitlines():
        start = line.find("{")
        if start < 0 or '"event"' not in line:
            continue
        try:
            record = json.loads(line[start:])
        except ValueError:
            continue
        if record.get("job_id") == job_id:
            events.append(record)
    return events


def llm_calls(job_id):
    return [e for e in worker_events(job_id) if e["event"] == "llm_call"]


def job_events(job_id):
    return [e for e in worker_events(job_id) if e["event"] == "job"]


def stack_is_up():
    try:
        call(f"{API}/jobs/probe", timeout=3)  # any HTTP answer means the shim is listening
        return call(f"{FAKE}/health", timeout=3)[0] == 200
    except OSError:
        return False


def wait_until_up(timeout=300):
    """Block until the API shim and fake-gemini answer (the stack just started)."""
    deadline = time.time() + timeout
    while not stack_is_up():
        if time.time() > deadline:
            raise TimeoutError("the local stack did not come up")
        time.sleep(2)


if __name__ == "__main__":
    if sys.argv[1:] == ["wait"]:
        wait_until_up()
        print("stack is up")
    else:
        sys.exit("usage: stack_client.py wait")
