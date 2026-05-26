#!/usr/bin/env bash
# read-pr-comments.sh <pr-number>
#
# Emits as JSON the comments on the PR that are newer than the marker
# in the PR body: <!-- last-addressed-comment: <id> -->
# If the marker is missing or set to 0, returns all comments.
#
# Merges issue-style PR comments (gh api issues/:pr/comments) and review-
# thread comments (gh api pulls/:pr/comments). Output is a JSON array
# sorted by created_at ascending.
#
# Exits:
#   0  success (JSON emitted; may be `[]`)
#   1  usage / generic error
set -euo pipefail

usage() { echo "Usage: $0 <pr-number>" >&2; exit 1; }

[[ $# -eq 1 ]] || usage
PR="$1"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
BODY=$(gh pr view "$PR" --json body --jq .body)

# Extract marker. Default to 0 if missing.
MARKER=$(grep -oE '<!-- last-addressed-comment: [0-9]+ -->' <<<"$BODY" \
  | grep -oE '[0-9]+' \
  | head -1)
MARKER="${MARKER:-0}"

# Each fetch defaults to `[]` on gh failure so jq -s never sees a null input
# (which would propagate through `add` to break the downstream map).
ISSUE_COMMENTS=$(gh api "repos/$REPO/issues/$PR/comments" --paginate 2>/dev/null \
  | jq '[.[] | {id, created_at, author: .user.login, body, kind: "issue"}]' \
  || echo "[]")
REVIEW_COMMENTS=$(gh api "repos/$REPO/pulls/$PR/comments" --paginate 2>/dev/null \
  | jq '[.[] | {id, created_at, author: .user.login, body, kind: "review", path}]' \
  || echo "[]")

jq -s --argjson marker "$MARKER" '
  add
  | map(select(.id > $marker))
  | sort_by(.created_at)
' <<<"$ISSUE_COMMENTS"$'\n'"$REVIEW_COMMENTS"
