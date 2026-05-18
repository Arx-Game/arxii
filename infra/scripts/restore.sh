#!/usr/bin/env bash
#
# restore.sh — DISASTER RECOVERY. Restores the database from a backup copy.
#
# This is DELIBERATELY SEPARATE from the stand-up button. Restoring OVERWRITES
# live data with a (possibly older) backup — running it by mistake against a
# healthy prod is the real "obliterate prod" path. It therefore:
#   - is never invoked by scripts/standup.sh,
#   - refuses to do anything without an explicit, unambiguous flag,
#   - prints loud warnings before any destructive step.
#
# T1 scaffold: the gate is real and active. The actual restore-from-Linode and
# restore-from-R2-offsite logic is wired in task T25 (and must support BOTH
# copies, per the 3-2-1 design).
set -euo pipefail

CONFIRMED=0

usage() {
  cat <<'EOF'
Usage: restore.sh --i-understand-this-overwrites [--source linode|r2]

  --i-understand-this-overwrites   REQUIRED. Restoring OVERWRITES live data.
  --source linode|r2               Which backup copy to restore from
                                   (default: linode primary).

Without the explicit flag this tool refuses and changes nothing.
EOF
}

log()  { printf '[restore] %s\n' "$*"; }
fail() { printf '[restore] REFUSING: %s\n' "$*" >&2; exit 1; }

SOURCE="linode"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --i-understand-this-overwrites) CONFIRMED=1; shift ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown argument: $1" ;;
  esac
done

[[ "${CONFIRMED}" -eq 1 ]] \
  || { usage; fail "explicit --i-understand-this-overwrites required; this OVERWRITES live data"; }
[[ "${SOURCE}" == "linode" || "${SOURCE}" == "r2" ]] \
  || fail "--source must be 'linode' or 'r2' (got: ${SOURCE})"

log "!!! THIS WILL OVERWRITE LIVE DATABASE DATA with the ${SOURCE} backup copy !!!"
log "    (separate from the stand-up button by design)"
# TODO(T25): restore from ${SOURCE} (linode primary OR r2 offsite) with verification.
fail "restore logic not yet wired (T1 scaffold); intentionally refusing to imply success"
