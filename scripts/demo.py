# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Send one sample invoice through the running local stack and print the result JSON.

`make demo` wraps this with stack-up, stack-wait and stack-down. The stack is token-free
(fake Gemini), so no credentials are needed. Exit code 0 only when the job `succeeded`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_client as stack


def main() -> int:
    _, job = stack.post_job()
    print(f"created job {job['job_id']} ({job['status']})", file=sys.stderr)
    stack.upload(job)
    print("uploaded the sample invoice, polling...", file=sys.stderr)
    body = stack.wait_for_end(job["job_id"])
    print(json.dumps(body, indent=2))
    return 0 if body["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
