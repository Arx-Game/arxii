#!/usr/bin/env bash
# get-ci-failure.sh <pr-number> <check-name>
#
# Finds a failing CI run on the given PR's head branch and prints the last
# ~200 lines of its failed-job log.
#
# Lookup strategy: `gh pr checks` reports CHECK/JOB names (e.g.,
# "pre-commit", "Run tests (3.13)"), but `gh run list` reports WORKFLOW
# names (e.g., "CI"). To bridge them, we first try to match the workflow
# name; if no match, we fall back to the most recent failing run on the
# branch regardless of name. The log usually identifies which job inside
# the run failed, so the agent reading it can still narrow down.
#
# Exits:
#   0  success (log printed)
#   1  usage / generic error
#   7  no failing run found on the branch at all
set -euo pipefail

usage() { echo "Usage: $0 <pr-number> <check-name>" >&2; exit 1; }

[[ $# -eq 2 ]] || usage
PR="$1"
CHECK="$2"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

# Find the PR's head branch ref.
HEAD_REF=$(gh pr view "$PR" --json headRefName --jq .headRefName)

RUNS_JSON=$(gh run list \
  --branch "$HEAD_REF" \
  --json databaseId,name,conclusion,createdAt \
  --limit 50)

# Helper: pick most-recent failing run, optionally filtered by name match.
pick_run() {
  local name_filter="$1"
  jq -r --arg name "$name_filter" '
    [.[] | select(
        (.conclusion == "failure" or .conclusion == "cancelled" or .conclusion == "timed_out")
        and ($name == "" or .name == $name)
    )]
    | sort_by(.createdAt) | reverse | .[0].databaseId // empty
  ' <<<"$RUNS_JSON"
}

# Try exact name match against the workflow name first.
RUN_ID=$(pick_run "$CHECK")
MATCHED="exact workflow-name match"

# Fall back to the most recent failing run regardless of name.
if [[ -z "$RUN_ID" ]]; then
  RUN_ID=$(pick_run "")
  MATCHED="fallback: most recent failing run on branch (no workflow named '$CHECK')"
fi

if [[ -z "$RUN_ID" ]]; then
  echo "ERROR: no failing run found on PR #$PR (branch $HEAD_REF)" >&2
  exit 7
fi

echo "=== check: $CHECK | run: $RUN_ID | branch: $HEAD_REF | $MATCHED ==="
gh run view "$RUN_ID" --log-failed 2>/dev/null | tail -n 200 || true
echo "=== end of failing log ==="
