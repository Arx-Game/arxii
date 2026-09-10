#!/usr/bin/env bash
# enqueue-pr.sh [--dry-run] <pr-number>
#
# Enables auto-merge (squash) on the PR. With the repo's merge queue enabled
# (#991), this hands the PR to the queue: once its required review + checks are
# satisfied, GitHub adds it to the queue, which re-tests it on top of main (and
# any earlier-queued PRs) and merges it in order. No manual re-sync with main,
# no manual merge click — the agent calls this after CI is green and exits; a
# human's approval is the only remaining gate.
#
# --auto does NOT require the PR to be mergeable yet; it arms the merge to
# happen later once requirements are met. Idempotent: a second call when
# auto-merge is already enabled is a no-op success.
#
# Exits:
#   0  auto-merge enabled (or already enabled)
#   1  usage / generic error
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi

usage() { echo "Usage: $0 [--dry-run] <pr-number>" >&2; exit 1; }
[[ $# -eq 1 ]] || usage
PR="$1"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_wt-helpers.sh"
HEAD_REF=$(gh pr view "$PR" --json headRefName --jq .headRefName)
PR_BODY=$(gh pr view "$PR" --json body --jq .body)
LINKED_ISSUE=$(grep -oE '^(Refs|Closes) #[0-9]+' <<<"$PR_BODY" | grep -oE '[0-9]+' | head -1 || true)
ISSUE_LABELS=""
if [[ -n "$LINKED_ISSUE" ]]; then
  ISSUE_LABELS=$(gh issue view "$LINKED_ISSUE" --json labels --jq '.labels[].name')
fi
if grep -qx "review:evidence-required" <<<"$ISSUE_LABELS"; then
  EVIDENCE_FILE="${PR_EVIDENCE_FILE:-}"
  EVIDENCE_URL="${PR_EVIDENCE_URL:-}"
  if [[ -z "$EVIDENCE_FILE" && -z "$EVIDENCE_URL" ]]; then
    EVIDENCE_LINE=$(grep -E '^- Report: ' <<<"$PR_BODY" | head -1 || true)
    EVIDENCE_REFERENCE="${EVIDENCE_LINE#- Report: }"
    EVIDENCE_REFERENCE="${EVIDENCE_REFERENCE#\`}"
    EVIDENCE_REFERENCE="${EVIDENCE_REFERENCE%\`}"
    if [[ "$EVIDENCE_REFERENCE" == https://* ]]; then
      EVIDENCE_URL="$EVIDENCE_REFERENCE"
    else
      EVIDENCE_FILE="$EVIDENCE_REFERENCE"
    fi
  fi
  if [[ -z "$EVIDENCE_FILE" && -z "$EVIDENCE_URL" ]]; then
    echo "ERROR: labeled issue #$LINKED_ISSUE requires a review evidence report." >&2
    exit 1
  fi
  BRANCH_WT=$(wt_for_branch "$HEAD_REF")
  if [[ -z "$BRANCH_WT" ]]; then
    echo "ERROR: branch $HEAD_REF is not checked out; cannot validate its evidence report." >&2
    exit 1
  fi
  REVIEWED_SHA=$(git -C "$BRANCH_WT" rev-parse HEAD^1)
  if [[ -n "$EVIDENCE_URL" ]]; then
    if [[ "$EVIDENCE_URL" != https://github.com/*/issues/*#issuecomment-* && "$EVIDENCE_URL" != https://github.com/*/pull/*#issuecomment-* ]]; then
      echo "ERROR: evidence URL must be a GitHub issue or PR comment URL." >&2
      exit 1
    fi
    COMMENT_ID="${EVIDENCE_URL##*#issuecomment-}"
    EVIDENCE_TMP=$(mktemp)
    REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    gh api "repos/$REPO/issues/comments/$COMMENT_ID" --jq .body > "$EVIDENCE_TMP"
    uv run python "$BRANCH_WT/tools/validate_review_evidence.py" "$EVIDENCE_TMP" --revision "$REVIEWED_SHA"
    rm -f "$EVIDENCE_TMP"
  else
    if [[ "$EVIDENCE_FILE" = /* || "$EVIDENCE_FILE" == *..* ]]; then
      echo "ERROR: evidence report path must be repository-relative without '..'." >&2
      exit 1
    fi
    uv run python "$BRANCH_WT/tools/validate_review_evidence.py" "$BRANCH_WT/$EVIDENCE_FILE" --revision "$REVIEWED_SHA"
  fi

else
  echo "review evidence not required for issue #${LINKED_ISSUE:-unknown}"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[dry-run] gh pr merge $PR --auto --squash"
  exit 0
fi

out=$(gh pr merge "$PR" --auto --squash 2>&1) || {
  if grep -qi "already" <<<"$out"; then
    echo "auto-merge already enabled on #$PR"
    exit 0
  fi
  echo "$out" >&2
  exit 1
}
echo "auto-merge (squash) enabled on #$PR — the merge queue will merge it once approved + green"
