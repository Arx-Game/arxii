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

# Substitute. Use a sentinel-free escape pass with python-like sed safety: use
# a delimiter unlikely to appear in values (|). Escape | in values just in case.
substitute() {
  local key="$1" value="$2"
  local escaped
  escaped=$(printf '%s' "$value" | sed 's/|/\\|/g')
  # Multiline-safe substitution via awk.
  awk -v k="{{${key}}}" -v v="$escaped" '
    {
      while ((idx = index($0, k)) > 0) {
        $0 = substr($0, 1, idx-1) v substr($0, idx + length(k))
      }
      print
    }
  '
}

BODY=$(cat "$TEMPLATE")
BODY=$(echo "$BODY" | substitute "issue_number" "$ISSUE")
BODY=$(echo "$BODY" | substitute "summary" "$SUMMARY")
BODY=$(echo "$BODY" | substitute "followup_list" "$FOLLOWUP_LIST")
BODY=$(echo "$BODY" | substitute "ran_or_skipped" "$RAN_OR_SKIPPED")
BODY=$(echo "$BODY" | substitute "spec_link" "$SPEC_LINK")
BODY=$(echo "$BODY" | substitute "sync_summary" "$SYNC_SUMMARY")

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

URL=$(gh pr create --base main --head "$BRANCH" --title "$PR_TITLE" --body-file "$BODY_FILE")
echo "$URL" | grep -oE '[0-9]+$'
