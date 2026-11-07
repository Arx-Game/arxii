#!/usr/bin/env bash
# CLI diagnostics may contain the fully expanded Compose environment.
set -u
umask 077
log=$(mktemp "${TMPDIR:-/tmp}/arxii-devcontainer.XXXXXXXX") || {
    echo "Could not create a private startup log; devcontainer was not started." >&2
    exit 1
}
if devcontainer up --workspace-folder . "$@" >"$log" 2>&1; then
    rm -f -- "$log"
    echo "Devcontainer started."
else
    status=$?
    echo "Devcontainer startup failed (exit $status). Private diagnostic log: $log" >&2
    echo "The log may contain credentials. Inspect locally; do not share it unredacted." >&2
    exit "$status"
fi
