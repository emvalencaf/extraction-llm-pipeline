#!/usr/bin/env bash
# Proves the `ci` checks fail on seeded violations: copies the working tree to a temp dir,
# plants one violation per check and asserts the matching command exits non-zero.
# Usage: scripts/ci_seeded_violations.sh   (needs uv and terraform; actionlint is optional)
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
failed=0

expect_fail() { # name, command...
  local name=$1
  shift
  if (cd "$tmp/w" && "$@" >/dev/null 2>&1); then
    echo "NOT CAUGHT: $name"
    failed=1
  else
    echo "caught:     $name"
  fi
}

fresh() {
  rm -rf "$tmp/w"
  mkdir "$tmp/w"
  tar -C "$root" --exclude=.git --exclude=.venv --exclude=.terraform -cf - . |
    tar -C "$tmp/w" -xf -
}

fresh
printf 'import os\n' >>"$tmp/w/src/invoice_extraction/domain/__init__.py"
expect_fail "ruff lint (unused import)" uvx ruff check .

fresh
printf 'x=1\n' >"$tmp/w/src/unformatted.py"
expect_fail "ruff format" uvx ruff format --check .

fresh
printf 'import boto3\n' >>"$tmp/w/src/invoice_extraction/domain/status.py"
expect_fail "import-linter (core imports boto3)" uv run lint-imports

fresh
printf '\ndef test_seeded():\n    assert False\n' >>"$tmp/w/tests/test_grounding.py"
expect_fail "unit tests" uv run pytest -q -x

fresh
printf 'resource "x" {\n bad = \n}\n' >"$tmp/w/infra/bad.tf"
expect_fail "terraform validate" sh -c \
  'terraform -chdir=infra init -backend=false -input=false && terraform -chdir=infra validate'

if command -v actionlint >/dev/null; then
  fresh
  sed -i 's/^  contents: read/  bogus: write/' "$tmp/w/.github/workflows/ci.yml"
  expect_fail "actionlint (invalid permission scope)" actionlint
fi

fresh
sed -i 's/^  pull_request:/  pull_request_target:/' "$tmp/w/.github/workflows/regression-gate.yml"
expect_fail "regression-gate hardening (pull_request_target)" \
  uv run pytest -q tests/test_regression_gate_workflow.py

fresh
sed -i 's/^  contents: read/  contents: write/' "$tmp/w/.github/workflows/regression-gate.yml"
expect_fail "regression-gate hardening (write token by default)" \
  uv run pytest -q tests/test_regression_gate_workflow.py

fresh
sed -i 's/return max(marked/return min(marked/' "$tmp/w/scripts/sticky_comment.py"
expect_fail "sticky comment (updates the oldest instead of the newest)" \
  uv run pytest -q tests/test_sticky_comment.py
exit $failed
