"""Fixtures for the compose-stack tests (test seam 2, API level).

These tests need the local stack: `make test-compose` starts it, runs them and stops it.
They are skipped when no stack answers, and deselected from a plain `pytest` run.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import stack_client as stack


def pytest_collection_modifyitems(items):
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.path)).parents:
            item.add_marker(pytest.mark.compose)
            if not stack.stack_is_up():
                item.add_marker(pytest.mark.skip(reason="local stack is not running"))


@pytest.fixture(scope="session", autouse=True)
def warm_workers():
    """Run jobs through both workers once: a cold worker loads the NLP model on first use."""
    if not stack.stack_is_up():
        return
    stack.clear_injections()
    jobs = [stack.submit() for _ in range(2)]
    for job_id in jobs:
        stack.wait_for(job_id, {"succeeded"}, timeout=180)


@pytest.fixture(autouse=True)
def clean_injections():
    """Every scenario starts and ends with fake-gemini behaving normally."""
    if stack.stack_is_up():
        stack.clear_injections()
    yield
    if stack.stack_is_up():
        stack.clear_injections()
