#!/usr/bin/env bash
# comment-on-issue.sh [--dry-run] <issue-number> <body-path>
#
# Posts a comment on an existing issue. Body comes from a file.
#
# Exits:
#   0  success (comment posted, or dry-run printed)
#   1  usage / generic error
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 [--dry-run] <issue-number> <body-path>" >&2
  exit 1
fi

ISSUE="$1"
BODY_PATH="$2"

[[ "$ISSUE" =~ ^[0-9]+$ ]] || { echo "ERROR: issue number must be numeric" >&2; exit 1; }
[[ -f "$BODY_PATH" ]] || { echo "ERROR: body file not found: $BODY_PATH" >&2; exit 1; }

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] would post to issue #$ISSUE:"
  sed 's/^/    /' "$BODY_PATH"
  exit 0
fi

gh issue comment "$ISSUE" --body-file "$BODY_PATH"
