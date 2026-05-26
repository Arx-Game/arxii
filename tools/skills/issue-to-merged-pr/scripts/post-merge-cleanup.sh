#!/usr/bin/env bash
# post-merge-cleanup.sh [--dry-run] <branch> <pr-number>
#
# Switches to main, pulls, deletes the named branch, and emits a JSON
# summary of related-issue actions taken. Dirty-tree handling: exits
# non-zero if the working tree has uncommitted changes — never stashes
# or resets. Squash-merge handling: tries safe-delete first; falls back
# to -D only after gh pr view confirms merged: true.
#
# Exits:
#   0  success (cleanup complete, JSON emitted)
#   1  usage / generic error
#   8  working tree is dirty (named files listed in stderr)
#   9  branch unsafe to delete (PR not merged)
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 [--dry-run] <branch> <pr-number>" >&2
  exit 1
fi

BRANCH="$1"
PR="$2"
[[ "$PR" =~ ^[0-9]+$ ]] || { echo "ERROR: pr number must be numeric" >&2; exit 1; }

# Dirty-tree check.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree has uncommitted changes:" >&2
  git status --short >&2
  echo "Commit, stash, or discard them before running post-merge cleanup." >&2
  exit 8
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would:"
  echo "  1. git checkout main"
  echo "  2. git pull --ff-only"
  echo "  3. git branch -d $BRANCH (fallback -D if PR confirmed merged)"
  echo "  4. emit JSON of linked-issue actions"
  exit 0
fi

git checkout main --quiet
git pull --ff-only --quiet

if git branch -d "$BRANCH" 2>/dev/null; then
  DELETE_METHOD="safe"
else
  MERGED=$(gh pr view "$PR" --json merged --jq .merged)
  if [[ "$MERGED" != "true" ]]; then
    echo "ERROR: PR #$PR is not merged; refusing to force-delete branch $BRANCH" >&2
    exit 9
  fi
  git branch -D "$BRANCH"
  DELETE_METHOD="forced (squash-merge)"
fi

# Verify auto-close behavior: list linked issues, see which are still open.
PR_BODY=$(gh pr view "$PR" --json body --jq .body)
LINKED_ISSUES=$(grep -oiE '(closes|fixes|resolves)[[:space:]]+#[0-9]+' <<<"$PR_BODY" \
  | grep -oE '[0-9]+' \
  | sort -u)

ACTIONS="[]"
for issue in $LINKED_ISSUES; do
  STATE=$(gh issue view "$issue" --json state --jq .state 2>/dev/null || echo "UNKNOWN")
  ACTIONS=$(jq --arg num "$issue" --arg state "$STATE" \
    '. + [{issue: ($num | tonumber), state: $state, action: (if $state == "CLOSED" then "auto-closed" else "needs-attention" end)}]' \
    <<<"$ACTIONS")
done

jq -n \
  --arg branch "$BRANCH" \
  --arg method "$DELETE_METHOD" \
  --argjson actions "$ACTIONS" \
  '{branch_deleted: $branch, delete_method: $method, linked_issue_actions: $actions}'
