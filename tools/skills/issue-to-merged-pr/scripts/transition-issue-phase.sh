#!/usr/bin/env bash
# transition-issue-phase.sh <issue-number> <from-status-label> <to-status-label>
#
# Move an owned issue between workflow phases without trusting a stale read.
# GitHub does not offer a transaction for issue bodies, assignees, and labels,
# so this helper validates a snapshot, performs the label change, then verifies
# the complete relevant state again. A mismatch is a failure: it never claims
# that the transition succeeded and never overwrites a concurrent edit.
set -euo pipefail

usage() {
  echo "Usage: $0 <issue-number> <from-status-label> <to-status-label>" >&2
  exit 2
}
[[ $# -eq 3 ]] || usage
ISSUE="$1"
FROM="$2"
TO="$3"
[[ "$ISSUE" =~ ^[0-9]+$ ]] || usage
[[ "$FROM" =~ ^status:[a-z-]+$ && "$TO" =~ ^status:[a-z-]+$ && "$FROM" != "$TO" ]] || usage

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
BEFORE_JSON="$TMP_DIR/before.json"
AFTER_JSON="$TMP_DIR/after.json"
BEFORE_BODY="$TMP_DIR/before.body"
AFTER_BODY="$TMP_DIR/after.body"

fetch_issue() {
  local destination="$1" attempt payload
  for attempt in 1 2 3; do
    if payload=$(gh issue view "$ISSUE" --json state,body,labels,assignees 2>/dev/null); then
      printf '%s' "$payload" > "$destination"
      return 0
    fi
    [[ "$attempt" -lt 3 ]] || break
  done
  echo "ERROR: could not read issue #$ISSUE from GitHub." >&2
  echo "Recovery: confirm GitHub access, inspect the issue, then retry the same transition." >&2
  return 1
}

fail_recovery() {
  local reason="$1"
  echo "ERROR: refused to report a successful transition for issue #$ISSUE: $reason" >&2
  echo "Recovery: inspect the issue and resolve the competing edit or claim; then rerun this transition." >&2
  return 1
}

CURRENT_USER=$(gh api user --jq '.login') || {
  echo "ERROR: could not determine the authenticated GitHub user." >&2
  exit 1
}
fetch_issue "$BEFORE_JSON"

STATE=$(jq -r '.state' "$BEFORE_JSON")
[[ "$STATE" == "OPEN" ]] || fail_recovery "issue is $STATE, not OPEN" || exit 1
jq -r '.body // ""' "$BEFORE_JSON" > "$BEFORE_BODY"
BEFORE_LABELS=$(jq -r '[.labels[].name] | sort | .[]' "$BEFORE_JSON")
BEFORE_ASSIGNEES=$(jq -r '[.assignees[].login] | sort | .[]' "$BEFORE_JSON")
BEFORE_LABELS_CSV=$(jq -r '[.labels[].name] | sort | join(",")' "$BEFORE_JSON")
BEFORE_APPROVED=0
if grep -Fxq "spec:approved" <<<"$BEFORE_LABELS"; then
  BEFORE_APPROVED=1
fi
if ! grep -Fxq "$FROM" <<<"$BEFORE_LABELS"; then
  fail_recovery "expected label $FROM is absent" || exit 1
fi
if grep -Fxq "$TO" <<<"$BEFORE_LABELS"; then
  fail_recovery "target label $TO is already present" || exit 1
fi
if ! grep -Fxq "$CURRENT_USER" <<<"$BEFORE_ASSIGNEES"; then
  fail_recovery "issue is not assigned to the authenticated user ($CURRENT_USER)" || exit 1
fi

# Validate the exact snapshot used for the transition, rather than fetching a
# second unconstrained snapshot that could already be stale.
"$SCRIPT_DIR/validate-discovery.sh" "$ISSUE" --body-file "$BEFORE_BODY" --labels "$BEFORE_LABELS_CSV" >/dev/null || {
  echo "ERROR: discovery validation failed before transitioning issue #$ISSUE." >&2
  echo "Recovery: fix the issue's discovery marker and rerun the transition." >&2
  exit 1
}

BEFORE_HASH=$(sha256sum "$BEFORE_BODY" | awk '{print $1}')
BEFORE_MARKER=$(awk '/<!-- spec:start -->/{exit} /<!-- discovery:lane=/{print}' "$BEFORE_BODY")
EXPECTED_LABELS=$(printf '%s\n' "$BEFORE_LABELS" | grep -Fxv "$FROM"; printf '%s\n' "$TO")
EXPECTED_LABELS=$(sort -u <<<"$EXPECTED_LABELS")

if ! gh issue edit "$ISSUE" --remove-label "$FROM" --add-label "$TO" >/dev/null; then
  echo "ERROR: GitHub rejected the phase transition for issue #$ISSUE." >&2
  echo "Recovery: inspect the labels; the operation may have partially applied. Rerun only after confirming the current phase." >&2
  exit 1
fi

if ! fetch_issue "$AFTER_JSON"; then
  echo "ERROR: phase label changed but post-transition verification could not read issue #$ISSUE." >&2
  echo "Recovery: inspect the issue before retrying; do not assume the transition is safe." >&2
  exit 1
fi
jq -r '.body // ""' "$AFTER_JSON" > "$AFTER_BODY"
AFTER_LABELS=$(jq -r '[.labels[].name] | sort | .[]' "$AFTER_JSON")
AFTER_ASSIGNEES=$(jq -r '[.assignees[].login] | sort | .[]' "$AFTER_JSON")
AFTER_APPROVED=0
if grep -Fxq "spec:approved" <<<"$AFTER_LABELS"; then
  AFTER_APPROVED=1
fi
AFTER_HASH=$(sha256sum "$AFTER_BODY" | awk '{print $1}')
AFTER_MARKER=$(awk '/<!-- spec:start -->/{exit} /<!-- discovery:lane=/{print}' "$AFTER_BODY")
AFTER_STATE=$(jq -r '.state' "$AFTER_JSON")

[[ "$AFTER_STATE" == "OPEN" ]] || fail_recovery "issue state changed to $AFTER_STATE" || exit 1
[[ "$AFTER_HASH" == "$BEFORE_HASH" ]] || fail_recovery "issue body changed during the transition" || exit 1
[[ "$AFTER_MARKER" == "$BEFORE_MARKER" ]] || fail_recovery "discovery marker changed during the transition" || exit 1
[[ "$AFTER_ASSIGNEES" == "$BEFORE_ASSIGNEES" ]] || fail_recovery "assignee or claim changed during the transition" || exit 1
[[ "$AFTER_APPROVED" == "$BEFORE_APPROVED" ]] || fail_recovery "approval state changed during the transition" || exit 1
[[ "$AFTER_LABELS" == "$EXPECTED_LABELS" ]] || fail_recovery "labels changed concurrently (expected only $FROM -> $TO)" || exit 1
if ! grep -Fxq "$CURRENT_USER" <<<"$AFTER_ASSIGNEES"; then
  fail_recovery "issue is no longer assigned to the authenticated user" || exit 1
fi

printf 'transition: %s -> %s issue=%s user=%s\n' "$FROM" "$TO" "$ISSUE" "$CURRENT_USER"
