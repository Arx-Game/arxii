#!/usr/bin/env bash
# post-merge-cleanup.sh [--dry-run] <branch> <pr-number>
#
# Updates the main working tree, removes the branch's worktree, deletes the
# branch, and emits a JSON summary of related-issue actions. Dirty-tree
# handling: exits non-zero if the branch's worktree has uncommitted (tracked)
# changes — never stashes or resets. Squash-merge handling: tries safe-delete
# first; falls back to -D only after gh pr view confirms merged.
#
# **Cwd-independent (#2060):** all operations target resolved directories via
# `git -C` — main-branch ops run in the primary working tree, branch deletion
# runs after removing the branch's linked worktree. The old code ran bare
# `git checkout main` + `git branch -d`, which failed from inside a worktree
# ("'main' is already checked out at ...", "cannot delete branch checked out
# at ...").
#
# Exits:
#   0  success (cleanup complete, JSON emitted)
#   1  usage / generic error
#   8  branch worktree has uncommitted changes (named files listed in stderr)
#   9  branch unsafe to delete (PR not merged)
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Sourced at runtime via $SCRIPT_DIR; shellcheck can't resolve the dynamic path.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_wt-helpers.sh"

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

MAIN_WT=$(wt_main_path)
BRANCH_WT=$(wt_for_branch "$BRANCH")

# Dirty-tree check runs against the branch's worktree (the thing we're about to
# remove) when it exists, else the main tree. Tracked changes only — a worktree
# always carries untracked build artifacts (.venv, __pycache__), which are not
# work to protect and are handled by --force on removal below.
CHECK_DIR="${BRANCH_WT:-$MAIN_WT}"
if ! git -C "$CHECK_DIR" diff --quiet || ! git -C "$CHECK_DIR" diff --cached --quiet; then
  echo "ERROR: working tree at $CHECK_DIR has uncommitted changes:" >&2
  git -C "$CHECK_DIR" status --short >&2
  echo "Commit, stash, or discard them before running post-merge cleanup." >&2
  exit 8
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would:"
  echo "  1. git -C $MAIN_WT checkout main && git pull --ff-only"
  echo "  2. git worktree remove --force ${BRANCH_WT:-<none>}"
  echo "  3. git -C $MAIN_WT branch -d $BRANCH (fallback -D if PR confirmed merged)"
  echo "  4. emit JSON of linked-issue actions"
  exit 0
fi

git -C "$MAIN_WT" checkout main --quiet
git -C "$MAIN_WT" pull --ff-only --quiet

# Remove the branch's linked worktree first — a branch checked out in a worktree
# cannot be deleted. --force because the worktree carries untracked build
# artifacts (tracked changes already gated to exit 8 above).
if [[ -n "$BRANCH_WT" ]]; then
  git -C "$MAIN_WT" worktree remove --force "$BRANCH_WT"
fi

if git -C "$MAIN_WT" branch -d "$BRANCH" 2>/dev/null; then
  DELETE_METHOD="safe"
else
  # gh pr view has no boolean `merged` field; state == "MERGED" is the
  # definitive indicator. Capture gh failures separately so the user sees
  # "auth/network error" rather than "PR not merged" when the API call dies.
  if ! PR_STATE=$(gh pr view "$PR" --json state --jq .state 2>&1); then
    echo "ERROR: could not query PR #$PR state (gh said: $PR_STATE)" >&2
    exit 1
  fi
  if [[ "$PR_STATE" != "MERGED" ]]; then
    echo "ERROR: PR #$PR state is $PR_STATE, not MERGED; refusing to force-delete branch $BRANCH" >&2
    exit 9
  fi
  git -C "$MAIN_WT" branch -D "$BRANCH"
  DELETE_METHOD="forced (squash-merge)"
fi

# Verify auto-close behavior: list linked issues, see which are still open.
# A PR with no Closes/Fixes/Resolves lines is valid (e.g., docs-only or
# bootstrap PRs that predate the issue-driven workflow); grep returns 1
# on no matches, which `set -e` + pipefail would otherwise turn into a
# script abort. `|| true` keeps LINKED_ISSUES empty in that case.
PR_BODY=$(gh pr view "$PR" --json body --jq .body)
LINKED_ISSUES=$( { grep -oiE '(closes|fixes|resolves)[[:space:]]+#[0-9]+' <<<"$PR_BODY" \
  | grep -oE '[0-9]+' \
  | sort -u; } || true)

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
