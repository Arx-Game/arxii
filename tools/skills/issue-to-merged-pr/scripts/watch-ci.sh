#!/usr/bin/env bash
# watch-ci.sh <pr-number>
#
# Polls gh pr checks for the given PR per the cadence in the spec
# (docs/superpowers/specs/2026-05-25-issue-to-merged-pr-design.md §
# "CI watch cadence"). Idempotent across sessions.
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
  local json
  json=$(gh pr checks "$PR" --json name,state 2>/dev/null || echo "[]")
  if [[ "$json" == "[]" ]] || [[ -z "$json" ]]; then
    echo "PASS"
    return
  fi

  local failing pending
  failing=$(jq -r '.[] | select(.state == "FAILURE" or .state == "ERROR" or .state == "CANCELLED") | .name' <<<"$json" | head -1)
  if [[ -n "$failing" ]]; then
    echo "FAIL $failing"
    return
  fi

  pending=$(jq -r '.[] | select(.state == "PENDING" or .state == "IN_PROGRESS" or .state == "QUEUED") | .name' <<<"$json" | head -1)
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
  esac
done

echo "TIMEOUT after ${HARD_CAP}s with checks still pending" >&2
exit 6
