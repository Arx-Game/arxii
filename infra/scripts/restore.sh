#!/usr/bin/env bash
#
# restore.sh — DISASTER RECOVERY. OVERWRITES the live DB from a backup copy.
#
# DELIBERATELY SEPARATE from the button (never invoked by standup.sh / the CI
# workflow). Running this against a healthy prod is the real "obliterate
# prod" path — hence the explicit gate. Supports BOTH 3-2-1 copies (linode
# primary OR r2 offsite). Operator-run, out-of-band. set +x, no secret echo.
#
# Required env (operator-supplied; read-capable creds, never the button's):
#   RESTORE_DB, RESTORE_DB_USER
#   linode: RESTORE_S3_ENDPOINT RESTORE_S3_REGION RESTORE_BUCKET
#           RESTORE_S3_ACCESS_KEY RESTORE_S3_SECRET_KEY   (a READ key)
#   r2:     RESTORE_R2_ENDPOINT RESTORE_R2_BUCKET
#           RESTORE_R2_ACCESS_KEY RESTORE_R2_SECRET_KEY
set -euo pipefail
set +x

CONFIRMED=0
SOURCE="linode"

usage() {
  cat <<'EOF'
Usage: restore.sh --i-understand-this-overwrites [--source linode|r2]
  --i-understand-this-overwrites   REQUIRED — restoring OVERWRITES live data.
  --source linode|r2               Which 3-2-1 copy (default: linode primary).
Without the explicit flag this refuses and changes nothing.
EOF
}

log()  { printf '[restore] %s\n' "$*"; }
fail() { printf '[restore] REFUSING: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --i-understand-this-overwrites) CONFIRMED=1; shift ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown argument: $1" ;;
  esac
done

[[ "${CONFIRMED}" -eq 1 ]] \
  || { usage; fail "explicit --i-understand-this-overwrites required (OVERWRITES live data)"; }
[[ "${SOURCE}" == "linode" || "${SOURCE}" == "r2" ]] \
  || fail "--source must be 'linode' or 'r2' (got: ${SOURCE})"

: "${RESTORE_DB:?set RESTORE_DB}"
: "${RESTORE_DB_USER:?set RESTORE_DB_USER}"

if [[ "${SOURCE}" == "linode" ]]; then
  ep="${RESTORE_S3_ENDPOINT:?}"; region="${RESTORE_S3_REGION:?}"; bucket="${RESTORE_BUCKET:?}"
  ak="${RESTORE_S3_ACCESS_KEY:?}"; sk="${RESTORE_S3_SECRET_KEY:?}"
else
  ep="${RESTORE_R2_ENDPOINT:?}"; region="auto"; bucket="${RESTORE_R2_BUCKET:?}"
  ak="${RESTORE_R2_ACCESS_KEY:?}"; sk="${RESTORE_R2_SECRET_KEY:?}"
fi

log "!!! OVERWRITING live DB '${RESTORE_DB}' from the ${SOURCE} backup copy !!!"

tmp="$(mktemp -d)"; trap 'rm -rf "${tmp}"' EXIT

# Latest dump under db/ (lexicographic = chronological: arxii-<UTC ts>.sql.gz)
latest="$(AWS_ACCESS_KEY_ID="${ak}" AWS_SECRET_ACCESS_KEY="${sk}" \
  aws --endpoint-url "${ep}" --region "${region}" \
  s3 ls "s3://${bucket}/db/" | awk '{print $4}' | sort | tail -1)"
[[ -n "${latest}" ]] || fail "no backup object found in s3://${bucket}/db/"
log "restoring object: ${latest}"

AWS_ACCESS_KEY_ID="${ak}" AWS_SECRET_ACCESS_KEY="${sk}" \
  aws --endpoint-url "${ep}" --region "${region}" \
  s3 cp "s3://${bucket}/db/${latest}" "${tmp}/dump.sql.gz"

# Restore (plain-SQL pg_dump). The clean-overwrite specifics (terminate
# connections / recreate DB vs psql apply) are an operator/runbook verify
# item — confirm against the deployed Postgres before a real DR.
gunzip -c "${tmp}/dump.sql.gz" | psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "${RESTORE_DB_USER}" "${RESTORE_DB}"

# Verify: the restored DB has tables.
n="$(psql -tA -h 127.0.0.1 -U "${RESTORE_DB_USER}" "${RESTORE_DB}" \
  -c "select count(*) from information_schema.tables where table_schema='public';")"
[[ "${n}" -gt 0 ]] || fail "post-restore verification failed (0 public tables)"
log "restore complete and verified (${n} public tables)."
