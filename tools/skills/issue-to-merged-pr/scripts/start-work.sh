#!/usr/bin/env bash
# start-work.sh <issue-number>
#
# Mandatory first call of the issue-to-merged-pr skill. Assigns the issue
# (via pickup-issue.sh) and creates an isolated worktree in one call, so the
# agent cannot begin work without claiming the issue.
#
# Emits JSON on stdout (pickup-issue.sh's output plus worktree_path).
#
# Exits:
#   0  success
#   1  usage / generic error
#   3  issue assigned to a different user (the duplicate-work guard)
set -euo pipefail

usage() { echo "Usage: $0 <issue-number>" >&2; exit 1; }
[[ $# -eq 1 ]] || usage
ISSUE="$1"
[[ "$ISSUE" =~ ^[0-9]+$ ]] || usage

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# 1. Claim: delegate to pickup-issue.sh (assigns + status:spec-draft + branch).
#    pickup-issue.sh exits 3 if the issue is assigned to a different user,
#    which is the duplicate-work guard.
PICKUP_OUTPUT=$(bash "$SCRIPT_DIR/pickup-issue.sh" "$ISSUE")
# pickup-issue.sh emits its JSON contract as the final stdout line. Guard against
# any stray stdout leaking ahead of it (the #2060 crash was git's "set up to
# track 'origin/main'." notice landing on stdout): take the last line and
# validate it before parsing, so a leak fails with a readable error + the raw
# output instead of a cryptic `jq: parse error: Invalid numeric literal`.
PICKUP_JSON=$(printf '%s\n' "$PICKUP_OUTPUT" | tail -n 1)
if ! jq -e . >/dev/null 2>&1 <<<"$PICKUP_JSON"; then
  echo "ERROR: pickup-issue.sh did not emit valid JSON on its final stdout line." >&2
  echo "Raw pickup output was:" >&2
  printf '%s\n' "$PICKUP_OUTPUT" >&2
  exit 1
fi
BRANCH=$(jq -r '.branch' <<<"$PICKUP_JSON")

# 1b. Re-verify assignment after claiming (closes the gap where pickup's
#     pre-check passed but a concurrent session assigned between the check
#     and the add-assignee). Refuse if the issue is now NOT assigned to us.
CURRENT_USER=$(gh api user --jq '.login')
ASSIGNEES=$(gh issue view "$ISSUE" --json assignees --jq '.assignees[].login')
if [[ -z "$ASSIGNEES" ]]; then
  echo "ERROR: issue #$ISSUE is unassigned — the claim did not take." >&2
  echo "(pickup's gh issue edit --add-assignee may have no-op'd, e.g. lacking triage permission). Re-run start-work.sh." >&2
  exit 3
fi
if ! grep -qx "$CURRENT_USER" <<<"$ASSIGNEES"; then
  echo "ERROR: issue #$ISSUE is assigned to someone else ($ASSIGNEES), not you ($CURRENT_USER)." >&2
  echo "Claim was lost (likely a concurrent session). Re-run start-work.sh." >&2
  exit 3
fi

# 2. Create the worktree at .claude/worktrees/<branch>.
#    Reuses the using-git-worktrees Step 1b pattern. The branch already exists
#    (pickup created it unchecked-out), so check it out WITHOUT -b.
LOCATION=".claude/worktrees"
mkdir -p "$LOCATION"
# Verify ignored (worktree skill mandates this). .claude is in .gitignore:87.
git check-ignore -q "$LOCATION" || {
  echo "ERROR: $LOCATION is not gitignored — refusing to create a worktree there." >&2
  echo "Add it to .gitignore first." >&2
  exit 1
}
WORKTREE_PATH="$LOCATION/$BRANCH"
if [ -d "$WORKTREE_PATH" ]; then
  echo "NOTE: worktree already exists at $WORKTREE_PATH (idempotent)." >&2
else
  git worktree add "$WORKTREE_PATH" "$BRANCH"
fi

# 3. Emit JSON: pickup fields + worktree_path.
jq -c --arg wt "$WORKTREE_PATH" '. + {worktree_path: $wt}' <<<"$PICKUP_JSON"
