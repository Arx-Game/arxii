#!/usr/bin/env bash
# Generates .devcontainer/dev.env from src/.env with DATABASE_URL pointed at
# the compose db service. Bound on top of src/.env inside the container so
# the host's bare-metal .env (which targets a localhost Postgres) doesn't
# leak in. Idempotent — exits cleanly if dev.env already exists.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
src_env="${repo_root}/src/.env"
dev_env="${repo_root}/.devcontainer/dev.env"
db_url="postgres://arxii:arxii@db:5432/arxiidev"

if [[ -f "$dev_env" ]]; then
  exit 0
fi

if [[ ! -f "$src_env" ]]; then
  cat > "$dev_env" <<EOF
DEBUG=True
SECRET_KEY=$(head -c 50 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 50)
DATABASE_URL=${db_url}
# Set your git author identity here so post-create.sh wires it into the
# container's ~/.gitconfig and your commits attribute correctly.
GIT_USER_NAME=
GIT_USER_EMAIL=
EOF
  echo "Generated $dev_env (no src/.env found; minimal defaults written)."
  exit 0
fi

cp "$src_env" "$dev_env"

if grep -q '^DATABASE_URL=' "$dev_env"; then
  sed -i "s|^DATABASE_URL=.*\$|DATABASE_URL=${db_url}|" "$dev_env"
else
  echo "DATABASE_URL=${db_url}" >> "$dev_env"
fi

# Add empty GIT_USER_NAME / GIT_USER_EMAIL placeholders if not already
# present, so contributors see where to put their identity for
# post-create.sh to consume.
if ! grep -q '^GIT_USER_NAME=' "$dev_env"; then
  printf '\n# Git author identity — set these so post-create.sh wires them into the container.\n' >> "$dev_env"
  printf 'GIT_USER_NAME=\n' >> "$dev_env"
fi
if ! grep -q '^GIT_USER_EMAIL=' "$dev_env"; then
  printf 'GIT_USER_EMAIL=\n' >> "$dev_env"
fi

echo "Generated $dev_env from $src_env (DATABASE_URL → compose db service)."
