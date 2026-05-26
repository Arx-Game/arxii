#!/usr/bin/env bash
# open-pr.sh [--dry-run] <branch> <issue-number> [followup-issue-numbers...]
#
# Pushes the branch (--force-with-lease if it was rebased) and opens a PR
# whose body is composed from templates/pr-body.md with substitutions:
#   {{issue_number}}, {{summary}}, {{followup_list}},
#   {{ran_or_skipped}}, {{spec_link}}, {{sync_summary}}
#
# Optional env vars (used as substitution sources if set):
#   PR_SUMMARY        - replaces {{summary}}     (default: "(no summary provided)")
#   PR_RAN_OR_SKIPPED - replaces {{ran_or_skipped}} (default: "ran")
#   PR_SPEC_LINK      - replaces {{spec_link}}      (default: "")
#   PR_SYNC_SUMMARY   - replaces {{sync_summary}}   (default: "(no rebase performed)")
#   PR_TITLE          - PR title (default: derived from issue title)
#
# Emits the new PR number on stdout.
#
# Exits:
#   0  success (PR opened, or dry-run printed)
#   1  usage / generic error
set -euo pipefail

# bash 5.2+ defaults `patsub_replacement` ON, which makes `&` in the
# replacement string of `${var//pat/rep}` substitute with the matched
# pattern (sed-like). PR_SUMMARY content frequently contains `&` (e.g.,
# "Steps 8 & 9"), so leave this OFF so the substitution is literal.
shopt -u patsub_replacement

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 [--dry-run] <branch> <issue-number> [followup-issue-numbers...]" >&2
  exit 1
fi

BRANCH="$1"
ISSUE="$2"
shift 2
FOLLOWUPS=("$@")

# Locate template relative to this script.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEMPLATE="$SCRIPT_DIR/../templates/pr-body.md"
[[ -f "$TEMPLATE" ]] || { echo "ERROR: template not found: $TEMPLATE" >&2; exit 1; }

SUMMARY="${PR_SUMMARY:-(no summary provided)}"
RAN_OR_SKIPPED="${PR_RAN_OR_SKIPPED:-ran}"
SPEC_LINK="${PR_SPEC_LINK:-}"
SYNC_SUMMARY="${PR_SYNC_SUMMARY:-(no rebase performed)}"

# Build the follow-up list (markdown bullets) or "(none)".
if [[ ${#FOLLOWUPS[@]} -eq 0 ]]; then
  FOLLOWUP_LIST="(none)"
else
  FOLLOWUP_LIST=""
  for n in "${FOLLOWUPS[@]}"; do
    FOLLOWUP_LIST+="- #${n}"$'\n'
  done
  FOLLOWUP_LIST="${FOLLOWUP_LIST%$'\n'}"
fi

# Substitute via bash parameter expansion (`${var//pattern/replacement}`):
# multiline-safe, single-pass, and — critically — does NOT recurse into the
# replacement text. A value that itself contains "{{summary}}" gets inserted
# literally rather than triggering the infinite loop the prior awk-based
# implementation had.
BODY=$(cat "$TEMPLATE")
BODY=${BODY//\{\{issue_number\}\}/$ISSUE}
BODY=${BODY//\{\{summary\}\}/$SUMMARY}
BODY=${BODY//\{\{followup_list\}\}/$FOLLOWUP_LIST}
BODY=${BODY//\{\{ran_or_skipped\}\}/$RAN_OR_SKIPPED}
BODY=${BODY//\{\{spec_link\}\}/$SPEC_LINK}
BODY=${BODY//\{\{sync_summary\}\}/$SYNC_SUMMARY}

# Derive a PR title if not explicitly given.
if [[ -z "${PR_TITLE:-}" ]]; then
  ISSUE_TITLE=$(gh issue view "$ISSUE" --json title --jq .title 2>/dev/null || echo "Closes #${ISSUE}")
  PR_TITLE="$ISSUE_TITLE"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would open PR:"
  echo "  branch: $BRANCH"
  echo "  title:  $PR_TITLE"
  echo "  body:"
  while IFS= read -r line; do echo "    $line"; done <<< "$BODY"
  exit 0
fi

# Push. Use --force-with-lease unconditionally on this branch (no-op if not
# diverged; safe if rebased; rejects if upstream moved unexpectedly).
git push --force-with-lease --set-upstream origin "$BRANCH"

# Open the PR.
BODY_FILE=$(mktemp)
trap 'rm -f "$BODY_FILE"' EXIT
printf '%s' "$BODY" > "$BODY_FILE"

# gh pr create emits the PR URL; gh has no --json flag for create itself, but
# we can ask gh pr view for the number after the fact (more robust than
# regex-parsing the URL, which would silently break under set -e if the URL
# format gains a suffix).
URL=$(gh pr create --base main --head "$BRANCH" --title "$PR_TITLE" --body-file "$BODY_FILE")
PR_NUMBER=$(gh pr view "$URL" --json number --jq .number)
echo "$PR_NUMBER"
