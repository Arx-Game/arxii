#!/usr/bin/env bash
# arx-test-scratch.sh — wrap `arx test` and mirror combined stdout+stderr to
# .claude/scratch/<name>, exiting with the real test-runner exit code.
#
# Usage:
#   bash .claude/scripts/arx-test-scratch.sh <name> [arx test args...]
#
# Examples:
#   bash .claude/scripts/arx-test-scratch.sh missions.log world.missions --keepdb
#   bash .claude/scripts/arx-test-scratch.sh regression.txt
#
# <name> must be a bare filename (no slashes, no `..`) — output lands at
# .claude/scratch/<name>. The whole .claude/ tree is gitignored.
#
# Output is BOTH streamed to the terminal AND captured to the file via `tee`,
# so the caller sees progress in real time. `set -o pipefail` + `${PIPESTATUS}`
# preserves the test runner's exit code through the tee pipe.
#
# This script is referenced by the `test-scratch` and `regression-scratch`
# recipes in the project justfile. It exists so the canonical output-capture
# workflow (per project memory) avoids the per-file "sensitive file" Bash
# prompts that fire when redirecting to varying filenames.

set -e
set -o pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <name> [arx test args...]" >&2
    exit 2
fi

NAME="$1"
shift

# Path-traversal / shape guards: <name> must be a single path segment with
# no separators and no parent-dir references.
case "$NAME" in
    */* | *\\* | *..* | "")
        echo "error: <name> must be a bare filename (got: '$NAME')" >&2
        exit 2
        ;;
esac

# Resolve the project root from this script's location so the recipe works
# regardless of which working directory `just` invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRATCH_DIR="$PROJECT_ROOT/.claude/scratch"
OUT_FILE="$SCRATCH_DIR/$NAME"

mkdir -p "$SCRATCH_DIR"

# Auto-confirm Evennia's destroy-test-DB prompt by piping "yes" upfront.
# tee captures combined stdout+stderr; pipefail propagates the runner's exit.
echo "yes" | uv run arx test "$@" 2>&1 | tee "$OUT_FILE"
exit "${PIPESTATUS[0]}"
