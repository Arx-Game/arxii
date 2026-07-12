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
# Optional env:
#   RESTORE_TARGET_HOST   Postgres host to restore into (default 127.0.0.1).
#                         127.0.0.1/localhost means "the host this script is
#                         actually running ON" — for the prod box that's
#                         prod itself; restore-rehearsal.sh runs this script
#                         ON the ephemeral stage box over SSH so its own
#                         127.0.0.1 means the STAGE box, never the operator's
#                         local machine.
# pg_hba.conf requires scram on any TCP connection (see roles/postgres/
# templates/pg_hba.conf.j2 — no `trust` anywhere), so RESTORE_DB_USER needs
# a password reachable via the standard libpq PGPASSWORD env var or
# ~/.pgpass — this script does not manage or default that credential.
# RESTORE_DB_USER also needs privileges beyond the app's normal runtime role
# for the drop/recreate below: CREATEDB, plus either superuser or enough to
# terminate other backends on RESTORE_DB (pg_signal_backend / superuser).
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
RESTORE_TARGET_HOST="${RESTORE_TARGET_HOST:-127.0.0.1}"

if [[ "${SOURCE}" == "linode" ]]; then
  ep="${RESTORE_S3_ENDPOINT:?}"; region="${RESTORE_S3_REGION:?}"; bucket="${RESTORE_BUCKET:?}"
  ak="${RESTORE_S3_ACCESS_KEY:?}"; sk="${RESTORE_S3_SECRET_KEY:?}"
else
  ep="${RESTORE_R2_ENDPOINT:?}"; region="auto"; bucket="${RESTORE_R2_BUCKET:?}"
  ak="${RESTORE_R2_ACCESS_KEY:?}"; sk="${RESTORE_R2_SECRET_KEY:?}"
fi

log "!!! OVERWRITING live DB '${RESTORE_DB}' on ${RESTORE_TARGET_HOST}" \
  "from the ${SOURCE} backup copy !!!"

tmp="$(mktemp -d)"
# Only stop/restart the game service when we're actually restoring into the
# host this script runs on (127.0.0.1/localhost) — restoring into a remote
# target (or a target without systemd, e.g. a bare Postgres test box) has no
# local arxii.service to touch. `service_was_active` starts false and is
# only ever flipped to true right before we actually stop it below, so the
# trap is a no-op unless we really did stop something.
service_was_active=0
cleanup() {
  rm -rf "${tmp}"
  if [[ "${service_was_active}" -eq 1 ]]; then
    log "restarting arxii.service (trap — runs even if the restore failed)…"
    systemctl start arxii.service \
      || printf '[restore] WARNING: failed to restart arxii.service — start it manually!\n' >&2
  fi
}
trap cleanup EXIT

is_local_target=0
if [[ "${RESTORE_TARGET_HOST}" == "127.0.0.1" || "${RESTORE_TARGET_HOST}" == "localhost" ]]; then
  is_local_target=1
fi
if [[ "${is_local_target}" -eq 1 ]] \
    && command -v systemctl >/dev/null 2>&1 \
    && systemctl is-active --quiet arxii.service 2>/dev/null; then
  log "stopping arxii.service before restore (restoring into the live target —" \
    "stale connections/writes must not race the restore)…"
  systemctl stop arxii.service
  service_was_active=1
fi

# Latest dump under db/ (lexicographic = chronological: arxii-<UTC ts>.sql.gz)
latest="$(AWS_ACCESS_KEY_ID="${ak}" AWS_SECRET_ACCESS_KEY="${sk}" \
  aws --endpoint-url "${ep}" --region "${region}" \
  s3 ls "s3://${bucket}/db/" | awk '{print $4}' | sort | tail -1)"
[[ -n "${latest}" ]] || fail "no backup object found in s3://${bucket}/db/"
log "restoring object: ${latest}"

AWS_ACCESS_KEY_ID="${ak}" AWS_SECRET_ACCESS_KEY="${sk}" \
  aws --endpoint-url "${ep}" --region "${region}" \
  s3 cp "s3://${bucket}/db/${latest}" "${tmp}/dump.sql.gz"

# The dump is plain-SQL (pg_dump default format — kept, NOT switched to
# -Fc/custom format: the offsite chain and .sql.gz naming depend on it).
# Piping plain SQL straight into an EXISTING schema aborts on the first
# object collision (ON_ERROR_STOP catches that), but a HALF-applied dump
# can still leave enough tables behind that a bare ">0 tables" check
# reports PASSED on a broken restore. Terminate + drop + recreate the
# target DB first so the dump always applies against a clean schema.
log "terminating existing connections to '${RESTORE_DB}' on ${RESTORE_TARGET_HOST}…"
psql -v ON_ERROR_STOP=1 -h "${RESTORE_TARGET_HOST}" -U "${RESTORE_DB_USER}" \
  -d postgres -c \
  "select pg_terminate_backend(pid) from pg_stat_activity
     where datname = '${RESTORE_DB}' and pid <> pg_backend_pid();" \
  >/dev/null

log "dropping + recreating '${RESTORE_DB}' (owner: ${RESTORE_DB_USER})…"
dropdb --if-exists -h "${RESTORE_TARGET_HOST}" -U "${RESTORE_DB_USER}" "${RESTORE_DB}"
createdb -h "${RESTORE_TARGET_HOST}" -U "${RESTORE_DB_USER}" -O "${RESTORE_DB_USER}" "${RESTORE_DB}"

gunzip -c "${tmp}/dump.sql.gz" \
  | psql -v ON_ERROR_STOP=1 -h "${RESTORE_TARGET_HOST}" -U "${RESTORE_DB_USER}" "${RESTORE_DB}"

# Verify: not just "has tables" (a partial/broken restore can still leave a
# handful of tables behind and pass a bare `>0` check) — assert BOTH that
# Django's own migration ledger actually has rows (the schema is really
# Django's, not some stray leftover) AND that the public schema has at
# least a sane floor of tables. This app has HUNDREDS of tables (Evennia +
# every game app); 50 is comfortably below the real count but high enough
# that a near-empty/partial restore fails loudly instead of reporting a
# false PASSED.
MIN_PUBLIC_TABLES=50

log "verifying restore…"
migrations_n="$(psql -tA -v ON_ERROR_STOP=1 -h "${RESTORE_TARGET_HOST}" \
  -U "${RESTORE_DB_USER}" "${RESTORE_DB}" \
  -c "select count(*) from django_migrations;")"
tables_n="$(psql -tA -v ON_ERROR_STOP=1 -h "${RESTORE_TARGET_HOST}" \
  -U "${RESTORE_DB_USER}" "${RESTORE_DB}" \
  -c "select count(*) from information_schema.tables where table_schema='public';")"

[[ "${migrations_n}" -gt 0 ]] \
  || fail "post-restore verification FAILED:" \
     "django_migrations has 0 rows (schema not really restored)"
[[ "${tables_n}" -ge "${MIN_PUBLIC_TABLES}" ]] \
  || fail "post-restore verification FAILED:" \
     "only ${tables_n} public tables (< floor ${MIN_PUBLIC_TABLES})"

log "restore complete and verified (${tables_n} public tables," \
  "django_migrations has ${migrations_n} rows)."
