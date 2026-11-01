"""Hardening invariants of the regression-gate workflow (actionlint covers the syntax)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / ".github/workflows/regression-gate.yml").read_text(encoding="utf-8")


def job_block(name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", TEXT, re.S | re.M)
    assert match, f"job {name} not found"
    return match.group(1)


def test_never_runs_untrusted_code_with_the_base_repo_token():
    code = "\n".join(
        line.split(" #")[0] for line in TEXT.splitlines() if not line.lstrip().startswith("#")
    )
    assert "pull_request_target" not in code
    assert re.search(r"^  pull_request:", TEXT, re.M)


def test_default_token_is_read_only_and_only_the_comment_job_writes():
    assert re.search(r"^permissions:\n  contents: read\n", TEXT, re.M)
    assert TEXT.count("pull-requests: write") == 1
    assert "pull-requests: write" in job_block("comment")


def test_secrets_only_reach_the_gate_job_and_fork_prs_fail_safe():
    for name in ("fork-guard", "comment"):
        assert "secrets." not in job_block(name)
    assert "secrets.GATE_GEMINI_API_KEY" in job_block("gate")
    assert "head.repo.full_name == github.repository" in job_block("gate")
    assert "exit 1" in job_block("fork-guard")


def test_path_filter_lists_what_the_gate_depends_on_and_existing_paths_only():
    paths = re.findall(r"^      - (\S+)$", TEXT.split("permissions:")[0], re.M)
    assert "src/invoice_extraction/prompts/**" in paths
    assert "data/baseline.json" in paths
    assert "scripts/regression_gate.py" in paths
    for path in paths:
        assert list(ROOT.glob(path)), f"{path} matches nothing"


def test_third_party_actions_are_pinned_to_a_commit():
    for use in re.findall(r"uses: (\S+)", TEXT):
        assert re.search(r"@[0-9a-f]{40}$", use), use
