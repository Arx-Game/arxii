#!/usr/bin/env bash
# watch-ci.sh <pr-number>
#
# Polls gh pr checks for the given PR per the cadence in the design doc
# (../references/design.md § "CI watch cadence"). Idempotent across sessions.
#
# Stdout: "OK" if all checks pass and no review thread is open, "FAIL <check-name>"
# on the first failure, "REVIEW <n> unresolved thread(s)" plus one line per thread
# when checks pass but review comments are waiting.
#
# Exits:
#   0  all checks passed and no review thread is unresolved
#   1  usage / generic error
#   5  at least one check failed (stdout names the first failing check)
#   6  hard cap (25 minutes) tripped with checks still pending
#  11  checks passed, but review threads are unresolved. These are blockers (the
#      ruleset requires every thread resolved), and green checks used to read as
#      "OK" while the code-review bot's comments sat unread (#4882). Fix or answer
#      each one, reply, resolve it, push, and watch again.
#
# WATCH_CI_THREADS_JSON_FILE substitutes the review-threads GraphQL response (tests).
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

  # A successful partial rollup (only CodeQL and SonarCloud, #4643) is not proof
  # that CI ran. ci.yml always posts the required `backend` and `frontend`
  # aggregators, even when their tests are skipped, so wait until both are there.
  if ! jq -e 'any(.[]; .name == "backend") and any(.[]; .name == "frontend")' \
    <<<"$json" >/dev/null; then
    echo "PENDING"
    return
  fi

  echo "PASS"
}

# Called once checks are green. The code-review job is itself one of the checks, so
# by now its comments are posted. Threads from any author count.
review_state() {
  local threads_json open
  if [[ -n "${WATCH_CI_THREADS_JSON_FILE:-}" ]]; then
    threads_json=$(cat "$WATCH_CI_THREADS_JSON_FILE")
  else
    local repo
    repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    # shellcheck disable=SC2016  # GraphQL variables, not shell expansions.
    threads_json=$(gh api graphql -F pr="$PR" -f owner="${repo%/*}" -f name="${repo#*/}" \
      -f query='query($owner:String!,$name:String!,$pr:Int!){repository(owner:$owner,name:$name){
        pullRequest(number:$pr){reviewThreads(first:100){nodes{id isResolved path line
          comments(first:1){nodes{author{login} body}}}}}}}') || { echo "ERROR"; return; }
  fi
  open=$(jq -r '.data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false)
    | "  \(.path):\(.line // "?") [\(.comments.nodes[0].author.login // "?")] \(.comments.nodes[0].body | split("\n")[0] | .[0:160])  (thread \(.id))"' \
    <<<"$threads_json")
  if [[ -z "$open" ]]; then
    echo "OK"
  else
    echo "REVIEW $(grep -c . <<<"$open") unresolved thread(s)"
    echo "$open"
  fi
}

# Green checks are only half the answer: report open review threads too.
finish_pass() {
  local review
  review=$(review_state)
  echo "$review"
  case "$review" in
    OK) exit 0 ;;
    REVIEW*) exit 11 ;;
    *) echo "could not read review threads" >&2; exit 1 ;;
  esac
}

# Idempotency: probe first; if not pending, exit immediately.
state=$(check_state)
case "$state" in
  PASS)
    finish_pass
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
    PASS) finish_pass ;;
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
    PASS) finish_pass ;;
    FAIL*) echo "$state"; exit 5 ;;
    *) ;;  # PENDING (or unexpected): keep polling until the hard cap.
  esac
done

echo "TIMEOUT after ${HARD_CAP}s with checks still pending" >&2
exit 6
