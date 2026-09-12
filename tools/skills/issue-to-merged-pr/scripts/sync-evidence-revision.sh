#!/usr/bin/env bash
# Re-point a PR's review-evidence comment at the revision the gate will check.
#
# Both `open-pr.sh` and the `review-evidence` CI job validate the report against
# `git rev-parse HEAD^1`. Every push after the report is written moves that
# target, so the report goes stale and the job fails. This restates it, and
# shows what changed between the old revision and the new one so the author
# decides whether the review still stands rather than rubber-stamping it.
#
# Usage: sync-evidence-revision.sh <pr-number> [--yes]
#   --yes  skip the confirmation when code changed between revisions
#
# Run it as the LAST step before every push once the evidence comment exists.
set -euo pipefail

PR="${1:?usage: sync-evidence-revision.sh <pr-number> [--yes]}"
ASSUME_YES="${2:-}"

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
NEW_REV="$(git rev-parse HEAD^1)"

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
echo "  gate checks: $NEW_REV  (HEAD^1)"
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
