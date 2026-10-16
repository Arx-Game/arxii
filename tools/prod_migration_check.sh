#!/usr/bin/env bash
#
# prod_migration_check.sh - prove a migration (or a data check) against the
# NEWEST production dump, in a throwaway scratch database. Wrapped by
# `just prod-migration-check` (#4390).
#
# Usage:
#   tools/prod_migration_check.sh [target_migration] [--tables a,b,c] [--keep]
#
#   target_migration  Migration to step back to (number prefix such as 0234, or
#                     the full name). Default: main's tip, read from
#                     origin/main's max_migration.txt.
#   --tables a,b,c    Tables to count before and after (arxii_ prefix optional).
#   --keep            Leave the scratch database in place and print how to drop
#                     it. Without it, the database and the dump are removed on
#                     every exit path.
#   --database NAME   Name the scratch database. Accepted ONLY if it matches
#                     scratch_pmc_<UTC timestamp>_<pid> and does not exist yet;
#                     anything else (arxiidev, a name from src/.env) is refused.
#                     This exists so the refusal can be demonstrated.
#
# What it does: fetch the newest dump with the read-only dev_reader key, create
# a fresh scratch database, restore, migrate forward to this branch's head,
# back to the target, forward again, count rows, list pending migrations. The
# report on stdout is meant to be pasted as evidence. Exit status is non-zero
# on any failure.
#
# Safety, enforced below and not by convention:
#   - the database it creates, restores into, migrates and drops must match
#     the scratch prefix, must not exist beforehand, and must not be named in
#     src/.env (assert_scratch, called before every use);
#   - the only credential for the bucket is the dev_reader key; it issues
#     `s3 ls` and `s3 cp` and nothing else;
#   - the migrate runs with DATABASE_URL pointed at the scratch database, and
#     the database Django actually connected to is read back and compared
#     before any migration is applied (src/.env cannot silently win: this
#     calls `evennia` directly, not `arx manage`, which loads src/.env with
#     override=True);
#   - the whole run holds /tmp/claude-1000/arx-heavy.lock (override with
#     ARX_HEAVY_LOCK) for at most 20 minutes.
set -euo pipefail
set +x

readonly SCRATCH_PREFIX="scratch_pmc_"
MAX_SECONDS="${ARX_PMC_MAX_SECONDS:-1200}"   # override only to test the ceiling
LOCK_FILE="${ARX_HEAVY_LOCK:-/tmp/claude-1000/arx-heavy.lock}"

# Take the heavy-command lock and a hard 20 minute ceiling by re-running
# ourselves under flock + timeout. A timeout sends TERM to the script, which
# the traps below turn into a normal exit, so cleanup still runs.
if [[ -z "${PMC_LOCKED:-}" ]]; then
  mkdir -p "$(dirname "${LOCK_FILE}")"
  exec env PMC_LOCKED=1 flock "${LOCK_FILE}" \
    timeout "${MAX_SECONDS}" "${BASH_SOURCE[0]}" "$@"
fi

log()  { printf '[prod-migration-check] %s\n' "$*" >&2; }
fail() { printf '[prod-migration-check] REFUSING/FAILED: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MIGRATIONS_DIR="${ROOT}/src/world/migrations"
APP_LABEL="arxii"

TARGET=""
TABLES=""
KEEP=0
SCRATCH_DB=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tables)    [[ $# -ge 2 ]] || fail "--tables needs a value"; TABLES="$2"; shift 2 ;;
    --tables=*)  TABLES="${1#--tables=}"; shift ;;
    --keep)      KEEP=1; shift ;;
    --database)  [[ $# -ge 2 ]] || fail "--database needs a value"; SCRATCH_DB="$2"; shift 2 ;;
    --database=*) SCRATCH_DB="${1#--database=}"; shift ;;
    -h|--help)   sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)          fail "unknown option: $1" ;;
    *)           [[ -z "${TARGET}" ]] || fail "only one target migration allowed"
                 TARGET="$1"; shift ;;
  esac
done

# ---- configuration ---------------------------------------------------------

# The main checkout's src/.env is the source of config; a worktree has none.
find_env_file() {
  local common
  if [[ -n "${ARX_ENV_FILE:-}" ]]; then printf '%s' "${ARX_ENV_FILE}"; return; fi
  if [[ -f "${ROOT}/src/.env" ]]; then printf '%s' "${ROOT}/src/.env"; return; fi
  common="$(git -C "${ROOT}" rev-parse --git-common-dir 2>/dev/null || true)"
  [[ -n "${common}" ]] && printf '%s' "$(cd "${common}/.." && pwd)/src/.env"
}
ENV_FILE="$(find_env_file)"
[[ -f "${ENV_FILE}" ]] || fail "no src/.env found (looked at ${ENV_FILE:-nothing}); set ARX_ENV_FILE"

# env_or_file NAME: exported env var wins, else the last NAME= line of the file.
env_or_file() {
  local name="$1" val="${!1:-}"
  if [[ -n "${val}" ]]; then printf '%s' "${val}"; return; fi
  grep -E "^${name}=" "${ENV_FILE}" | tail -1 | cut -d= -f2- | sed -E "s/^(['\"])(.*)\1$/\2/" || true
}
require() {
  local val; val="$(env_or_file "$1")"
  [[ -n "${val}" ]] || fail "$1 not set (env or ${ENV_FILE}); see infra/README.md 'Pull prod data down'"
  printf '%s' "${val}"
}

ACCESS_KEY="$(require ARXII_DEV_READER_ACCESS_KEY)"
SECRET_KEY_VAL="$(require ARXII_DEV_READER_SECRET_KEY)"
BUCKET="$(require ARXII_BACKUPS_BUCKET)"
ENDPOINT="$(require ARXII_BACKUPS_S3_ENDPOINT)"
REGION="$(require ARXII_BACKUPS_REGION)"
BASE_URL="$(require DATABASE_URL)"

if [[ "${BASE_URL}" =~ ^postgres(ql)?://([^:@/]+)(:([^@]*))?@([^:/@]+)(:([0-9]+))?/([A-Za-z0-9_]+)$ ]]; then
  DB_USER="${BASH_REMATCH[2]}"; DB_PASS="${BASH_REMATCH[4]}"
  DB_HOST="${BASH_REMATCH[5]}"; DB_PORT="${BASH_REMATCH[7]:-5432}"
else
  fail "DATABASE_URL is not postgres://user[:pass]@host[:port]/dbname"
fi
[[ -z "${DB_PASS}" ]] || export PGPASSWORD="${DB_PASS}"

# Every database name the configuration mentions. The scratch name must never
# be one of them (it cannot match the prefix anyway; this is the second lock).
PROTECTED_DBS=" arxiidev postgres template0 template1 "
while read -r name; do
  [[ -n "${name}" ]] && PROTECTED_DBS+="${name} "
done < <( { grep -hoE 'postgres(ql)?://[^[:space:]"'"'"']*/[A-Za-z0-9_]+' "${ENV_FILE}" || true
            printf '%s\n' "${DATABASE_URL:-}" "${BASE_URL}"; } \
          | grep -oE '/[A-Za-z0-9_]+$' | tr -d / )

assert_scratch() {
  local name="$1"
  [[ "${name}" =~ ^${SCRATCH_PREFIX}[0-9]{8}T[0-9]{6}Z_[0-9]+$ ]] \
    || fail "'${name}' is not a scratch database name (${SCRATCH_PREFIX}<UTC timestamp>_<pid>)"
  [[ "${PROTECTED_DBS}" != *" ${name} "* ]] \
    || fail "'${name}' is a database named in the configuration"
}

# The tool creates and drops databases, so it only ever does that on this
# machine or a private network (same gate as infra/scripts/pull_prod_db.sh).
assert_local_target() {
  local host="$1" ips ip
  [[ "${host}" == localhost ]] && return 0
  ips="$(getent ahostsv4 "${host}" 2>/dev/null | awk '{print $1}' | sort -u)"
  [[ -n "${ips}" ]] || fail "cannot resolve database host '${host}'"
  while read -r ip; do
    case "${ip}" in
      127.*|10.*|192.168.*|169.254.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;;
      *) fail "database host '${host}' resolves to ${ip}, which is not loopback/private" ;;
    esac
  done <<< "${ips}"
}
assert_local_target "${DB_HOST}"

PSQL=(psql -X -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}")
db_exists() { "${PSQL[@]}" -d postgres -Atc "select 1 from pg_database where datname = '$1'" | grep -q 1; }

if [[ -z "${SCRATCH_DB}" ]]; then
  SCRATCH_DB="${SCRATCH_PREFIX}$(date -u +%Y%m%dT%H%M%SZ)_$$"
fi
assert_scratch "${SCRATCH_DB}"
db_exists "${SCRATCH_DB}" && fail "'${SCRATCH_DB}' already exists; a scratch database must be fresh"

# ---- migrations: branch head, main tip, target ----------------------------

resolve_migration() {
  local want="$1" hits
  hits=( "${MIGRATIONS_DIR}/${want}"*.py )
  [[ -e "${hits[0]}" && ${#hits[@]} -eq 1 ]] \
    || fail "target '${want}' does not match exactly one migration in ${MIGRATIONS_DIR}"
  basename "${hits[0]}" .py
}

BRANCH_HEAD="$(tr -d '[:space:]' < "${MIGRATIONS_DIR}/max_migration.txt")"
[[ -n "${BRANCH_HEAD}" ]] || fail "max_migration.txt is empty"
git -C "${ROOT}" fetch --quiet origin main || log "fetch of origin/main failed; using the local ref"
MAIN_TIP="$(git -C "${ROOT}" show origin/main:src/world/migrations/max_migration.txt 2>/dev/null \
  | tr -d '[:space:]' || true)"
[[ -n "${MAIN_TIP}" ]] || fail "cannot read origin/main's max_migration.txt"
if [[ -n "${TARGET}" ]]; then BACK_TO="$(resolve_migration "${TARGET}")"; else BACK_TO="${MAIN_TIP}"; fi
HEAD_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
BRANCH_NAME="$(git -C "${ROOT}" branch --show-current)"

# ---- table list ------------------------------------------------------------
TABLE_LIST=()
if [[ -n "${TABLES}" ]]; then
  IFS=, read -r -a TABLE_LIST <<< "${TABLES}"
  for t in "${TABLE_LIST[@]}"; do
    [[ "${t}" =~ ^[a-z0-9_]+$ ]] || fail "table name '${t}' must be lowercase letters, digits, underscore"
  done
fi

# ---- cleanup (every exit path) ---------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pmc.XXXXXX")"
CREATED=0
CLEANED="no scratch database was created"
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "${CREATED}" -eq 1 && "${KEEP}" -eq 0 ]]; then
    assert_scratch "${SCRATCH_DB}"
    "${PSQL[@]}" -d postgres -qAtc "select pg_terminate_backend(pid) from pg_stat_activity
      where datname = '${SCRATCH_DB}' and pid <> pg_backend_pid()" >/dev/null 2>&1 || true
    if dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${SCRATCH_DB}" 2>/dev/null; then
      CLEANED="scratch database ${SCRATCH_DB} dropped, dump deleted"
    else
      CLEANED="COULD NOT DROP ${SCRATCH_DB}; drop it by hand: dropdb -h ${DB_HOST} -U ${DB_USER} ${SCRATCH_DB}"
      rc=1
    fi
  elif [[ "${CREATED}" -eq 1 ]]; then
    CLEANED="KEPT ${SCRATCH_DB} (--keep); dump deleted. Drop it with: dropdb -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} ${SCRATCH_DB}"
  fi
  rm -rf "${WORK}"
  printf 'cleanup: %s\n' "${CLEANED}"
  if [[ "${rc}" -eq 0 ]]; then echo "RESULT: PASS"; else echo "RESULT: FAIL (exit ${rc}); logs above"; fi
  exit "${rc}"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# ---- fetch the newest dump with the read-only key only ---------------------
if command -v aws >/dev/null 2>&1; then AWS_CMD=(aws)
elif command -v uvx >/dev/null 2>&1; then AWS_CMD=(uvx --from awscli aws)
else fail "no aws CLI and no uvx available"; fi

aws_ro() {
  # Only the dev_reader key is ever in the environment for the bucket calls.
  env -u AWS_SESSION_TOKEN -u AWS_PROFILE \
    AWS_ACCESS_KEY_ID="${ACCESS_KEY}" AWS_SECRET_ACCESS_KEY="${SECRET_KEY_VAL}" \
    "${AWS_CMD[@]}" --endpoint-url "${ENDPOINT}" --region "${REGION}" "$@"
}

log "listing the backups bucket"
DUMP_NAME="$(aws_ro s3 ls "s3://${BUCKET}/db/" | awk '{print $4}' \
  | grep -E '^arxii-[0-9TZ]+\.sql\.gz$' | sort | tail -1 || true)"
[[ -n "${DUMP_NAME}" ]] || fail "no dump found in the backups bucket"
log "downloading ${DUMP_NAME}"
aws_ro s3 cp --only-show-errors "s3://${BUCKET}/db/${DUMP_NAME}" "${WORK}/dump.sql.gz"

# ---- scratch database ------------------------------------------------------
assert_scratch "${SCRATCH_DB}"
createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -O "${DB_USER}" "${SCRATCH_DB}"
CREATED=1
log "restoring into ${SCRATCH_DB}"
assert_scratch "${SCRATCH_DB}"
gunzip -c "${WORK}/dump.sql.gz" | "${PSQL[@]}" -q -d "${SCRATCH_DB}" >"${WORK}/restore.log" 2>&1 \
  || { tail -20 "${WORK}/restore.log" >&2; fail "restore failed"; }

q() { "${PSQL[@]}" -d "${SCRATCH_DB}" -Atc "$1"; }
applied_tip() { q "select name from django_migrations where app = '${APP_LABEL}' order by name desc limit 1"; }

# Table counts for the report. A bare name falls back to the arxii_ prefix.
count_tables() {
  local t full
  [[ ${#TABLE_LIST[@]} -gt 0 ]] || return 0
  for t in "${TABLE_LIST[@]}"; do
    full="${t}"
    [[ "$(q "select to_regclass('public.\"${full}\"') is not null")" == t ]] || full="${APP_LABEL}_${t}"
    if [[ "$(q "select to_regclass('public.\"${full}\"') is not null")" == t ]]; then
      printf '  %s=%s\n' "${full}" "$(q "select count(*) from \"${full}\"")"
    else
      printf '  %s=(table absent)\n' "${t}"
      ABSENT_TABLES+=("${t}")
    fi
  done
}
ABSENT_TABLES=()

# Run evennia against the scratch database. The environment is the file's
# values (only where unset, as settings.py does) with DATABASE_URL forced.
EVENNIA_ENV=()
while IFS= read -r line; do
  [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
  k="${line%%=*}"; v="${line#*=}"
  v="$(sed -E "s/^(['\"])(.*)\1$/\2/" <<<"${v}")"
  [[ "${k}" == DATABASE_URL ]] && continue
  [[ -n "${!k:-}" ]] || EVENNIA_ENV+=("${k}=${v}")
done < "${ENV_FILE}"
SCRATCH_URL="postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${SCRATCH_DB}"
evennia_scratch() {
  assert_scratch "${SCRATCH_DB}"
  ( cd "${ROOT}/src" && env "${EVENNIA_ENV[@]}" DATABASE_URL="${SCRATCH_URL}" uv run evennia "$@" )
}

# Prove which database Django will use, before any migration touches it.
USED_DB="$(evennia_scratch shell -c "from django.db import connection; print('DB=' + connection.settings_dict['NAME'])" 2>"${WORK}/shell.err" | grep '^DB=' | tail -1 | cut -c4- || true)"
[[ "${USED_DB}" == "${SCRATCH_DB}" ]] \
  || { cat "${WORK}/shell.err" >&2; fail "Django would use '${USED_DB:-nothing}', not ${SCRATCH_DB}; not migrating"; }

# Run one migrate step, check the recorded tip afterwards (the launcher exits 0
# when settings fail to import), print the Applying/Unapplying lines.
migrate_step() {
  local label="$1" expect="$2" logf="${WORK}/migrate-$1.log"; shift 2
  evennia_scratch migrate --noinput "$@" >"${logf}" 2>&1 || { tail -30 "${logf}" >&2; fail "migrate (${label}) failed"; }
  grep -E '^  (Applying|Unapplying) ' "${logf}" | sed 's/^ */  /' || true
  [[ "$(applied_tip)" == "${expect}" ]] \
    || { tail -30 "${logf}" >&2; fail "after '${label}' the recorded tip is '$(applied_tip)', expected '${expect}'"; }
}

# ---- the run ---------------------------------------------------------------
echo "== prod-migration-check report"
echo "head: ${HEAD_SHA} (${BRANCH_NAME})"
echo "dump: ${DUMP_NAME}"
echo "scratch database: ${SCRATCH_DB} (django connected to: ${USED_DB})"
PROD_TIP="$(applied_tip)"
echo "production tip: ${PROD_TIP:-none} | branch head: ${BRANCH_HEAD} | main tip: ${MAIN_TIP} | step back to: ${BACK_TO}"
echo "== rows before (dump as restored)"
count_tables
ABSENT_BEFORE=" ${ABSENT_TABLES[*]:-} "
ABSENT_TABLES=()
echo "== forward to branch head"
migrate_step forward "${BRANCH_HEAD}"
if [[ "${BACK_TO}" < "${BRANCH_HEAD}" ]]; then
  echo "== back to ${BACK_TO}"
  migrate_step back "${BACK_TO}" "${APP_LABEL}" "${BACK_TO}"
  echo "== forward again"
  migrate_step forward-again "${BRANCH_HEAD}"
else
  echo "== back/forward skipped: ${BACK_TO} is not behind the branch head ${BRANCH_HEAD}"
fi
echo "== rows after"
count_tables
# A name missing both before and after never existed: a typo, not a result.
for t in "${ABSENT_TABLES[@]:-}"; do
  [[ -z "${t}" || "${ABSENT_BEFORE}" != *" ${t} "* ]] || fail "table '${t}' is absent before and after; check the name"
done
echo "== pending migrations"
PENDING="$(evennia_scratch showmigrations 2>/dev/null | grep -E '^ *\[ \]' || true)"
if [[ -z "${PENDING}" ]]; then echo "  none"; else echo "${PENDING}"; fi
[[ -z "${PENDING}" ]] || fail "${PENDING//$'\n'/; } still pending"
echo "== done"
