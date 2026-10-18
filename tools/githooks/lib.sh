#!/usr/bin/env bash
# Sourced by the tracked hooks in tools/githooks/ (#4428). Not run directly.
#
# Resolves the pre-commit to run at the moment a hook fires, from the worktree that is
# committing or pushing. Nothing here is written at install time, so no installed hook
# names a worktree path that a later `git worktree remove` could strand.
#
# resolve_pre_commit sets PRE_COMMIT_CMD (an array) and returns 0, or returns 1 when no
# pre-commit can be found. Order: an explicit PRE_COMMIT_PYTHON, this worktree's venv, the
# main checkout's venv (a fresh worktree before `uv sync`), pre-commit on PATH, then uv.
resolve_pre_commit() {
  local top main_root candidate
  top=$(git rev-parse --show-toplevel) || return 1
  main_root=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")

  if [ -n "${PRE_COMMIT_PYTHON:-}" ] && [ -x "$PRE_COMMIT_PYTHON" ]; then
    PRE_COMMIT_CMD=("$PRE_COMMIT_PYTHON" -m pre_commit)
    return 0
  fi
  for candidate in "$top" "$main_root"; do
    if [ -x "$candidate/.venv/bin/python" ]; then
      PRE_COMMIT_CMD=("$candidate/.venv/bin/python" -m pre_commit)
      return 0
    fi
  done
  if command -v pre-commit >/dev/null 2>&1; then
    PRE_COMMIT_CMD=(pre-commit)
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    # shellcheck disable=SC2034  # read by the hook that sources this file
    PRE_COMMIT_CMD=(uv run --quiet --project "$top" pre-commit)
    return 0
  fi
  return 1
}
