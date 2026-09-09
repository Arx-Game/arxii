#!/usr/bin/env bash
# open-pr.sh [--dry-run] <branch> <issue-number> [followup-issue-numbers...]
#
# Pushes the branch (--force-with-lease if it was rebased) and opens a PR
# whose body is composed from templates/pr-body.md with substitutions:
#   {{issue_number}}, {{summary}}, {{followup_list}},
#   {{ran_or_skipped}}, {{sync_summary}}, {{evidence_file}}, {{link_verb}}
#
# Required env vars:
#   PR_EVIDENCE_FILE - tracked review report, validated against the reviewed code revision
#
# Optional env vars (used as substitution sources if set):
#   PR_SUMMARY        - replaces {{summary}}     (default: "(no summary provided)")
#   PR_RAN_OR_SKIPPED - replaces {{ran_or_skipped}} (default: "ran")
#   PR_SYNC_SUMMARY   - replaces {{sync_summary}} (default: "(no rebase performed)")
#   PR_CLOSE_ISSUE    - use Closes instead of Refs only with explicit completion (default: 0)
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
SYNC_SUMMARY="${PR_SYNC_SUMMARY:-(no rebase performed)}"
ISSUE_LABELS=$(gh issue view "$ISSUE" --json labels --jq '.labels[].name')
EVIDENCE_REQUIRED=0
if grep -qx "review:evidence-required" <<<"$ISSUE_LABELS"; then
  EVIDENCE_REQUIRED=1
fi
EVIDENCE_FILE="${PR_EVIDENCE_FILE:-}"
if [[ "$EVIDENCE_REQUIRED" == "1" ]]; then
  if [[ -z "$EVIDENCE_FILE" ]]; then
    echo "ERROR: issue #$ISSUE requires review evidence; set PR_EVIDENCE_FILE." >&2
    exit 1
  fi
  if [[ "$EVIDENCE_FILE" = /* || "$EVIDENCE_FILE" == *..* ]]; then
    echo "ERROR: PR_EVIDENCE_FILE must be repository-relative without '..'." >&2
    exit 1
  fi
  if ! git ls-files --error-unmatch "$EVIDENCE_FILE" >/dev/null 2>&1; then
    echo "ERROR: PR_EVIDENCE_FILE must name a tracked file: $EVIDENCE_FILE" >&2
    exit 1
  fi
  REVIEWED_SHA=$(git rev-parse HEAD^1)
  uv run python tools/validate_review_evidence.py "$EVIDENCE_FILE" --revision "$REVIEWED_SHA"
else
  EVIDENCE_FILE="${EVIDENCE_FILE:-not required for this issue}"
fi
EVIDENCE_MARKER=""
EVIDENCE_STATUS="- Review evidence is not required; this issue is not labeled \`review:evidence-required\`."
if [[ "$EVIDENCE_REQUIRED" == "1" ]]; then
  EVIDENCE_MARKER="<!-- review-evidence-required -->"
  EVIDENCE_STATUS="- Report: \`$EVIDENCE_FILE\`
- The report is validated against the exact reviewed code revision before this PR is opened.
- A PASS requires every mandatory criterion to have concrete evidence and no unresolved findings.
- A scoped or partial change uses \`Refs\` and links the remaining work; it does not claim umbrella completion."
fi
LINK_VERB="Refs"
if [[ "${PR_CLOSE_ISSUE:-0}" == "1" ]]; then
  LINK_VERB="Closes"
fi

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
BODY=${BODY//\{\{sync_summary\}\}/$SYNC_SUMMARY}
BODY=${BODY//\{\{evidence_file\}\}/$EVIDENCE_FILE}
BODY=${BODY//\{\{evidence_marker\}\}/$EVIDENCE_MARKER}
BODY=${BODY//\{\{evidence_status\}\}/$EVIDENCE_STATUS}
BODY=${BODY//\{\{link_verb\}\}/$LINK_VERB}

# Derive a PR title if not explicitly given.
if [[ -z "${PR_TITLE:-}" ]]; then
  ISSUE_TITLE=$(gh issue view "$ISSUE" --json title --jq .title 2>/dev/null || echo "Closes #${ISSUE}")
  PR_TITLE="$ISSUE_TITLE"
fi

# Guard: refuse to open a PR for an issue assigned to another session.
# Placed BEFORE the dry-run block so --dry-run exercises it too.
CURRENT_USER=$(gh api user --jq '.login')
ASSIGNEES=$(gh issue view "$ISSUE" --json assignees --jq '.assignees[].login' 2>/dev/null || true)
if [[ -n "$ASSIGNEES" ]] && ! grep -qx "$CURRENT_USER" <<<"$ASSIGNEES"; then
  echo "ERROR: issue #$ISSUE is assigned to someone else ($ASSIGNEES), not you ($CURRENT_USER)." >&2
  echo "Refusing to open a PR against another session's work. Run start-work.sh on your own issue." >&2
  exit 3
fi
# If unassigned, warn but proceed (the user's priority is "always open a PR").
if [[ -z "$ASSIGNEES" ]]; then
  echo "WARN: issue #$ISSUE is unassigned. Consider running start-work.sh to claim it." >&2
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
