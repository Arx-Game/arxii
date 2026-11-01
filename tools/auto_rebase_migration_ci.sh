#!/usr/bin/env bash
# CI driver for tools/auto_rebase_migration.py (#4879); run by
# .github/workflows/migration-conflict-rebase.yml from a full checkout of main.
#
# For each open, same-repo PR into main that changes max_migration.txt and is
# CONFLICTING: run the script on its head, then
#   resolved      -> push the merge commit (fast-forward only), comment, re-arm
#                    auto-merge if the merge queue dropped it for this conflict;
#   nothing to do -> leave it;
#   refused       -> comment the reason once per head SHA, push nothing.
#
# Env: GH_TOKEN (the push PAT), ONLY_PR (optional single PR number).
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?}"
MAX_PATH="src/world/migrations/max_migration.txt"
MARKER="<!-- migration-auto-rebase"
SCRATCH="$(mktemp -d)"

# Run main's copy of the script with main's venv, never the PR's: a PR opened before
# #4879 has no copy, and a PR's own copy must not decide what gets pushed. The graph
# check still loads the PR's models (it has to), so the token is stripped from that
# process's environment and the checkout persists no credential.
cp tools/auto_rebase_migration.py "$SCRATCH/auto_rebase_migration.py"
PY="$PWD/.venv/bin/python"
PUSH_URL="${PUSH_URL:-https://x-access-token:${GH_TOKEN:?}@github.com/${REPO}.git}"

git config user.name "arx-migration-rebase"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git fetch -q origin main

# Mergeability is computed lazily after main moves; UNKNOWN means "ask again".
mergeable_state() {
  local pr="$1" state=""
  for _ in 1 2 3 4 5 6 7 8; do
    state="$(gh pr view "$pr" --repo "$REPO" --json mergeable --jq .mergeable)"
    [ "$state" != "UNKNOWN" ] && break
    sleep 15
  done
  echo "$state"
}

touches_max_migration() {
  gh api "repos/$REPO/pulls/$1/files" --paginate --jq '.[].filename' | grep -qx "$MAX_PATH"
}

# The merge queue dropped the PR over a conflict and nobody disarmed it since.
dropped_for_conflict() {
  local last
  # shellcheck disable=SC2016  # GraphQL variables, not shell ones
  last="$(gh api graphql -F n="$1" -f owner="${REPO%/*}" -f name="${REPO#*/}" -f query='
    query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){
      pullRequest(number:$n){timelineItems(last:1,itemTypes:[AUTO_MERGE_ENABLED_EVENT,
        AUTO_MERGE_DISABLED_EVENT,ADDED_TO_MERGE_QUEUE_EVENT,REMOVED_FROM_MERGE_QUEUE_EVENT]){
        nodes{__typename ... on RemovedFromMergeQueueEvent{reason}}}}}}' \
    --jq '.data.repository.pullRequest.timelineItems.nodes[0] | "\(.__typename) \(.reason // "")"')"
  [ "$last" = "RemovedFromMergeQueueEvent merge_conflict" ]
}

evidence_required() {
  local issue
  issue="$(gh pr view "$1" --repo "$REPO" --json body --jq .body \
    | grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?) #[0-9]+' | head -1 | grep -oE '[0-9]+' || true)"
  [ -n "$issue" ] && gh api "repos/$REPO/issues/$issue/labels" --jq '.[].name' \
    | grep -qx "review:evidence-required"
}

already_commented() {
  gh api "repos/$REPO/issues/$1/comments" --paginate --jq '.[].body' \
    | grep -qF "$MARKER sha=$2 "
}

handle_pr() {
  local pr="$1" head_ref head_sha result code rearm="" cross
  # `set -e` does not apply inside a function called from `||`, so every step that
  # decides which tree the script runs on returns explicitly.
  cross="$(gh pr view "$pr" --repo "$REPO" --json isCrossRepository --jq .isCrossRepository)" \
    || return 1
  if [ "$cross" != "false" ]; then
    echo "#$pr: from a fork; CI cannot push there"
    return 0
  fi
  head_ref="$(gh pr view "$pr" --repo "$REPO" --json headRefName --jq .headRefName)" || return 1
  git fetch -q origin "refs/heads/$head_ref" || return 1
  head_sha="$(git rev-parse FETCH_HEAD)" || return 1
  git checkout -q --detach "$head_sha" || return 1
  result="$SCRATCH/$pr.json"

  set +e
  env -u GH_TOKEN -u TOKEN "$PY" "$SCRATCH/auto_rebase_migration.py" \
    --main-ref origin/main --result "$result"
  code=$?
  set -e

  local body="$SCRATCH/$pr.md"
  case "$code" in
    0)
      # Fast-forward only: if the author pushed meanwhile this is rejected, and the
      # next main push (or a manual dispatch) retries against their new head.
      if ! git push -q "$PUSH_URL" "HEAD:refs/heads/$head_ref"; then
        echo "::warning::#$pr: branch moved while fixing; skipped"
        return 0
      fi
      if dropped_for_conflict "$pr"; then
        if evidence_required "$pr"; then
          rearm="Not re-armed: this PR carries review evidence, whose revision has to be restated (\`sync-evidence-revision.sh\`) before \`enqueue-pr.sh\`."
        else
          gh pr merge "$pr" --repo "$REPO" --auto --squash || return 1
          rearm="The merge queue had dropped this PR for the conflict, so auto-merge is re-armed."
        fi
      elif evidence_required "$pr"; then
        rearm="This PR carries review evidence: restate its revision with \`sync-evidence-revision.sh\`."
      fi
      {
        echo "$MARKER sha=$(git rev-parse HEAD) status=resolved -->"
        echo "Main moved past this PR's migrations, and \`max_migration.txt\` was the only conflict, so CI merged main in and renumbered them (\`tools/auto_rebase_migration.py\`, #4879):"
        echo
        jq -r '.renames[] | "- `\(.old)` -> `\(.new)`"' "$result"
        echo
        echo "Only each file's \`arxii\` dependency changed. The script checked that against the AST, checked that main's migrations are untouched, and loaded the graph (one leaf, no missing migrations). Pull before your next push: \`git pull --ff-only\`."
        jq -r '.warnings[] | "- Not renamed in prose: \(.)"' "$result"
        [ -n "$rearm" ] && { echo; echo "$rearm"; }
      } > "$body"
      gh pr comment "$pr" --repo "$REPO" --body-file "$body" || return 1
      ;;
    3)
      echo "#$pr: nothing to do ($(jq -r .reason "$result"))"
      ;;
    *)
      if [ ! -s "$result" ]; then
        echo "::error::#$pr: auto_rebase_migration.py crashed (exit $code)"
        git merge --abort 2>/dev/null || true
        return 0
      fi
      if already_commented "$pr" "$head_sha"; then
        echo "#$pr: refused again at $head_sha; already commented"
      else
        {
          echo "$MARKER sha=$head_sha status=refused -->"
          echo "This PR conflicts with main on \`max_migration.txt\`, but CI did not fix it automatically (#4879), because:"
          echo
          echo '```'
          jq -r .reason "$result"
          echo '```'
          echo
          echo "Only a PR that adds one linear chain of migrations, with no other conflict, is handled. Use the manual recipe in \`tools/skills/issue-to-merged-pr/references/ci-merge-queue-gotchas.md\`."
        } > "$body"
        gh pr comment "$pr" --repo "$REPO" --body-file "$body" || return 1
      fi
      ;;
  esac
}

if [ -n "${ONLY_PR:-}" ]; then
  candidates="$ONLY_PR"
else
  candidates="$(gh pr list --repo "$REPO" --base main --state open --limit 200 \
    --json number,isCrossRepository --jq '.[] | select(.isCrossRepository | not) | .number')"
fi

for pr in $candidates; do
  touches_max_migration "$pr" || continue
  state="$(mergeable_state "$pr")"
  if [ "$state" != "CONFLICTING" ]; then
    echo "#$pr: $state; nothing to do"
    continue
  fi
  echo "::group::#$pr"
  handle_pr "$pr" || echo "::error::#$pr: failed; continuing with the next PR"
  git merge --abort 2>/dev/null || true
  git checkout -q --detach origin/main
  echo "::endgroup::"
done
