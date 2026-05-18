#!/usr/bin/env bash
# Runs ONCE on container create, while the network is still open.
# Generates src/.env, installs project deps, applies DB schema.
set -euo pipefail

cd /workspaces/arxii
eval "$(~/.local/bin/mise activate bash)"

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
