#!/usr/bin/env bash
# pickup-issue.sh <issue-number>
#
# 1. Precheck: superpowers plugin must be installed.
# 2. Fetch the issue via `gh issue view`.
# 3. Infer the issue type from labels (feature|fix|chore|refactor|test|docs|perf).
# 4. Build slug from the title (lowercase, alphanumerics + hyphens, max 40 chars).
# 5. Create branch <type>-<N>-<slug> from origin/main.
# 6. Emit JSON {type, slug, branch, parent_issue_url} on stdout.
#
# Exits:
#   0  success
#   1  usage / generic error
#   2  superpowers plugin missing
#   3  issue closed or assigned to a different user
set -euo pipefail

usage() {
  echo "Usage: $0 <issue-number>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage
ISSUE="$1"
[[ "$ISSUE" =~ ^[0-9]+$ ]] || usage

# 1. Superpowers precheck
if ! claude plugin list 2>/dev/null | grep -q "superpowers@claude-plugins-official"; then
  echo "ERROR: superpowers plugin not installed." >&2
  echo "Install with: claude plugin install superpowers@claude-plugins-official" >&2
  exit 2
fi

# 2. Fetch the issue
ISSUE_JSON=$(gh issue view "$ISSUE" --json number,title,labels,state,assignees,url)

STATE=$(jq -r '.state' <<<"$ISSUE_JSON")
if [[ "$STATE" != "OPEN" ]]; then
  echo "ERROR: issue #$ISSUE is $STATE, not OPEN." >&2
  exit 3
fi

CURRENT_USER=$(gh api user --jq '.login')
ASSIGNEES=$(jq -r '.assignees[].login' <<<"$ISSUE_JSON")
if [[ -n "$ASSIGNEES" ]] && ! grep -qx "$CURRENT_USER" <<<"$ASSIGNEES"; then
  echo "ERROR: issue #$ISSUE is assigned to: $ASSIGNEES (you are $CURRENT_USER)." >&2
  exit 3
fi

# 3. Infer type from labels
LABELS=$(jq -r '.labels[].name' <<<"$ISSUE_JSON")
TYPE=""
for candidate in feature fix chore refactor test docs perf; do
  if grep -qx "$candidate" <<<"$LABELS"; then
    TYPE="$candidate"
    break
  fi
done
if [[ -z "$TYPE" ]]; then
  echo "ERROR: issue #$ISSUE has no recognized type label" >&2
  echo "(expected one of: feature, fix, chore, refactor, test, docs, perf)." >&2
  echo "Labels found: $LABELS" >&2
  exit 1
fi

# 4. Build slug
TITLE=$(jq -r '.title' <<<"$ISSUE_JSON")
SLUG=$(echo "$TITLE" \
  | tr '[:upper:]' '[:lower:]' \
  | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' \
  | cut -c1-40 \
  | sed 's/-$//')
BRANCH="${TYPE}-${ISSUE}-${SLUG}"

# 5. Create branch from origin/main
git fetch origin main --quiet
git checkout -b "$BRANCH" origin/main

# 6. Emit JSON
URL=$(jq -r '.url' <<<"$ISSUE_JSON")
jq -n \
  --arg type "$TYPE" \
  --arg slug "$SLUG" \
  --arg branch "$BRANCH" \
  --arg url "$URL" \
  '{type: $type, slug: $slug, branch: $branch, parent_issue_url: $url}'
