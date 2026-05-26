#!/usr/bin/env bash
# file-followup.sh [--dry-run] <title> <body-path> [labels...]
#
# Creates a new GitHub issue with the given title, body (read from file),
# and optional labels. Emits the new issue number on stdout.
#
# Exits:
#   0  success (issue created, or dry-run printed)
#   1  usage / generic error
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 [--dry-run] <title> <body-path> [labels...]" >&2
  exit 1
fi

TITLE="$1"
BODY_PATH="$2"
shift 2
LABELS=("$@")

if [[ ! -f "$BODY_PATH" ]]; then
  echo "ERROR: body file not found: $BODY_PATH" >&2
  exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would create issue:"
  echo "  title:  $TITLE"
  echo "  labels: ${LABELS[*]:-(none)}"
  echo "  body:"
  sed 's/^/    /' "$BODY_PATH"
  exit 0
fi

# Build gh args.
GH_ARGS=(issue create --title "$TITLE" --body-file "$BODY_PATH")
for label in "${LABELS[@]}"; do
  GH_ARGS+=(--label "$label")
done

# gh issue create prints the issue URL. Ask gh for the number directly after
# creation rather than regex-parsing the URL — robust to URL-format changes
# and to `set -e` aborting on a regex miss.
URL=$(gh "${GH_ARGS[@]}")
gh issue view "$URL" --json number --jq .number
