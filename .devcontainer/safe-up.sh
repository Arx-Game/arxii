#!/usr/bin/env bash
# The CLI can print the fully expanded Compose environment, including secrets.
# Neither stream is safe to forward or save, including on error.
set -u
if devcontainer up --workspace-folder . "$@" >/dev/null 2>&1; then
    echo "Devcontainer started."
else
    status=$?
    echo "Devcontainer startup failed (exit $status); output suppressed because it may contain credentials." >&2
    exit "$status"
fi
