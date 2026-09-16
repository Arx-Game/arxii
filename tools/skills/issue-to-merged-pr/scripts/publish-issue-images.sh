#!/usr/bin/env bash
# publish-issue-images.sh [--dry-run] <issue-number> <branch> <image-path>...
#
# Uploads review/demo images to a pushed GitHub branch through the documented
# Contents API, then posts a Markdown comment to the issue using immutable
# raw.githubusercontent.com URLs. This is the fallback for environments where
# the interactive Artifact publisher is unavailable.
#
# The branch must already exist on origin. Each image is committed by the
# Contents API under .github/issue-evidence/<issue-number>/<timestamp>-<name>.
# The upload commit SHA is used in each image URL so later branch changes cannot
# silently replace the evidence.
#
# Exits:
#   0  success (comment URL printed, or dry-run body printed)
#   1  usage / generic error
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 [--dry-run] <issue-number> <branch> <image-path>..." >&2
  exit 1
fi

ISSUE="$1"
BRANCH="$2"
shift 2

[[ "$ISSUE" =~ ^[0-9]+$ ]] || {
  echo "ERROR: issue number must be numeric" >&2
  exit 1
}
[[ "$BRANCH" != *$'\n'* && "$BRANCH" != *$'\r'* ]] || {
  echo "ERROR: branch must not contain a newline" >&2
  exit 1
}

for image in "$@"; do
  [[ -f "$image" ]] || { echo "ERROR: image file not found: $image" >&2; exit 1; }
  case "${image,,}" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.svg) ;;
    *)
      echo "ERROR: image path must end in .png, .jpg, .jpeg, .gif, .webp, or .svg: $image" >&2
      exit 1
      ;;
  esac
done

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COMMENT_TMP=$(mktemp)
trap 'rm -f "$COMMENT_TMP"' EXIT
{
  echo "## Review/demo images"
  echo
  echo "These images are hosted from immutable commits on branch \`$BRANCH\`."
  echo
} > "$COMMENT_TMP"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would upload to $REPO on branch $BRANCH:"
  for image in "$@"; do
    name=$(basename "$image")
    remote_path=".github/issue-evidence/$ISSUE/$STAMP-$name"
    echo "  $image -> $remote_path"
  done
  echo "[dry-run] would post to issue #$ISSUE:"
  sed 's/^/    /' "$COMMENT_TMP"
  exit 0
fi

# Verify the target branch exists remotely before making Contents commits.
ENCODED_BRANCH=${BRANCH//\//%2F}
gh api "repos/$REPO/branches/$ENCODED_BRANCH" >/dev/null

for image in "$@"; do
  name=$(basename "$image")
  remote_path=".github/issue-evidence/$ISSUE/$STAMP-$name"
  encoded_tmp=$(mktemp)
  payload_tmp=$(mktemp)
  trap 'rm -f "$COMMENT_TMP" "$encoded_tmp" "$payload_tmp"' EXIT
  base64 --wrap=0 "$image" > "$encoded_tmp"
  # Keep the base64 out of argv. Several screenshots can exceed ARG_MAX when
  # sent as repeated `gh -f content=...` form arguments.
  jq -n \
    --arg message "docs: publish issue #$ISSUE review image $name" \
    --rawfile content "$encoded_tmp" \
    --arg branch "$BRANCH" \
    '{message: $message, content: ($content | rtrimstr("\n")), branch: $branch}' > "$payload_tmp"
  response=$(gh api -X PUT "repos/$REPO/contents/$remote_path" --input "$payload_tmp")
  rm -f "$encoded_tmp" "$payload_tmp"
  commit_sha=$(jq -r '.commit.sha' <<<"$response")
  [[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]] || {
    echo "ERROR: GitHub returned no commit SHA for $image" >&2
    exit 1
  }
  raw_url="https://raw.githubusercontent.com/$REPO/$commit_sha/$remote_path"
  echo "![${name}](${raw_url})" >> "$COMMENT_TMP"
done

gh issue comment "$ISSUE" --body-file "$COMMENT_TMP"
