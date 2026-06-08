#!/usr/bin/env bash
# watch-ci.sh <pr-number>
#
# Polls gh pr checks for the given PR per the cadence in the design doc
# (../references/design.md § "CI watch cadence"). Idempotent across sessions.
#
# Stdout: "OK" if all checks pass, "FAIL <check-name>" on the first failure.
#
# Exits:
#   0  all checks passed (or already settled when invoked)
#   1  usage / generic error
#   5  at least one check failed (stdout names the first failing check)
#   6  hard cap (25 minutes) tripped with checks still pending
set -euo pipefail

usage() { echo "Usage: $0 <pr-number>" >&2; exit 1; }

[[ $# -eq 1 ]] || usage
PR="$1"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

CADENCE=(90 300 180 120 60)
HARD_CAP=$((25 * 60))
elapsed=0

check_state() {
  # Emit one of: "PASS", "FAIL <name>", "PENDING".
  # `gh pr checks` has no --json flag; use `gh pr view --json statusCheckRollup`
  # which returns an array of {name, status, conclusion, workflowName, ...}.
  # status is one of QUEUED, IN_PROGRESS, COMPLETED. conclusion is SUCCESS,
  # FAILURE, CANCELLED, SKIPPED, NEUTRAL, TIMED_OUT, ACTION_REQUIRED, STALE.
  local json
  json=$(gh pr view "$PR" --json statusCheckRollup --jq .statusCheckRollup 2>/dev/null || echo "")
  if [[ -z "$json" ]] || [[ "$json" == "null" ]]; then
    # gh actually failed (auth, network, missing PR). Don't pretend it passed.
    echo "ERROR" >&2
    return 1
  fi
  if [[ "$json" == "[]" ]]; then
    # PR exists but no checks attached yet. Treat as pending — checks may register shortly.
    echo "PENDING"
    return
  fi

  local failing pending
  failing=$(jq -r '
    .[] | select(.status == "COMPLETED" and
      (.conclusion == "FAILURE" or .conclusion == "CANCELLED" or .conclusion == "TIMED_OUT" or .conclusion == "ACTION_REQUIRED")
    ) | .name
  ' <<<"$json" | head -1)
  if [[ -n "$failing" ]]; then
    echo "FAIL $failing"
    return
  fi

  pending=$(jq -r '.[] | select(.status != "COMPLETED") | .name' <<<"$json" | head -1)
  if [[ -n "$pending" ]]; then
    echo "PENDING"
    return
  fi

  echo "PASS"
}

# Idempotency: probe first; if not pending, exit immediately.
state=$(check_state)
case "$state" in
  PASS)
    echo "OK"
    exit 0
    ;;
  FAIL*)
    echo "$state"
    exit 5
    ;;
  *) ;;  # PENDING (or unexpected): fall through to the cadence loop.
esac

# Pending: walk the cadence.
for delay in "${CADENCE[@]}"; do
  if (( elapsed + delay > HARD_CAP )); then
    delay=$(( HARD_CAP - elapsed ))
    (( delay <= 0 )) && break
  fi
  sleep "$delay"
  elapsed=$((elapsed + delay))
  state=$(check_state)
  case "$state" in
    PASS) echo "OK"; exit 0 ;;
    FAIL*) echo "$state"; exit 5 ;;
    *) ;;  # PENDING (or unexpected): keep walking the cadence.
  esac
done

# Stay at the final cadence (60s) until cap.
while (( elapsed < HARD_CAP )); do
  remaining=$(( HARD_CAP - elapsed ))
  delay=$(( remaining < 60 ? remaining : 60 ))
  sleep "$delay"
  elapsed=$((elapsed + delay))
  state=$(check_state)
  case "$state" in
    PASS) echo "OK"; exit 0 ;;
    FAIL*) echo "$state"; exit 5 ;;
    *) ;;  # PENDING (or unexpected): keep polling until the hard cap.
  esac
done

echo "TIMEOUT after ${HARD_CAP}s with checks still pending" >&2
exit 6
