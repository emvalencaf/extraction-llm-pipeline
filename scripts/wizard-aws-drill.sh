#!/usr/bin/env bash
#
# A wizard walks a human through a manual procedure, step by step.
# Walks the AWS drill of docs/aws-drill.md.
#
# Everything above the "STAGES" marker is the wizard library: do not hand-edit
# it. Author the per-step stages below the marker.

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# Wizard library: delightful, consistent UX, identical across every wizard.
# ──────────────────────────────────────────────────────────────────────────

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  BOLD=$(tput bold); DIM=$(tput dim); RESET=$(tput sgr0)
  BLUE=$(tput setaf 4); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3)
else
  BOLD=""; DIM=""; RESET=""; BLUE=""; GREEN=""; YELLOW=""
fi

# Author sets this at the top of the stages section.
TOTAL_STAGES=0

_STAGE_INDEX=0
ENV_FILE="${ENV_FILE:-.env}"
WRITTEN_ENV=()    # KEYs written to ENV_FILE this run
WRITTEN_SECRET=() # secret NAMEs set this run
SKIPPED=()        # things we couldn't do (e.g. gh missing)

# _clear wipes the terminal so only the current step is on screen. No-op when
# output isn't a terminal, so piped logs stay readable.
_clear() {
  [[ -t 1 ]] || return 0
  if command -v tput >/dev/null 2>&1 && tput clear 2>/dev/null; then return 0; fi
  printf '\033[2J\033[3J\033[H'
}

# banner "Title" shows the opening frame: what this wizard does.
banner() {
  _clear
  printf '\n%s%s  %s%s\n' "$BOLD" "$BLUE" "$1" "$RESET"
  printf '%s  %s stages%s\n\n' "$DIM" "$TOTAL_STAGES" "$RESET"
  printf '%s  You drive the browser; this wizard tells you exactly what to do and\n' "$DIM"
  printf '  captures the values you copy back. Stop any time with Ctrl-C and re-run\n'
  printf '  later, since it remembers values already saved.%s\n' "$RESET"
  pause "Ready to start?"
}

# stage "Name" clears the screen, then announces a stage and shows progress.
# Clearing keeps only the current step on screen.
stage() {
  _clear
  _STAGE_INDEX=$((_STAGE_INDEX + 1))
  printf '\n%s%s▸ Stage %s/%s · %s%s\n' \
    "$BOLD" "$BLUE" "$_STAGE_INDEX" "$TOTAL_STAGES" "$1" "$RESET"
}

# say "..." prints a plain instruction line.
say()  { printf '  %s\n' "$1"; }
# step "..." is a numbered-feeling action the human takes in the browser.
step() { printf '  %s•%s %s\n' "$BLUE" "$RESET" "$1"; }
note() { printf '  %s%s%s\n' "$DIM" "$1" "$RESET"; }
warn() { printf '  %s⚠ %s%s\n' "$YELLOW" "$1" "$RESET"; }

# open_url URL opens it in the human's browser, cross-platform incl. WSL.
open_url() {
  local url="$1"
  printf '  %s↗ opening%s %s\n' "$GREEN" "$RESET" "$url"
  { if   command -v wslview     >/dev/null 2>&1; then wslview "$url"
    elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$url"
    elif command -v xdg-open    >/dev/null 2>&1; then xdg-open "$url"
    elif command -v open        >/dev/null 2>&1; then open "$url"
    else false; fi
  } >/dev/null 2>&1 || warn "couldn't open a browser, so visit it manually: $url"
}

# pause "msg" waits for the human to confirm they've done the manual part.
pause() {
  printf '  %s%s%s ' "$DIM" "${1:-Press Enter to continue}" "$RESET"
  read -r _ || true
}

# confirm "question" is a y/N gate; returns success on yes.
confirm() {
  local reply=""
  printf '  %s? %s [y/N] ' "$YELLOW" "$1"
  read -r reply || true
  [[ "$reply" =~ ^[Yy] ]]
}

# _existing KEY: current value of KEY in ENV_FILE, if any, with write_env's single
# quotes or a plain dotenv double-quoted value undone.
_existing() {
  [[ -f "$ENV_FILE" ]] || return 1
  local line value sq="'\\''"; line=$(grep -E "^${1}=" "$ENV_FILE" | tail -n1) || return 1
  value="${line#*=}"
  if [[ "$value" == \'*\' ]]; then value="${value:1:${#value}-2}"; value="${value//"$sq"/\'}"
  elif [[ "$value" == \"*\" ]]; then
    value="${value:1:${#value}-2}"
    [[ "$value" == *[\\\$\"]* ]] && return 1   # escapes, $ or ": can't decode safely; ask again
  fi
  printf '%s' "$value"
}

# ask KEY "Prompt" reads a value into $KEY. Offers the existing .env value as
# a default on re-runs (Enter keeps it). Visible input (non-secret), edited
# with Readline. Fails at EOF with no input.
ask() {
  local key="$1" prompt="$2" current input s=$'\001' e=$'\002' p rc=0
  current=$(_existing "$key" || true)
  # Readline needs the colour codes wrapped in \001..\002 to place the cursor.
  p="  $s$BOLD$e$prompt$s$RESET$e "
  [[ -n "$current" ]] && p+="$s$DIM$e[Enter keeps current]$s$RESET$e "
  read -e -r -p "$p" input || rc=1
  if (( rc )) && [[ -z "$input" ]]; then return 1; fi
  [[ -z "$input" && -n "$current" ]] && input="$current"
  printf -v "$key" '%s' "$input"
}

# ask_secret KEY "Prompt" is like ask, but input is hidden.
ask_secret() {
  local key="$1" prompt="$2" current input rc=0
  current=$(_existing "$key" || true)
  if [[ -n "$current" ]]; then
    printf '  %s%s%s %s[Enter keeps current]%s ' "$BOLD" "$prompt" "$RESET" "$DIM" "$RESET"
  else
    printf '  %s%s%s ' "$BOLD" "$prompt" "$RESET"
  fi
  read -rs input || rc=1
  printf '\n'
  if (( rc )) && [[ -z "$input" ]]; then return 1; fi
  [[ -z "$input" && -n "$current" ]] && input="$current"
  printf -v "$key" '%s' "$input"
}

# write_env KEY VALUE upserts KEY='VALUE' into ENV_FILE (replaces any existing
# line) and sets $KEY. Idempotent. Creates ENV_FILE at mode 0600; writes through
# a symlink and keeps an existing file's mode.
write_env() {
  local key="$1" value="$2" tmp sq="'\\''"
  [[ -e "$ENV_FILE" ]] || (umask 077 && : > "$ENV_FILE")
  tmp=$(mktemp)
  grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf "%s='%s'\n" "$key" "${value//\'/$sq}" >> "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
  printf -v "$key" '%s' "$value"
  WRITTEN_ENV+=("$key")
  printf '  %s✓ wrote%s %s → %s\n' "$GREEN" "$RESET" "$key" "$ENV_FILE"
}

# set_secret NAME VALUE sets a GitHub Actions repo secret via gh. Falls back
# to a warning (and records it) if gh is unavailable or unauthenticated.
set_secret() {
  local name="$1" value="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if printf '%s' "$value" | gh secret set "$name" >/dev/null 2>&1; then
      WRITTEN_SECRET+=("$name")
      printf '  %s✓ set%s GitHub secret %s\n' "$GREEN" "$RESET" "$name"
      return
    fi
  fi
  SKIPPED+=("GitHub secret $name (set it manually: gh secret set $name)")
  warn "skipped GitHub secret $name: gh not ready; set it later"
}

# set_var NAME VALUE sets a GitHub Actions repo variable (non-secret).
set_var() {
  local name="$1" value="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh variable set "$name" --body "$value" >/dev/null 2>&1; then
      printf '  %s✓ set%s GitHub variable %s\n' "$GREEN" "$RESET" "$name"
      return
    fi
  fi
  SKIPPED+=("GitHub variable $name")
  warn "skipped GitHub variable $name, gh not ready; set it later"
}

# finish clears, then shows a closing summary of everything configured.
finish() {
  _clear
  printf '\n%s%s  ✓ Setup complete%s\n' "$BOLD" "$GREEN" "$RESET"
  (( ${#WRITTEN_ENV[@]} ))    && note "wrote ${#WRITTEN_ENV[@]} value(s) to $ENV_FILE: ${WRITTEN_ENV[*]}"
  (( ${#WRITTEN_SECRET[@]} )) && note "set ${#WRITTEN_SECRET[@]} GitHub secret(s): ${WRITTEN_SECRET[*]}"
  if (( ${#SKIPPED[@]} )); then
    printf '\n'; warn "still to do by hand:"
    for s in "${SKIPPED[@]}"; do note "  - $s"; done
  fi
  printf '\n'
}

# ──────────────────────────────────────────────────────────────────────────
# STAGES: the AWS drill of docs/aws-drill.md. Needs AWS credentials in the
# shell. It only touches the deployed stack's alarms and the two queues.
# ──────────────────────────────────────────────────────────────────────────

ALARMS=(job-failed llm-call-errors job-duration-high grounding-rate-low
        dlq-not-empty queue-age-high worker-errors api-errors)
export AWS_PAGER=""   # no (END) pager from the aws CLI
ORIGINAL_VT=""   # jobs queue visibility timeout before the drill
VT_CHANGED=0

queue_count() {  # queue_count URL ATTR
  aws sqs get-queue-attributes --queue-url "$1" --attribute-names "$2" \
    --query "Attributes.$2" --output text
}

restore_vt() {
  if [[ "$VT_CHANGED" == "1" && -n "$ORIGINAL_VT" ]]; then
    aws sqs set-queue-attributes --queue-url "$JOBS_URL" \
      --attributes VisibilityTimeout="$ORIGINAL_VT" >/dev/null \
      && VT_CHANGED=0 && printf '  restored the jobs queue visibility timeout to %s\n' "$ORIGINAL_VT"
  fi
}
trap restore_vt EXIT

# wait_for "what" SECONDS CMD... polls CMD every 10 s until it succeeds.
wait_for() {
  local what="$1" limit="$2" waited=0; shift 2
  while ! "$@" >/dev/null 2>&1; do
    (( waited >= limit )) && { warn "timed out after ${limit}s waiting for: $what"; return 1; }
    printf '  %s… waiting for %s (%ss)%s\r' "$DIM" "$what" "$waited" "$RESET"
    sleep 10; waited=$((waited + 10))
  done
  printf '\n  %s✓%s %s\n' "$GREEN" "$RESET" "$what"
}

dlq_has_message() { [[ "$(queue_count "$DLQ_URL" ApproximateNumberOfMessagesVisible)" -ge 1 ]]; }
dlq_is_empty()    { [[ "$(queue_count "$DLQ_URL" ApproximateNumberOfMessagesVisible)" -eq 0 ]]; }
alarm_in_alarm()  { [[ "$(aws cloudwatch describe-alarms --alarm-names "$PREFIX-dlq-not-empty" \
                          --query 'MetricAlarms[0].StateValue' --output text)" == "ALARM" ]]; }
alarm_is_ok()     { [[ "$(aws cloudwatch describe-alarms --alarm-names "$PREFIX-dlq-not-empty" \
                          --query 'MetricAlarms[0].StateValue' --output text)" != "ALARM" ]]; }

run_wizard() {

TOTAL_STAGES=7
RESULT_ALARMS="?"; RESULT_DLQ="no"; RESULT_REDRIVE="no"

banner "AWS drill: alarms, poison message and redrive (docs/aws-drill.md)"

stage "Preflight"
say "Checks credentials, reads the queues from Terraform and refuses to start on a"
say "dirty DLQ (a purge at the end would destroy real failed jobs)."
command -v aws >/dev/null || { warn "aws CLI not found"; exit 1; }
command -v terraform >/dev/null || { warn "terraform not found"; exit 1; }
[[ -f infra/main.tf ]] || { warn "run this from the repository root"; exit 1; }
aws sts get-caller-identity --query Arn --output text || { warn "no valid AWS credentials in this shell"; exit 1; }
export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_DEFAULT_REGION="$AWS_REGION"
PREFIX="${PREFIX:-invoice-extraction-prod}"
JOBS_URL=$(terraform -chdir=infra output -raw jobs_queue_url)
DLQ_URL=$(terraform -chdir=infra output -raw dlq_url)
export JOBS_QUEUE_NAME="${JOBS_URL##*/}" DLQ_NAME="${DLQ_URL##*/}"
say "region=$AWS_REGION prefix=$PREFIX"
say "jobs queue=$JOBS_QUEUE_NAME  dlq=$DLQ_NAME"
if ! dlq_is_empty; then
  warn "the DLQ already holds messages. Handle them first (see docs/runbook.md); the drill purges the DLQ."
  exit 1
fi
if [[ "$(queue_count "$JOBS_URL" ApproximateNumberOfMessagesVisible)" != "0" ]]; then
  warn "the jobs queue has pending messages; the drill shortens its visibility timeout."
  confirm "Continue anyway?" || exit 1
fi
say "Open the inbox of alert_email: the SNS subscription must be confirmed."
confirm "Is the SNS subscription confirmed?" || { warn "confirm it first (docs/runbook.md, First deploy)"; exit 1; }
confirm "Run the drill against this account and region?" || exit 1

stage "1/5 · Fire the 8 alarms"
say "set-alarm-state moves each alarm to ALARM; it tests the SNS topic and the email."
for name in "${ALARMS[@]}"; do
  aws cloudwatch set-alarm-state --alarm-name "$PREFIX-$name" \
    --state-value ALARM --state-reason "aws-drill: fire alarm $name"
  say "✓ $PREFIX-$name"
done
step "Check your inbox: one email per alarm should arrive within a few minutes (8)."
ask RESULT_ALARMS "How many alarm emails arrived (0-8)?"
(( RESULT_ALARMS == 8 )) || warn "expected 8; check the SNS subscription and spam"

stage "2/5 · Send the poison message"
say "The jobs queue visibility timeout is 6x the worker timeout; the drill lowers it"
say "to 30 s so the 5 receives take minutes, and restores it afterwards (also on Ctrl-C)."
ORIGINAL_VT=$(queue_count "$JOBS_URL" VisibilityTimeout)
say "original visibility timeout: ${ORIGINAL_VT}s"
aws sqs set-queue-attributes --queue-url "$JOBS_URL" --attributes VisibilityTimeout=30
VT_CHANGED=1
aws sqs send-message --queue-url "$JOBS_URL" \
  --message-body 'aws-drill poison message, not an S3 notification' >/dev/null
say "✓ sent"
if wait_for "the message to reach the DLQ" 900 dlq_has_message; then RESULT_DLQ="yes"; fi
restore_vt
note "Worker log: aws logs tail /aws/lambda/$PREFIX-worker --since 20m  (receive_count=1..5)"

stage "3/5 · The dlq-not-empty alarm from the real metric"
say "set-alarm-state was only a push; now the metric itself should breach (up to ~5 min)."
if wait_for "dlq-not-empty to reach ALARM" 600 alarm_in_alarm; then
  step "An email for dlq-not-empty should arrive again."
else
  warn "the alarm did not fire from the metric; check evaluation periods in the observability module"
fi
pause "Press Enter to continue."

stage "4/5 · Inspect the DLQ message"
aws sqs receive-message --queue-url "$DLQ_URL" --visibility-timeout 0 \
  --message-attribute-names All --max-number-of-messages 1 \
  --query 'Messages[0].Body' --output text
say "↑ the body should be the poison text."
pause "Press Enter to redrive."

stage "5/5 · Redrive, then drain"
say "A poison message fails again after a redrive; this shows the mechanics and the loop."
if ! uv run python -m invoice_extraction.entrypoints.redrive; then
  warn "redrive failed; see docs/runbook.md"
else
  RESULT_REDRIVE="ok"
  aws sqs set-queue-attributes --queue-url "$JOBS_URL" --attributes VisibilityTimeout=30
  VT_CHANGED=1
  wait_for "the DLQ to be empty after the redrive" 120 dlq_is_empty || true
  wait_for "the message to fail 5 more times and return to the DLQ" 900 dlq_has_message || true
  restore_vt
fi
if [[ "$(queue_count "$DLQ_URL" ApproximateNumberOfMessagesVisible)" == "1" ]]; then
  if confirm "The DLQ holds only the drill's message. Purge the DLQ?"; then
    aws sqs purge-queue --queue-url "$DLQ_URL"
    wait_for "dlq-not-empty back to OK" 600 alarm_is_ok || true
  fi
else
  warn "the DLQ does not hold exactly 1 message; not purging. Inspect it by hand."
fi

stage "Clean up and check"
restore_vt
say "Jobs queue visibility timeout: $(queue_count "$JOBS_URL" VisibilityTimeout)s (original ${ORIGINAL_VT}s)"
aws cloudwatch describe-alarms --alarm-name-prefix "$PREFIX" \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table
note "Alarms return to OK/INSUFFICIENT_DATA on their next evaluation (up to 5 min)."
say "terraform plan (expects no changes):"
set +e
terraform -chdir=infra plan -detailed-exitcode -input=false >/dev/null 2>&1
rc=$?
set -e
case $rc in
  0) say "✓ no changes" ;;
  2) warn "terraform shows drift; check the visibility timeout and re-run the plan" ;;
  *) warn "terraform plan failed; run it by hand" ;;
esac

COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
finish
say "Add this row to the Outcome table in docs/aws-drill.md:"
printf '\n| %s | %s | %s | %s of 8 | %s | %s | |\n\n' \
  "$(date +%F)" "$(git config user.name 2>/dev/null || echo "?")" "$COMMIT" \
  "$RESULT_ALARMS" "$RESULT_DLQ" "$RESULT_REDRIVE"
}

run_wizard "$@"; exit
