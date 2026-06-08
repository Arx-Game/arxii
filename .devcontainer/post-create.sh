#!/usr/bin/env bash
# Runs ONCE on container create, while the network is still open.
# Generates src/.env, installs project deps, applies DB schema.
set -euo pipefail

cd /workspaces/arxii
# Trust the workspace mise.toml first — mise activate skips PATH setup for an
# untrusted config and only prompts interactively afterward, which leaves the
# postCreate shell without uv/pnpm/etc. on PATH.
~/.local/bin/mise trust
eval "$(~/.local/bin/mise activate bash)"

# Git identity so commits made from inside the container land with the right
# author. ~/.gitconfig lives in the container's writable layer (not a named
# volume), so this needs to re-run on every fresh container — cheap and
# idempotent. Read each contributor's personal identity from dev.env
# (gitignored, per-contributor) so we don't have to hardcode anyone's name
# in the script.
if [[ -f .devcontainer/dev.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .devcontainer/dev.env
  set +a
fi
if [[ -n "${GIT_USER_NAME:-}" ]] && [[ -n "${GIT_USER_EMAIL:-}" ]]; then
  git config --global user.name "$GIT_USER_NAME"
  git config --global user.email "$GIT_USER_EMAIL"
else
  echo "[post-create] GIT_USER_NAME / GIT_USER_EMAIL not set in .devcontainer/dev.env." >&2
  echo "[post-create] Add them there (see sync-env.sh placeholders), or run" >&2
  echo "[post-create] 'git config --global user.name ...' yourself in the container." >&2
fi
# Safe-directory exemption: git in modern versions refuses to operate on a
# repo owned by a different uid than the current user. The bind-mounted repo
# is owned by whoever owns it on Windows, which isn't the container's vscode
# uid. Without this, every git command fails with "dubious ownership".
git config --global --add safe.directory /workspaces/arxii

# Named-volume mountpoints (.venv, frontend/node_modules) come up root-owned
# because they're sub-paths of a bind mount. Chown them before uv/pnpm try
# to write into them.
sudo /usr/local/bin/fix-volume-perms.sh

# Claude Code .claude.json relocation (issue #505).
#
# CLAUDE_CONFIG_DIR (set in docker-compose.yml) points Claude Code at
# /home/vscode/.claude/ for its config dir, so .claude.json lands INSIDE
# the arxii-claude-home named volume and persists across dc-down/dc-up.
#
# One-shot migration: if a pre-relocation .claude.json exists at the old
# default path (~/.claude.json) AND the new persisted location doesn't yet
# have one, move the file. This carries the user's existing login state
# forward on the first dc-up after this change lands, so they don't need
# to re-authenticate.
#
# Idempotent: subsequent runs see ~/.claude/.claude.json already present
# and skip. Never overwrites existing persisted state.
if [[ -f /home/vscode/.claude.json ]] && [[ ! -f /home/vscode/.claude/.claude.json ]]; then
  mv /home/vscode/.claude.json /home/vscode/.claude/.claude.json
  echo "[post-create] migrated ~/.claude.json -> ~/.claude/.claude.json (issue #505)"
fi

# settings.py requires SECRET_KEY and DATABASE_URL (django-environ, raises if
# missing). No .env ships in a fresh checkout. DATABASE_URL also arrives via
# compose env, but settings reads src/.env, so write it there too.
if [[ ! -f src/.env ]]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  cat > src/.env <<EOF
DEBUG=True
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgres://arxii:arxii@db:5432/arxiidev
EOF
fi

uv sync
pnpm install --dir frontend

# pre-commit hooks: install fresh inside the container.
#
# Background: if the host (Windows) ever ran `pre-commit install`, it baked
# its own absolute path into .git/config's core.hooksPath plus dropped a
# CRLF-shebang'd hook into .git/hooks/. Both survive the bind mount and
# silently bypass every commit's checks from inside Linux — git can't exec
# the CRLF shebang and `core.hooksPath` points at a non-existent Windows
# path. Unset the stale config, wipe any stale hook files, then reinstall.
git config --unset-all core.hooksPath 2>/dev/null || true
rm -f .git/hooks/pre-commit .git/hooks/pre-push
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Wait for the db service (bounded — never hang first-run forever), then
# apply schema (test-only DB, safe to recreate).
timeout 90 bash -c 'until pg_isready -h db -U arxii -d arxiidev >/dev/null 2>&1; do sleep 1; done' \
  || { echo "db service did not become ready within 90s" >&2; exit 1; }
uv run arx manage migrate

# Install required plugins idempotently. claude plugin commands are CLI-
# safe (no Claude Code session needed). The named volume at
# /home/vscode/.claude persists the plugin across container rebuilds,
# so this is fast on second and subsequent runs.
claude plugin marketplace add anthropics/claude-plugins-official 2>/dev/null || true
claude plugin install superpowers@claude-plugins-official 2>/dev/null || true

# Symlink in-repo skills into the user's Claude skills directory so they're
# discoverable by every session. -sfn is idempotent — re-runs cleanly. New
# skills committed to tools/skills/ appear on the next container creation.
# nullglob: if tools/skills/ is empty, the loop body should NOT run with the
# literal pattern (which would create a dangling "*" symlink).
mkdir -p /home/vscode/.claude/skills
shopt -s nullglob
for skill in /workspaces/arxii/tools/skills/*/; do
  name=$(basename "$skill")
  ln -sfn "$skill" "/home/vscode/.claude/skills/$name"
done
shopt -u nullglob
