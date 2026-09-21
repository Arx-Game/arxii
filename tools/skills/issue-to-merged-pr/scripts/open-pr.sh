#!/usr/bin/env bash
# open-pr.sh [--dry-run] <branch> <issue-number> [followup-issue-numbers...]
#
# Pushes the branch (--force-with-lease if it was rebased) and opens a PR
# whose body is composed from templates/pr-body.md with substitutions:
#   {{issue_number}}, {{spec_gate_status}}, {{summary}}, {{followup_list}},
#   {{ran_or_skipped}}, {{discovery_lane}}, {{brainstorm_demo_summary}},
#   {{quality_review_summary}}, {{sync_summary}}, {{evidence_file}}
#
# Required env vars (set exactly one):
#   PR_EVIDENCE_URL  - GitHub issue/PR comment containing the review report
#                       (PREFERRED - nothing lands in the repo's history)
#   PR_EVIDENCE_FILE - a committed report (repo path only, e.g. "docs/reviews/<slug>.md")
#                       squash-merges into main; use only when the evidence itself
#                       should be permanent, versioned project history, not for a
#                       throwaway scratch path (post that as a comment via
#                       PR_EVIDENCE_URL instead - see SKILL.md's evidence section)
#
# Optional env vars (used as substitution sources if set):
#   PR_SUMMARY              - replaces {{summary}} (default: "(no summary provided)")
#   PR_RAN_OR_SKIPPED       - replaces {{ran_or_skipped}} (default: "ran")
#   PR_DISCOVERY_LANE       - optional rationale note; lane is derived and checked
#   PR_BRAINSTORM_DEMO      - required concise PRD/demo decision note
#   PR_QUALITY_REVIEW       - required selected/skipped lane disposition note
#   PR_SYNC_SUMMARY         - replaces {{sync_summary}} (default: "(no rebase performed)")
#   PR_TITLE          - PR title (default: derived from issue title)
#
# Every PR opened by this script closes its issue. If the work is a partial
# step, file a child issue for the remaining scope and pass that child issue
# here instead of keeping the parent open with a Refs reference.
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
DISCOVERY_LANE="${PR_DISCOVERY_LANE:-}"
BRAINSTORM_DEMO_SUMMARY="${PR_BRAINSTORM_DEMO:-}"
QUALITY_REVIEW_SUMMARY="${PR_QUALITY_REVIEW:-}"
SYNC_SUMMARY="${PR_SYNC_SUMMARY:-(no rebase performed)}"
ISSUE_METADATA=$(gh issue view "$ISSUE" --json labels,body)
ISSUE_LABELS=$(jq -r '[.labels[].name] | join("\n")' <<<"$ISSUE_METADATA")
VALIDATOR="$SCRIPT_DIR/validate-discovery.sh"
VALIDATION_RESULT=$("$VALIDATOR" "$ISSUE" --allow-approved-legacy) || {
  echo "ERROR: discovery validation failed for issue #$ISSUE." >&2
  exit 1
}
if ! grep -qx "status:implementing" <<<"$ISSUE_LABELS"; then
  echo "ERROR: issue #$ISSUE must carry status:implementing before opening a PR." >&2
  exit 1
fi
has_issue_label() {
  grep -qx "$1" <<<"$ISSUE_LABELS"
}
if ! has_issue_label spec:approved && [[ "$VALIDATION_RESULT" != *"lane=lightweight state=complete"* ]]; then
  echo "ERROR: issue #$ISSUE requires spec:approved unless it has a complete lightweight discovery marker." >&2
  exit 1
fi
if [[ "$VALIDATION_RESULT" == *"legacy-approved"* ]]; then
  VALIDATED_LANE="legacy-approved"
else
  VALIDATED_LANE=$(sed -E 's/.*lane=([^ ]+) state=.*/\1/' <<<"$VALIDATION_RESULT")
fi
if [[ ! "$VALIDATED_LANE" =~ ^(lightweight|standard|heavyweight|legacy-approved)$ ]]; then
  echo "ERROR: discovery validator returned no usable lane for issue #$ISSUE." >&2
  exit 1
fi
if [[ -z "$DISCOVERY_LANE" ]]; then
  DISCOVERY_LANE="$VALIDATED_LANE: validated from issue body"
elif [[ "$DISCOVERY_LANE" != "$VALIDATED_LANE:"* ]]; then
  echo "ERROR: PR_DISCOVERY_LANE disagrees with the validated issue marker ($VALIDATED_LANE)." >&2
  exit 1
fi
if [[ -z "$BRAINSTORM_DEMO_SUMMARY" || "$BRAINSTORM_DEMO_SUMMARY" == *"not recorded"* ]]; then
  echo "ERROR: PR_BRAINSTORM_DEMO must record the PRD/demo decision or explicit lightweight non-applicability." >&2
  exit 1
fi
if [[ -z "$QUALITY_REVIEW_SUMMARY" || "$QUALITY_REVIEW_SUMMARY" != *"selected:"* || "$QUALITY_REVIEW_SUMMARY" != *"skipped:"* || "$QUALITY_REVIEW_SUMMARY" != *"disposition:"* ]]; then
  echo "ERROR: PR_QUALITY_REVIEW must include selected:, skipped:, and disposition: entries." >&2
  exit 1
fi
if has_issue_label spec:approved; then
  SPEC_GATE_STATUS="member-approved"
else
  SPEC_GATE_STATUS="validated-lightweight-bypass"
fi
EVIDENCE_REQUIRED=0
if grep -qx "review:evidence-required" <<<"$ISSUE_LABELS"; then
  EVIDENCE_REQUIRED=1
fi
EVIDENCE_FILE="${PR_EVIDENCE_FILE:-}"
EVIDENCE_URL="${PR_EVIDENCE_URL:-}"
if [[ "$EVIDENCE_REQUIRED" == "1" ]]; then
  if [[ -z "$EVIDENCE_FILE" && -z "$EVIDENCE_URL" ]]; then
    echo "ERROR: issue #$ISSUE requires review evidence; set PR_EVIDENCE_FILE or PR_EVIDENCE_URL." >&2
    exit 1
  fi
  REVIEWED_SHA=$(git rev-parse HEAD^1)
  if [[ -n "$EVIDENCE_URL" ]]; then
    if [[ "$EVIDENCE_URL" != https://github.com/*/issues/*#issuecomment-* && "$EVIDENCE_URL" != https://github.com/*/pull/*#issuecomment-* ]]; then
      echo "ERROR: PR_EVIDENCE_URL must be a GitHub issue or PR comment URL." >&2
      exit 1
    fi
    COMMENT_ID="${EVIDENCE_URL##*#issuecomment-}"
    EVIDENCE_TMP=$(mktemp)
    trap 'rm -f "$EVIDENCE_TMP"' EXIT
    REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    gh api "repos/$REPO/issues/comments/$COMMENT_ID" --jq .body > "$EVIDENCE_TMP"
    uv run python tools/validate_review_evidence.py "$EVIDENCE_TMP" --revision "$REVIEWED_SHA"
    EVIDENCE_REFERENCE="$EVIDENCE_URL"
  else
    uv run python tools/validate_review_evidence.py "$EVIDENCE_FILE" --revision "$REVIEWED_SHA"
    EVIDENCE_REFERENCE="$EVIDENCE_FILE"
  fi
else
  EVIDENCE_REFERENCE="not required for this issue"
fi
EVIDENCE_MARKER=""
EVIDENCE_STATUS="- Review evidence is not required; this issue is not labeled \`review:evidence-required\`."
if [[ "$EVIDENCE_REQUIRED" == "1" ]]; then
  EVIDENCE_MARKER="<!-- review-evidence-required -->"
  # The one place the report reference is shaped for the PR body. The
  # review-evidence check (REPORT_LINE in validate_review_evidence.py) accepts
  # a bare https URL or a backtick-wrapped path, never a bare path and never
  # double backticks. EVIDENCE_REFERENCE stays unwrapped everywhere above.
  # tools/tests/test_open_pr_body.py runs this script and asserts both shapes.
  if [[ "$EVIDENCE_REFERENCE" == https://* ]]; then
    REPORT_LINE="$EVIDENCE_REFERENCE"
  else
    REPORT_LINE="\`$EVIDENCE_REFERENCE\`"
  fi
  EVIDENCE_STATUS="- Report: $REPORT_LINE
- The local reviewer report is validated against the exact reviewed code revision before this PR is opened.
- A PASS requires concrete evidence for every mandatory criterion, including a visual checklist where applicable, and no unresolved findings."
fi

if [[ "${PR_KEEP_OPEN:-0}" == "1" ]]; then
  echo "ERROR: PR_KEEP_OPEN is no longer supported; file a child issue for remaining scope and close that issue." >&2
  exit 1
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
BODY=${BODY//\{\{spec_gate_status\}\}/$SPEC_GATE_STATUS}
BODY=${BODY//\{\{summary\}\}/$SUMMARY}
BODY=${BODY//\{\{followup_list\}\}/$FOLLOWUP_LIST}
BODY=${BODY//\{\{ran_or_skipped\}\}/$RAN_OR_SKIPPED}
BODY=${BODY//\{\{discovery_lane\}\}/$DISCOVERY_LANE}
BODY=${BODY//\{\{brainstorm_demo_summary\}\}/$BRAINSTORM_DEMO_SUMMARY}
BODY=${BODY//\{\{quality_review_summary\}\}/$QUALITY_REVIEW_SUMMARY}
BODY=${BODY//\{\{sync_summary\}\}/$SYNC_SUMMARY}
BODY=${BODY//\{\{evidence_file\}\}/$EVIDENCE_REFERENCE}
BODY=${BODY//\{\{evidence_marker\}\}/$EVIDENCE_MARKER}
BODY=${BODY//\{\{evidence_status\}\}/$EVIDENCE_STATUS}

# Keep the close contract mechanical: a future template edit cannot silently
# reintroduce a non-closing reference after this script has passed its checks.
FIRST_LINE=${BODY%%$'\n'*}
if [[ "$FIRST_LINE" != "Closes #${ISSUE}" && "$FIRST_LINE" != "Closes #${ISSUE}." ]]; then
  echo "ERROR: generated PR body must begin with 'Closes #${ISSUE}'." >&2
  exit 1
fi

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
