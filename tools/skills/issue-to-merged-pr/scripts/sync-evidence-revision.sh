#!/usr/bin/env bash
# Re-point a PR's review-evidence comment at the revision the gate will check.
#
# Only use after reviewing the current HEAD. Verified neutral updates carry the old
# report forward automatically; material changes require review and updated evidence.
# This script shows the diff, but does not itself perform a review.
#
# Usage: sync-evidence-revision.sh <pr-number> [--yes]
#   --yes  skip the confirmation when code changed between revisions
#
# Do not use merely to silence CI: first complete the review of the new revision.
set -euo pipefail

PR="${1:?usage: sync-evidence-revision.sh <pr-number> [--yes]}"
ASSUME_YES="${2:-}"

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
REPO_ROOT="$(git rev-parse --show-toplevel)"
NEW_REV="$(git rev-parse HEAD)"

BODY_FILE="$(mktemp)"
gh pr view "$PR" --json body --jq .body > "$BODY_FILE"

REPORT_LINE="$(grep -m1 '^- Report: ' "$BODY_FILE" || true)"
REPORT_REF="${REPORT_LINE#- Report: }"
REPORT_REF="${REPORT_REF//\`/}"
if [[ "$REPORT_REF" != https://github.com/*#issuecomment-* ]]; then
  echo "ERROR: PR #$PR's '- Report:' line is not a comment URL: ${REPORT_REF:-<missing>}" >&2
  echo "Evidence must live in a PR comment; see the skill's evidence section." >&2
  exit 2
fi
COMMENT_ID="${REPORT_REF##*#issuecomment-}"

REPORT_FILE="$(mktemp)"
gh api "repos/$REPO/issues/comments/$COMMENT_ID" --jq .body > "$REPORT_FILE"

REV_LINE="$(grep -m1 '^- Reviewed revision: ' "$REPORT_FILE" || true)"
OLD_REV="${REV_LINE#- Reviewed revision: }"
OLD_REV="${OLD_REV//\`/}"
OLD_REV="${OLD_REV// /}"
if [[ "$OLD_REV" == "$NEW_REV" ]]; then
  echo "Evidence revision already current ($NEW_REV). Nothing to do."
  exit 0
fi

echo "Evidence revision is stale."
echo "  report says: $OLD_REV"
echo "  gate checks: $NEW_REV  (resolved evidence revision)"
echo

if git cat-file -e "${OLD_REV}^{commit}" 2>/dev/null; then
  CHANGED="$(git diff --stat "$OLD_REV" "$NEW_REV" -- 2>/dev/null || true)"
  if [[ -n "$CHANGED" ]]; then
    echo "Code changed between those revisions:"
    while IFS= read -r line; do printf '  %s\n' "$line"; done <<< "$CHANGED"
    echo
    echo "The report claims a review of the OLD revision. Before restating it, decide"
    echo "whether those changes touch anything the review covered. If they do, re-verify"
    echo "and say so in the report; if they do not, prove it with a diff of the reviewed"
    echo "files rather than asserting it."
    if [[ "$ASSUME_YES" != "--yes" ]]; then
      # An agent's shell has no terminal and its stdin never closes, so a prompt there
      # waits forever (#4797). Without a terminal, stop and say how to proceed instead.
      if [[ ! -t 0 ]]; then
        echo "No terminal to confirm on. Judge the diff above, then re-run with --yes."
        echo "Report left unchanged."
        exit 3
      fi
      read -r -p "Restate the revision anyway? [y/N] " reply
      [[ "$reply" =~ ^[Yy]$ ]] || { echo "Aborted; report left unchanged."; exit 3; }
    fi
  else
    echo "No file changed between those revisions (history rewrite only)."
  fi
else
  echo "NOTE: $OLD_REV is not reachable here, so the diff could not be shown."
fi

python3 - "$REPORT_FILE" "$OLD_REV" "$NEW_REV" <<'PY'
import re, sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as fh:
    body = fh.read()
patched, count = re.subn(
    r"^- Reviewed revision: .*$",
    f"- Reviewed revision: `{new}`",
    body, count=1, flags=re.M,
)
if count != 1:
    raise SystemExit("could not find a '- Reviewed revision:' line to update")
with open(path, "w", encoding="utf-8") as fh:
    fh.write(patched)
PY

gh api -X PATCH "repos/$REPO/issues/comments/$COMMENT_ID" -F body=@"$REPORT_FILE" --jq .html_url

REPO_ROOT="$(git rev-parse --show-toplevel)"
(cd "$REPO_ROOT/src" && uv run python ../tools/validate_review_evidence.py \
    "$REPORT_FILE" --revision "$NEW_REV" --pr-body "$BODY_FILE")

echo "Evidence now names $NEW_REV and validates. Safe to push."
