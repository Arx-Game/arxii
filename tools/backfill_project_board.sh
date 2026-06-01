#!/usr/bin/env bash
# One-time, idempotent sweep that reconciles the existing backlog with the new
# automation: adds every OPEN issue to the org Project and sets its Status (from
# assignment) and Stage (from status:* / spec:* labels). Safe to re-run.
#
# Usage (needs a PAT that can write the project -- e.g. the maintainer PAT):
#   GH_TOKEN=<pat> tools/backfill_project_board.sh
# It falls back to `gh auth token` if GH_TOKEN/GITHUB_TOKEN are unset.
#
# See docs/project-board-automation.md for the full picture.
set -euo pipefail

: "${GITHUB_REPOSITORY:=Arx-Game/arxii}"
: "${PROJECT_NUMBER:=1}"
export GITHUB_REPOSITORY PROJECT_NUMBER
export GITHUB_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-$(gh auth token)}}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/project_board_sync.py" backfill
