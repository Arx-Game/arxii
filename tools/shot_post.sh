#!/usr/bin/env bash
# shot_post.sh [--dry-run] <pr-or-issue-number> <png>...   (just shot-post, #5310)
#
# Posts screenshots of the running app to a PR (or an issue, before the PR exists)
# without touching any branch:
#   1. stores the PNGs as blobs on an orphan commit made with git plumbing (the
#      worktree and the index are never touched);
#   2. pushes that commit to refs/evidence/<number>/<stamp>. No workflow runs on
#      that ref, a clone does not fetch it, and nothing rebases or force-pushes it,
#      so the links stay valid for as long as the ref exists;
#   3. checks every image URL answers 200 with image/png;
#   4. adds the images to one comment on the PR (it updates its own earlier comment
#      rather than posting a second one);
#   5. prints the Markdown so the same images can go in the PR body, which the
#      frontend-screenshot check in spec-evidence.yml reads.
#
# Never delete an evidence ref: a merged PR's screenshots are linked through it.
#
# Exits: 0 posted (or dry run), 1 usage or a failed step.
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi
if [[ $# -lt 2 ]]; then
  echo "Usage: just shot-post [--dry-run] <pr-or-issue-number> <png>..." >&2
  exit 1
fi
NUMBER="$1"
shift
[[ "$NUMBER" =~ ^[0-9]+$ ]] || { echo "ERROR: the PR or issue number must be numeric" >&2; exit 1; }

readonly MAX_FILES=20
readonly MAX_BYTES=$((5 * 1024 * 1024))
readonly PNG_MAGIC="89504e470d0a1a0a"
[[ $# -le $MAX_FILES ]] || { echo "ERROR: at most $MAX_FILES images per post" >&2; exit 1; }

entries=""
names=()
index=0
for png in "$@"; do
  [[ -f "$png" ]] || { echo "ERROR: not a file: $png" >&2; exit 1; }
  magic="$(head -c 8 "$png" | od -An -tx1 | tr -d ' \n')"
  [[ "$magic" == "$PNG_MAGIC" ]] || { echo "ERROR: not a PNG: $png" >&2; exit 1; }
  size="$(stat -c %s "$png")"
  (( size <= MAX_BYTES )) || { echo "ERROR: over 5 MB: $png" >&2; exit 1; }
  index=$((index + 1))
  # `just shot` already numbers its files; renumber across this post instead.
  base="$(basename "$png" .png | sed -E 's/^[0-9]+-//' | tr -c 'A-Za-z0-9._-' '-' | sed 's/-*$//')"
  name="$(printf '%02d-%s.png' "$index" "$base")"
  blob="$(git hash-object -w -- "$png")"
  entries+="$(printf '100644 blob %s\t%s' "$blob" "$name")"$'\n'
  names+=("$name")
done

tree="$(printf '%s' "$entries" | git mktree)"
commit="$(git commit-tree "$tree" -m "Screenshots for #$NUMBER (just shot-post)")"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
ref="refs/evidence/$NUMBER/$stamp"
repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
head_sha="$(git rev-parse --short HEAD)"

markdown=""
for name in "${names[@]}"; do
  markdown+="![${name%.png}](https://raw.githubusercontent.com/$repo/$commit/$name)"$'\n'
done

if [[ "$DRY_RUN" == 1 ]]; then
  echo "dry run: would push $commit to $ref and post:" >&2
  printf '%s' "$markdown"
  exit 0
fi

git push origin "${commit}:${ref}" >&2

# raw.githubusercontent.com can lag a push by a few seconds.
for name in "${names[@]}"; do
  url="https://raw.githubusercontent.com/$repo/$commit/$name"
  ok=0
  for _ in 1 2 3 4 5 6; do
    if curl -fsSI "$url" | grep -qi '^content-type: image/png'; then
      ok=1
      break
    fi
    sleep 5
  done
  (( ok )) || { echo "ERROR: $url does not load; the push went to $ref" >&2; exit 1; }
done

marker="<!-- shot-post -->"
section="**Screenshots of the running app** at \`$head_sha\` ($stamp, ref \`$ref\`)"$'\n\n'"$markdown"
me="$(gh api user --jq .login)"
existing="$(gh api "repos/$repo/issues/$NUMBER/comments" --paginate \
  --jq ".[] | select(.user.login == \"$me\") | select(.body | startswith(\"$marker\")) | .id" \
  | tail -n 1)"
if [[ -n "$existing" ]]; then
  body="$(gh api "repos/$repo/issues/comments/$existing" --jq .body)"$'\n\n'"$section"
  url="$(gh api -X PATCH "repos/$repo/issues/comments/$existing" -f body="$body" --jq .html_url)"
else
  url="$(gh api "repos/$repo/issues/$NUMBER/comments" -f body="$marker"$'\n'"$section" \
    --jq .html_url)"
fi
echo "posted: $url" >&2
echo "Paste into the PR body (the frontend-screenshot check reads it):" >&2
printf '%s' "$markdown"
