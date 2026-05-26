#!/usr/bin/env bash
# sync-with-main.sh <branch>
#
# Fetches origin/main and integrates it into the named branch. Strategy
# depends on whether the branch has already been pushed to origin:
#
# - **Branch not on origin (local-only):** rebase. Clean linear history;
#   no force-push needed because the branch is local.
# - **Branch already on origin (pushed):** merge. Avoids rewriting
#   already-published history, so the subsequent `git push` is a
#   fast-forward and doesn't need `--force-with-lease` (which requires
#   user approval in restricted environments).
#
# On conflict: emits JSON listing conflicted files, conflict symbols
# (function/class names extracted from `git diff --unified=0` hunk headers
# against origin/main), and any open issues whose body/comments
# substring-match those file paths or symbols. Match is intentionally
# over-inclusive — prefers false positives to false negatives.
#
# Exits:
#   0  sync succeeded with no conflicts (no JSON emitted)
#   1  usage / generic error
#   4  sync produced conflicts (JSON emitted to stdout; sync left in progress)
set -euo pipefail

usage() {
  echo "Usage: $0 <branch>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage
BRANCH="$1"

git fetch origin --quiet
git checkout "$BRANCH" --quiet

# Decide rebase vs merge based on whether the branch is published.
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  SYNC_STRATEGY="merge"
  if git merge origin/main --no-edit; then
    exit 0
  fi
else
  SYNC_STRATEGY="rebase"
  if git rebase origin/main; then
    exit 0
  fi
fi

# Conflicts present. Collect conflicted files.
CONFLICTS=$(git diff --name-only --diff-filter=U)

# Collect conflict symbols from hunk headers vs origin/main.
# `git diff --unified=0 origin/main -- <file>` emits hunks with headers like
# `@@ ... @@ def my_func(...)` or `@@ ... @@ class MyClass:` for known languages.
SYMBOLS=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  HUNK_SYMBOLS=$(git diff --unified=0 origin/main -- "$f" 2>/dev/null \
    | grep -oE '@@[^@]+@@ .*' \
    | sed 's/^@@[^@]*@@ //' \
    | grep -oE '(def|class|function)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' \
    | awk '{print $2}' \
    || true)
  SYMBOLS="$SYMBOLS"$'\n'"$HUNK_SYMBOLS"
done <<<"$CONFLICTS"
SYMBOLS=$(echo "$SYMBOLS" | sed '/^$/d' | sort -u)

# Find potentially impacted issues. Fetch all open issues with body + comments.
OPEN_ISSUES=$(gh issue list --state open --limit 500 --json number,title,body)
IMPACTED="[]"

# Combine search terms.
TERMS=$(printf "%s\n%s\n" "$CONFLICTS" "$SYMBOLS" | sed '/^$/d' | sort -u)

while IFS= read -r issue_row; do
  NUM=$(jq -r '.number' <<<"$issue_row")
  TITLE=$(jq -r '.title' <<<"$issue_row")
  BODY=$(jq -r '.body // ""' <<<"$issue_row")
  COMMENTS=$(gh issue view "$NUM" --json comments --jq '.comments[].body' 2>/dev/null || echo "")
  HAYSTACK="$BODY"$'\n'"$COMMENTS"

  MATCHES=""
  while IFS= read -r term; do
    [[ -z "$term" ]] && continue
    if grep -qF -- "$term" <<<"$HAYSTACK"; then
      MATCHES="$MATCHES"$'\n'"$term"
    fi
  done <<<"$TERMS"
  MATCHES=$(echo "$MATCHES" | sed '/^$/d')

  if [[ -n "$MATCHES" ]]; then
    MATCH_JSON=$(jq -R . <<<"$MATCHES" | jq -s .)
    IMPACTED=$(jq --argjson m "$MATCH_JSON" \
      --arg num "$NUM" --arg title "$TITLE" \
      '. + [{number: ($num | tonumber), title: $title, matched_on: $m}]' \
      <<<"$IMPACTED")
  fi
done < <(jq -c '.[]' <<<"$OPEN_ISSUES")

CONFLICTS_JSON=$(echo "$CONFLICTS" | sed '/^$/d' | jq -R . | jq -s .)
# Drop blank lines BEFORE jq sees them — `echo ""` followed by `jq -R .` yields
# the string "" which `jq -s` wraps as `[""]`. The sed filter matches the
# guard CONFLICTS_JSON uses above.
SYMBOLS_JSON=$(echo "$SYMBOLS" | sed '/^$/d' | jq -R . | jq -s .)

jq -n \
  --argjson c "$CONFLICTS_JSON" \
  --argjson s "$SYMBOLS_JSON" \
  --argjson i "$IMPACTED" \
  --arg strategy "$SYNC_STRATEGY" \
  '{strategy: $strategy, conflicts: $c, conflict_symbols: $s, potentially_impacted_issues: $i}'

exit 4
