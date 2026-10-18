#!/usr/bin/env bash
# Install the git hook shims that run the tracked hooks in tools/githooks/ (#3814, #4428, ADR-0296).
#
# Every worktree shares one hooks directory (the common .git/hooks), so one install covers
# them all. Each shim runs the tracked hook from whichever worktree is committing or pushing,
# and that hook resolves its own pre-commit at run time (tools/githooks/lib.sh). No shim
# names a worktree or venv path, so removing a worktree cannot strand the hooks (#4428).
#
# A branch cut before a tracked hook existed gets a fallback that runs pre-commit's own hook.
#
# Not core.hooksPath: .git/config sits on the bind mount shared with the Windows host, which
# is why .devcontainer/post-create.sh unsets it. This script unsets it too. Idempotent. It
# replaces any pre-commit-generated hook, which is what baked the stale path in.
set -euo pipefail

common_dir=$(git rev-parse --path-format=absolute --git-common-dir)
hooks_dir="$common_dir/hooks"

git config --unset-all core.hooksPath 2>/dev/null || true
mkdir -p "$hooks_dir"

write_shim() {
  local hook="$1"
  local path="$hooks_dir/$hook"
  rm -f "$path"
  sed "s/__HOOK__/$hook/g" >"$path" <<'SHIM'
#!/usr/bin/env bash
# Written by tools/githooks/install.sh (#4428). Re-run that script; do not edit.
# Names no worktree: the tracked hook resolves its own tooling when it runs.
top="$(git rev-parse --show-toplevel)"
tracked="$top/tools/githooks/__HOOK__"
if [ -f "$tracked" ]; then
  exec bash "$tracked" "$@"
fi
# A branch cut before the tracked hook: run pre-commit's own hook, as before.
here="$(cd "$(dirname "$0")" && pwd)"
args=(hook-impl --config=.pre-commit-config.yaml --hook-type=__HOOK__ --hook-dir "$here" -- "$@")
if [ -n "${PRE_COMMIT_PYTHON:-}" ] && [ -x "$PRE_COMMIT_PYTHON" ]; then
  exec "$PRE_COMMIT_PYTHON" -m pre_commit "${args[@]}"
elif [ -x "$top/.venv/bin/python" ]; then
  exec "$top/.venv/bin/python" -m pre_commit "${args[@]}"
elif command -v pre-commit >/dev/null 2>&1; then
  exec pre-commit "${args[@]}"
fi
echo '`pre-commit` not found. Run uv sync in this worktree or put pre-commit on PATH.' >&2
exit 1
SHIM
  chmod +x "$path"
  echo "Installed $path (runs tools/githooks/$hook)"
}

write_shim pre-commit
write_shim pre-push
