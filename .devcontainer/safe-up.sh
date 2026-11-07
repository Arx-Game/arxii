#!/usr/bin/env bash
# CLI diagnostics may contain the fully expanded Compose environment.
set -u
umask 077
log=$(mktemp "${TMPDIR:-/tmp}/arxii-devcontainer.XXXXXXXX") || {
    echo "Could not create a private startup log; devcontainer was not started." >&2
    exit 1
}
# Git Bash on Windows does not enforce Unix mode bits as an NTFS ACL.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        if ! MSYS_NO_PATHCONV=1 icacls.exe "$(cygpath -w "$log")" /inheritance:r /grant:r "${USERNAME}:(F)" '*S-1-5-18:(F)' >/dev/null 2>&1; then
            rm -f -- "$log"
            echo "Could not restrict startup log access; devcontainer was not started." >&2
            exit 1
        fi
        ;;
esac
if devcontainer up --workspace-folder . "$@" >"$log" 2>&1; then
    rm -f -- "$log"
    echo "Devcontainer started."
else
    status=$?
    echo "Devcontainer startup failed (exit $status). Private diagnostic log: $log" >&2
    echo "The log may contain credentials. Inspect locally; do not share it unredacted." >&2
    exit "$status"
fi
