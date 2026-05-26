#!/usr/bin/env bash
# get-ci-failure.sh <pr-number> <check-name>
#
# Finds the most recent failing run of <check-name> on the given PR,
# fetches its log via gh run view --log-failed, and prints the last
# ~200 lines plus a summary line (the check name and conclusion).
#
# Exits:
#   0  success (log printed)
#   1  usage / generic error
#   7  no failing run found for that check name
set -euo pipefail

usage() { echo "Usage: $0 <pr-number> <check-name>" >&2; exit 1; }

[[ $# -eq 2 ]] || usage
PR="$1"
CHECK="$2"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

# Find the PR's head branch ref.
HEAD_REF=$(gh pr view "$PR" --json headRefName --jq .headRefName)

# List recent runs on this branch matching the check name, take the most recent failing.
RUN_ID=$(gh run list \
  --branch "$HEAD_REF" \
  --json databaseId,name,conclusion,createdAt \
  --limit 50 \
  | jq -r --arg name "$CHECK" \
      '[.[] | select(.name == $name and (.conclusion == "failure" or .conclusion == "cancelled" or .conclusion == "timed_out"))]
       | sort_by(.createdAt) | reverse | .[0].databaseId // empty')

if [[ -z "$RUN_ID" ]]; then
  echo "ERROR: no failing run found for check '$CHECK' on PR #$PR (branch $HEAD_REF)" >&2
  exit 7
fi

echo "=== check: $CHECK | run: $RUN_ID | branch: $HEAD_REF ==="
gh run view "$RUN_ID" --log-failed 2>/dev/null | tail -n 200
echo "=== end of failing log ==="
