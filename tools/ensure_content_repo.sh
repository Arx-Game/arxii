#!/usr/bin/env bash
# Ensure the private content repo checkout exists at CONTENT_REPO_PATH.
#
# If the checkout already exists, this is a no-op.
# If CONTENT_REPO_URL is set and the checkout doesn't exist, clones it via `gh`.
# If CONTENT_REPO_URL is not set, prints a hint and exits 1.
#
# Both vars are read from src/.env or the environment. The repo is never
# named in the codebase — CONTENT_REPO_URL is a per-machine config value.
set -euo pipefail

ENV_FILE="src/.env"

# Read a var from .env or environment
read_var() {
    local key="$1"
    local value
    value=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)
    # Strip quotes
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    # Fall back to environment
    if [ -z "$value" ]; then
        value="${!key:-}"
    fi
    echo "$value"
}

path=$(read_var CONTENT_REPO_PATH)

if [ -z "$path" ]; then
    echo "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your"
    echo "local checkout of the private content repository."
    exit 1
fi

if [ -d "$path" ]; then
    # Checkout exists — nothing to do.
    exit 0
fi

url=$(read_var CONTENT_REPO_URL)

if [ -z "$url" ]; then
    echo "CONTENT_REPO_PATH is set to '$path' but the directory doesn't exist,"
    echo "and CONTENT_REPO_URL is not set. Either clone the content repo"
    echo "manually, or add CONTENT_REPO_URL to src/.env for auto-cloning."
    exit 1
fi

echo "Content checkout not found at $path — cloning from $url"
if ! gh repo clone "$url" "$path"; then
    echo "Clone failed. Ensure GH_TOKEN is set (see docs/devcontainer-setup.md)"
    echo "or clone the repo manually."
    exit 1
fi
