#!/usr/bin/env bash
# Install the pre-commit hook shim that runs tools/githooks/pre-commit (#3814, ADR-0296).
#
# Every worktree shares one hooks directory (the common .git/hooks), so one install covers
# them all. The shim runs the tracked hook from whichever worktree is committing, and falls
# back to pre-commit's own hook on a branch that predates it.
#
# Not core.hooksPath: .git/config sits on the bind mount shared with the Windows host, which
# is why .devcontainer/post-create.sh unsets it. This script unsets it too. Idempotent; the
# pre-push hook is left alone.
set -euo pipefail

common_dir=$(git rev-parse --path-format=absolute --git-common-dir)
python_bin=${PRE_COMMIT_PYTHON:-$(dirname "$common_dir")/.venv/bin/python}
hook="$common_dir/hooks/pre-commit"

git config --unset-all core.hooksPath 2>/dev/null || true
mkdir -p "$common_dir/hooks"
rm -f "$hook"

{
  printf '#!/usr/bin/env bash\n'
  printf '# Written by tools/githooks/install.sh (#3814). Re-run that script; do not edit.\n'
  printf 'PRE_COMMIT_PYTHON=%q\n' "$python_bin"
  cat <<'SHIM'
export PRE_COMMIT_PYTHON
here="$(cd "$(dirname "$0")" && pwd)"
tracked="$(git rev-parse --show-toplevel)/tools/githooks/pre-commit"
if [ -f "$tracked" ]; then
  exec bash "$tracked" "$@"
fi
# A branch cut before #3814 has no tracked hook: run pre-commit's own hook, as before.
args=(hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit --hook-dir "$here" -- "$@")
if [ -x "$PRE_COMMIT_PYTHON" ]; then
  exec "$PRE_COMMIT_PYTHON" -mpre_commit "${args[@]}"
elif command -v pre-commit >/dev/null 2>&1; then
  exec pre-commit "${args[@]}"
fi
echo '`pre-commit` not found. Did you forget to activate your virtualenv?' >&2
exit 1
SHIM
} >"$hook"

chmod +x "$hook"
echo "Installed $hook (pre-commit via $python_bin)"
