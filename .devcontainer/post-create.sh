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
# idempotent. Values mirror the host's bare-metal identity.
git config --global user.name "Dave Brannigan"
git config --global user.email "surly.mime@gmail.com"
# Safe-directory exemption: git in modern versions refuses to operate on a
# repo owned by a different uid than the current user. The bind-mounted repo
# is owned by whoever owns it on Windows, which isn't the container's vscode
# uid. Without this, every git command fails with "dubious ownership".
git config --global --add safe.directory /workspaces/arxii

# Named-volume mountpoints (.venv, frontend/node_modules) come up root-owned
# because they're sub-paths of a bind mount. Chown them before uv/pnpm try
# to write into them.
sudo /usr/local/bin/fix-volume-perms.sh

# settings.py requires SECRET_KEY and DATABASE_URL (django-environ, raises if
# missing). No .env ships in a fresh checkout. DATABASE_URL also arrives via
# compose env, but settings reads src/.env, so write it there too.
if [ ! -f src/.env ]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  cat > src/.env <<EOF
DEBUG=True
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgres://arxii:arxii@db:5432/arxiidev
EOF
fi

uv sync
pnpm install --dir frontend

# Wait for the db service (bounded — never hang first-run forever), then
# apply schema (test-only DB, safe to recreate).
timeout 90 bash -c 'until pg_isready -h db -U arxii -d arxiidev >/dev/null 2>&1; do sleep 1; done' \
  || { echo "db service did not become ready within 90s" >&2; exit 1; }
uv run arx manage migrate

# First-time setup reminder. Plugin install is a Claude Code in-session slash
# command, not a CLI subcommand, so we can't run it from bash. The named
# volume at /home/vscode/.claude persists the plugin across container
# rebuilds — just need to run this once per fresh volume.
if [ ! -d /home/vscode/.claude/plugins/superpowers ]; then
  cat <<'EOF'

──────────────────────────────────────────────────────────────────────
  ONE-TIME SETUP STEP REMAINING
──────────────────────────────────────────────────────────────────────
  Inside the container (e.g. via `just dc-shell`), launch claude and run:

      /plugin install superpowers@claude-plugins-official

  The plugin persists in the /home/vscode/.claude named volume across
  container rebuilds; this message stops appearing once it's installed.
──────────────────────────────────────────────────────────────────────

EOF
fi
