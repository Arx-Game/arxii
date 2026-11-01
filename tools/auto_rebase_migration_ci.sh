#!/usr/bin/env bash
# CI driver for tools/auto_rebase_migration.py (#4879, ADR-4879); run by
# .github/workflows/migration-conflict-rebase.yml from a checkout of main.
#
#   auto_rebase_migration_ci.sh check <out-dir>
#     Job with NO write token. For each open, same-repo PR into main that changes
#     max_migration.txt and is CONFLICTING, run the full script on its head,
#     including the graph check, which has to import the PR's code. Write one
#     <pr>.json per PR: the script's result plus head_ref, head_sha, main_sha.
#
#   auto_rebase_migration_ci.sh push <in-dir>
#     Job WITH the write token, which never runs PR code. For each result, re-derive
#     the merge from the same two commits with main's copy of the script, skipping
#     only the graph check (everything else reads PR files as data, via git and
#     ast.parse). Push only if the tree is byte-identical to the one the check job
#     graph-verified and neither ref has moved. Then comment, and re-arm auto-merge
#     if the queue dropped the PR for this conflict. Refusals are commented once
#     per head SHA.
#
# Env: GH_TOKEN (read-only in check, the push PAT in push), ONLY_PR (optional).
set -euo pipefail
# Never pipe `gh --paginate` straight into grep: grep stops at its first match (with
# -q, and also when its output is /dev/null), gh dies of SIGPIPE writing the next
# page, and pipefail turns the match into a miss. Capture the output, then grep it.

MODE="${1:?usage: auto_rebase_migration_ci.sh check|push <dir>}"
DIR="${2:?usage: auto_rebase_migration_ci.sh check|push <dir>}"
REPO="${GITHUB_REPOSITORY:?}"
MAX_PATH="src/world/migrations/max_migration.txt"
MARKER="<!-- migration-auto-rebase"
SCRATCH="$(mktemp -d)"
mkdir -p "$DIR"

# Always main's copy: a PR opened before #4879 has none, and a PR's own copy must
# never decide what is checked or pushed.
cp tools/auto_rebase_migration.py "$SCRATCH/auto_rebase_migration.py"

git config user.name "arx-migration-rebase"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git fetch -q origin main
MAIN_SHA="$(git rev-parse origin/main)"

pr_field() { gh pr view "$1" --repo "$REPO" --json "$2" --jq ".$2"; }

# Mergeability is computed lazily after main moves; UNKNOWN means "ask again".
mergeable_state() {
  local state=""
  for _ in 1 2 3 4 5 6 7 8; do
    state="$(pr_field "$1" mergeable)"
    [ "$state" != "UNKNOWN" ] && break
    sleep 15
  done
  echo "$state"
}

touches_max_migration() {
  local files
  files="$(gh api "repos/$REPO/pulls/$1/files" --paginate --jq '.[].filename')" || return 1
  grep -qx "$MAX_PATH" <<< "$files"
}

# Text that came from a PR (paths, the graph check's output) goes into a comment
# posted as the PAT's owner: no mentions, no breaking out of the code fence.
sanitize() { head -c 1500 | sed -e 's/`/'"'"'/g' -e 's/@/(at)/g'; }

reset_tree() {
  git merge --abort 2>/dev/null || true
  git checkout -q --force --detach "$MAIN_SHA"
}

# ------------------------------------------------------------------------- check

check_pr() {
  local pr="$1" head_ref head_sha code state
  [ "$(pr_field "$pr" isCrossRepository)" = "false" ] || { echo "#$pr: fork; skipped"; return 0; }
  [ "$(pr_field "$pr" baseRefName)" = "main" ] || { echo "#$pr: base is not main"; return 0; }
  touches_max_migration "$pr" || return 0
  state="$(mergeable_state "$pr")"
  [ "$state" = "CONFLICTING" ] || { echo "#$pr: $state; nothing to do"; return 0; }

  # `set -e` does not apply inside a function called from `||`, so every step that
  # picks the tree returns explicitly.
  head_ref="$(pr_field "$pr" headRefName)" || return 1
  git fetch -q origin "refs/heads/$head_ref" || return 1
  head_sha="$(git rev-parse FETCH_HEAD)" || return 1
  git checkout -q --detach "$head_sha" || return 1

  rm -f "$SCRATCH/r.json"
  set +e
  "$PY" "$SCRATCH/auto_rebase_migration.py" --main-ref origin/main --result "$SCRATCH/r.json"
  code=$?
  set -e
  if [ ! -s "$SCRATCH/r.json" ]; then
    echo "::error::#$pr: the script crashed (exit $code)"
    return 0
  fi
  jq --arg pr "$pr" --arg ref "$head_ref" --arg head "$head_sha" --arg main "$MAIN_SHA" \
    '. + {pr: $pr, head_ref: $ref, head_sha: $head, main_sha: $main}' \
    "$SCRATCH/r.json" > "$DIR/$pr.json"
}

# -------------------------------------------------------------------------- push

# The check job ran PR code, so its result files are data to verify, not facts:
# re-read the PR from the API and require it to match before acting on it.
live_pr_matches() {
  local pr="$1" json="$2" live
  live="$(gh pr view "$pr" --repo "$REPO" \
    --json state,isCrossRepository,baseRefName,headRefName,headRefOid \
    --jq '"\(.state) \(.isCrossRepository) \(.baseRefName) \(.headRefName) \(.headRefOid)"')" \
    || return 1
  [ "$live" = "OPEN false main $(jq -r '"\(.head_ref) \(.head_sha)"' "$json")" ]
}

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
  issue="$(pr_field "$1" body \
    | grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?) #[0-9]+' | head -1 | grep -oE '[0-9]+' || true)"
  [ -n "$issue" ] || return 1
  local labels
  labels="$(gh api "repos/$REPO/issues/$issue/labels" --paginate --jq '.[].name')" || return 1
  grep -qx "review:evidence-required" <<< "$labels"
}

already_commented() {
  local bodies
  bodies="$(gh api "repos/$REPO/issues/$1/comments" --paginate --jq '.[].body')" || return 1
  grep -qF "$MARKER sha=$2 " <<< "$bodies"
}

push_resolved() {
  local pr="$1" json="$2" head_ref head_sha want_tree got_tree rearm=""
  head_ref="$(jq -r .head_ref "$json")"
  head_sha="$(jq -r .head_sha "$json")"
  want_tree="$(jq -r .tree "$json")"
  if [ "$(jq -r .main_sha "$json")" != "$MAIN_SHA" ]; then
    echo "#$pr: main moved since the check; the next run redoes it"
    return 0
  fi
  git fetch -q origin "refs/heads/$head_ref" || return 1
  if [ "$(git rev-parse FETCH_HEAD)" != "$head_sha" ]; then
    echo "#$pr: the branch moved since the check; skipped"
    return 0
  fi
  git checkout -q --detach "$head_sha" || return 1
  if ! python3 "$SCRATCH/auto_rebase_migration.py" --main-ref origin/main \
    --skip-graph-check --result "$SCRATCH/again.json" > /dev/null; then
    echo "::error::#$pr: re-deriving the merge failed: $(jq -r .reason "$SCRATCH/again.json")"
    return 1
  fi
  got_tree="$(git rev-parse 'HEAD^{tree}')" || return 1
  # Everything the comment says comes from this re-derivation (no PR code ran),
  # never from the check job's file, which PR code could have rewritten.
  local mine="$SCRATCH/again.json"
  if [ "$got_tree" != "$want_tree" ]; then
    echo "::error::#$pr: re-derived tree $got_tree is not the checked $want_tree; not pushing"
    return 1
  fi

  # Fast-forward only, never --force. If the author pushed meanwhile it is rejected.
  if ! git push -q "${PUSH_URL:-https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git}" \
    "HEAD:refs/heads/$head_ref"; then
    echo "::warning::#$pr: push rejected (the branch moved); the next run retries"
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
    jq -r '.renames[] | "- `\(.old)` -> `\(.new)`"' "$mine"
    echo
    echo "They now run after main's $(jq -r '[.interleaved[] | "`\(.)`"] | join(", ")' "$mine"). No model those touch is named in this PR's migrations, and no model this PR's touch is named in them, so the new order changes nothing. Only each file's \`arxii\` dependency changed. The script checked that against the AST, checked that main's migrations are untouched, and loaded the graph (one leaf, no missing migrations)."
    if [ "$(jq '.doc_files | length' "$mine")" != "0" ]; then
      echo
      echo "The same names were updated in: $(jq -r '.doc_files | join(", ")' "$mine" | sanitize)"
    fi
    echo
    echo "Pull before your next push: \`git pull --ff-only\`. If you ran \`migrate\` on this branch, first run \`arx manage migrate arxii $(jq -r .base_tip "$mine")\`, because the old migration names will be gone after the pull."
    if [ -n "$rearm" ]; then echo; echo "$rearm"; fi
  } > "$SCRATCH/body.md"
  gh pr comment "$pr" --repo "$REPO" --body-file "$SCRATCH/body.md" || return 1
}

comment_refused() {
  local pr="$1" json="$2" head_sha
  head_sha="$(jq -r .head_sha "$json")"
  if already_commented "$pr" "$head_sha"; then
    echo "#$pr: refused again at $head_sha; already commented"
    return 0
  fi
  {
    echo "$MARKER sha=$head_sha status=refused -->"
    echo "This PR conflicts with main on \`max_migration.txt\`, but CI did not fix it automatically (#4879), because:"
    echo
    echo '```'
    jq -r .reason "$json" | sanitize
    echo '```'
    echo
    echo "Only a PR that adds one linear chain of migrations, with no other conflict, is handled. Use the manual recipe in \`tools/skills/issue-to-merged-pr/references/ci-merge-queue-gotchas.md\`."
  } > "$SCRATCH/body.md"
  gh pr comment "$pr" --repo "$REPO" --body-file "$SCRATCH/body.md" || return 1
}

# -------------------------------------------------------------------------- main

case "$MODE" in
  check)
    PY="$PWD/.venv/bin/python"
    if [ -n "${ONLY_PR:-}" ]; then
      [[ "$ONLY_PR" =~ ^[0-9]+$ ]] || { echo "::error::pr must be a number"; exit 1; }
      candidates="$ONLY_PR"
    else
      candidates="$(gh pr list --repo "$REPO" --base main --state open --limit 200 \
        --json number --jq '.[].number')"
    fi
    for pr in $candidates; do
      echo "::group::#$pr"
      check_pr "$pr" || echo "::error::#$pr: check failed; continuing"
      reset_tree
      echo "::endgroup::"
    done
    ;;
  push)
    shopt -s nullglob
    for json in "$DIR"/*.json; do
      pr="$(jq -r .pr "$json")"
      [[ "$pr" =~ ^[0-9]+$ ]] || continue
      echo "::group::#$pr"
      if ! live_pr_matches "$pr" "$json"; then
        echo "::warning::#$pr: result does not match the live PR; ignored"
        echo "::endgroup::"
        continue
      fi
      case "$(jq -r .status "$json")" in
        resolved) push_resolved "$pr" "$json" || echo "::error::#$pr: push step failed" ;;
        refused) comment_refused "$pr" "$json" || echo "::error::#$pr: comment failed" ;;
        *) echo "#$pr: $(jq -r .reason "$json")" ;;
      esac
      reset_tree
      echo "::endgroup::"
    done
    ;;
  *)
    echo "unknown mode: $MODE" >&2
    exit 2
    ;;
esac
