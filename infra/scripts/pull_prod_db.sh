#!/usr/bin/env bash
#
# pull_prod_db.sh — dev/operator-side convenience: fetch the LATEST prod DB
# dump (via the read-only `dev_reader` Object Storage key, §4.9 /
# infra/README.md "Pull prod data down") and restore it into the LOCAL dev
# Postgres (DATABASE_URL from src/.env). OVERWRITES local data; never
# touches prod (the dev_reader key is read-only by construction — it cannot
# `Put`/`Delete` even if this script tried).
#
# DELIBERATELY SEPARATE from restore.sh (that script restores a REMOTE/
# on-box target and is prod disaster-recovery machinery — systemd stop/
# start, root-owned paths, operator-supplied RESTORE_* env). This one is a
# plain dev laptop/devcontainer tool: no systemd, no root, config sourced
# from src/.env like every other local dev command in this repo.
#
# Required config (env var already exported wins; else read from src/.env —
# same "env or src/.env" precedence the justfile's `_testdb-url` recipe
# uses for DATABASE_URL, extended here to the dev_reader/bucket vars):
#   ARXII_DEV_READER_ACCESS_KEY, ARXII_DEV_READER_SECRET_KEY
#     Read-only Object Storage key (§4.9). Get them AFTER a successful
#     standup with:  cd infra/terraform/prod && tofu output -raw dev_reader_access_key
#     (and dev_reader_secret_key) — then paste both into src/.env.
#   ARXII_BACKUPS_BUCKET      = tofu output -raw backups_bucket
#   ARXII_BACKUPS_S3_ENDPOINT = tofu output -raw backups_s3_endpoint
#   ARXII_BACKUPS_REGION      = tofu output -raw region
#   DATABASE_URL (src/.env, already required for local dev) — the RESTORE
#     TARGET. Accepted form: postgres[ql]://user[:pass]@host[:port]/dbname
#     (no query string, no surrounding quotes; port defaults to 5432 when
#     omitted). The dbname charset check mirrors the justfile's
#     `_testdb-url` recipe's own check on the same variable — but that
#     recipe doesn't parse user/host/port at all (it just splits on the
#     last `/`), so this is NOT full parity with it, just the same dbname
#     restriction. Out of scope (fails loudly, not silently): bracketed
#     IPv6 hosts, percent-encoded passwords.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"; readonly ROOT
readonly ENV_FILE="${ROOT}/src/.env"

log()  { printf '[pull-prod] %s\n' "$*"; }
fail() { printf '[pull-prod] REFUSING: %s\n' "$*" >&2; exit 1; }

# verify_restored_db() (#2236 review) — this script is a dev laptop/
# devcontainer tool (unlike restore.sh, which deploys standalone to the prod
# box, where lib.sh is never shipped — see restore.sh's own inline copy),
# so sourcing lib.sh here is safe and de-duplicates the post-restore check.
# shellcheck source=infra/scripts/lib.sh
. "${SCRIPT_DIR}/lib.sh"

CONFIRMED=0

usage() {
  cat <<'EOF'
Usage: pull_prod_db.sh --i-understand-this-overwrites-local
  --i-understand-this-overwrites-local   REQUIRED — OVERWRITES your local dev DB.
Without the explicit flag this refuses and changes nothing. Never writes to
the bucket and never touches prod (dev_reader is a read-only key).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --i-understand-this-overwrites-local) CONFIRMED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown argument: $1" ;;
  esac
done

[[ "${CONFIRMED}" -eq 1 ]] \
  || { usage; fail "explicit --i-understand-this-overwrites-local required (OVERWRITES your local dev DB)"; }

# env_or_file <VAR_NAME>: an already-exported env var wins; otherwise grep it
# out of src/.env (same source + precedence the justfile's `_testdb-url`
# recipe uses for DATABASE_URL — VAR=value, one per line, last match wins).
env_or_file() {
  local name="$1" val="${!1:-}"
  if [[ -n "${val}" ]]; then
    printf '%s' "${val}"
    return
  fi
  [[ -f "${ENV_FILE}" ]] || return 0
  grep -E "^${name}=" "${ENV_FILE}" | tail -1 | cut -d= -f2-
}

# require <VAR_NAME> <how-to-get-it>: fail-closed, naming exactly which var
# is missing and where to get it — never a generic "config missing".
require() {
  local name="$1" hint="$2" val
  val="$(env_or_file "${name}")"
  [[ -n "${val}" ]] || fail "${name} not set (env or ${ENV_FILE}). ${hint}"
  printf '%s' "${val}"
}

[[ -f "${ENV_FILE}" ]] || fail "no ${ENV_FILE} — copy src/.env.example first"

log "checking config…"
DEV_READER_ACCESS_KEY="$(require ARXII_DEV_READER_ACCESS_KEY \
  "post-standup: cd infra/terraform/prod && tofu output -raw dev_reader_access_key — paste into src/.env")"
DEV_READER_SECRET_KEY="$(require ARXII_DEV_READER_SECRET_KEY \
  "post-standup: cd infra/terraform/prod && tofu output -raw dev_reader_secret_key — paste into src/.env")"
BACKUPS_BUCKET="$(require ARXII_BACKUPS_BUCKET \
  "post-standup: cd infra/terraform/prod && tofu output -raw backups_bucket — paste into src/.env")"
BACKUPS_S3_ENDPOINT="$(require ARXII_BACKUPS_S3_ENDPOINT \
  "post-standup: cd infra/terraform/prod && tofu output -raw backups_s3_endpoint — paste into src/.env")"
BACKUPS_REGION="$(require ARXII_BACKUPS_REGION \
  "post-standup: cd infra/terraform/prod && tofu output -raw region — paste into src/.env")"
DATABASE_URL_VAL="$(require DATABASE_URL \
  "src/.env is missing DATABASE_URL entirely — every local dev command needs this")"

# Parse DATABASE_URL into its parts. Accepted form:
# postgres[ql]://user[:pass]@host[:port]/dbname (no query string, no
# surrounding quotes) — password and port are OPTIONAL (port defaults to
# 5432 below when omitted). The dbname charset check is the same one the
# justfile's `_testdb-url` recipe applies to the same variable, but that
# recipe doesn't otherwise parse the URL (it just splits on the last `/`),
# so this regex is NOT a full-parity reimplementation of it — it is
# deliberately stricter about the overall shape, to fail loudly rather than
# silently mis-derive a part. Out of scope: bracketed IPv6 hosts,
# percent-encoded passwords — either fails this regex loudly rather than
# being silently mishandled.
if [[ "${DATABASE_URL_VAL}" =~ ^postgres(ql)?://([^:@/]+)(:([^@]*))?@([^:/@]+)(:([0-9]+))?/([A-Za-z0-9_]+)$ ]]; then
  DB_USER="${BASH_REMATCH[2]}"
  DB_PASS="${BASH_REMATCH[4]}"
  DB_HOST="${BASH_REMATCH[5]}"
  DB_PORT="${BASH_REMATCH[7]:-5432}"
  DB_NAME="${BASH_REMATCH[8]}"
else
  fail "src/.env's DATABASE_URL isn't in the supported form" \
    "postgres://user[:pass]@host[:port]/dbname (no query string, no surrounding quotes)"
fi

# aws CLI: prefer a system install; fall back to `uvx --from awscli aws`
# (works in this devcontainer — verified: PyPI is reachable from here,
# unlike some other package registries this firewall blocks). If the
# devcontainer firewall ever blocks PyPI mid-run, uvx's download fails
# loudly (non-zero exit) rather than silently — install `awscli` via apt/
# pip/pipx as a one-time fix and re-run.
if command -v aws >/dev/null 2>&1; then
  AWS_CMD=(aws)
elif command -v uvx >/dev/null 2>&1; then
  log "aws CLI not found — falling back to 'uvx --from awscli aws' (first run downloads from PyPI)…"
  AWS_CMD=(uvx --from awscli aws)
else
  fail "no aws CLI and no uvx available. Install one: apt-get install awscli," \
    "or 'pip install awscli' / 'pipx install awscli', or install uv (https://docs.astral.sh/uv/)"
fi

log "!!! OVERWRITING local dev DB '${DB_NAME}' on ${DB_HOST}:${DB_PORT} with the latest prod dump !!!"

tmp="$(mktemp -d)"
cleanup() { rm -rf "${tmp}"; }
trap cleanup EXIT

# Latest dump under db/, by the timestamp EMBEDDED IN THE NAME, not list
# order (same technique restore.sh uses: arxii-<UTC compact ts>.sql.gz sorts
# lexicographically == chronologically, so a plain `sort | tail -1` over
# the object names is correct — s3 ls's own listing order is not a
# reliable proxy for "latest").
log "listing s3://${BACKUPS_BUCKET}/db/ …"
# `|| true` on the pipeline (#2236 review): under `set -o pipefail`, `grep`
# matching ZERO objects exits 1 — the pipeline's rightmost failure — which
# would abort the whole script right here (set -e) and skip the intended
# `latest` empty-string diagnostic below entirely. `|| true` lets an empty
# result reach that check instead of aborting silently mid-pipeline.
latest="$(AWS_ACCESS_KEY_ID="${DEV_READER_ACCESS_KEY}" AWS_SECRET_ACCESS_KEY="${DEV_READER_SECRET_KEY}" \
  "${AWS_CMD[@]}" --endpoint-url "${BACKUPS_S3_ENDPOINT}" --region "${BACKUPS_REGION}" \
  s3 ls "s3://${BACKUPS_BUCKET}/db/" \
  | awk '{print $4}' | grep -E '^arxii-[0-9TZ]+\.sql\.gz$' | sort | tail -1 || true)"
[[ -n "${latest}" ]] || fail "no backup object found in s3://${BACKUPS_BUCKET}/db/"
log "pulling object: ${latest}"

AWS_ACCESS_KEY_ID="${DEV_READER_ACCESS_KEY}" AWS_SECRET_ACCESS_KEY="${DEV_READER_SECRET_KEY}" \
  "${AWS_CMD[@]}" --endpoint-url "${BACKUPS_S3_ENDPOINT}" --region "${BACKUPS_REGION}" \
  s3 cp "s3://${BACKUPS_BUCKET}/db/${latest}" "${tmp}/dump.sql.gz"

# (#2236 review) DB_PASS is now genuinely optional (see the regex above) —
# only set/export PGPASSWORD when a password was actually present; an empty
# PGPASSWORD='' is not the same as "unset" to libpq (some setups treat an
# empty value as "explicitly no password" rather than "fall through to
# ~/.pgpass/peer auth" the way a truly-unset var would).
if [[ -n "${DB_PASS}" ]]; then
  export PGPASSWORD="${DB_PASS}"
fi

# (#2236 review) Retried (3 attempts, 1s apart): an auto-reconnecting local
# process (a dev server, a test runner) can grab a brand-new connection to
# ${DB_NAME} in the gap between pg_terminate_backend and dropdb, aborting the
# drop with "database is being accessed by other users". One shot was not
# enough in practice; terminate+drop together each attempt since a fresh
# connection can appear either before or after the terminate query runs.
terminate_and_drop() {
  psql -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -c \
    "select pg_terminate_backend(pid) from pg_stat_activity
       where datname = '${DB_NAME}' and pid <> pg_backend_pid();" \
    >/dev/null
  dropdb --if-exists -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}"
}
log "terminating existing connections + dropping '${DB_NAME}' on ${DB_HOST}:${DB_PORT}…"
drop_attempts=3
drop_ok=0
for ((attempt = 1; attempt <= drop_attempts; attempt++)); do
  if terminate_and_drop; then
    drop_ok=1
    break
  fi
  log "terminate+drop attempt ${attempt}/${drop_attempts} failed — retrying in 1s…"
  sleep 1
done
[[ "${drop_ok}" -eq 1 ]] \
  || fail "could not terminate connections + drop '${DB_NAME}' after ${drop_attempts} attempts" \
    "— stop local dev servers/test runners holding connections to it and retry"

log "recreating '${DB_NAME}' (owner: ${DB_USER})…"
createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -O "${DB_USER}" "${DB_NAME}"

gunzip -c "${tmp}/dump.sql.gz" \
  | psql -v ON_ERROR_STOP=1 -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}"

log "running migrations (idempotent)…"
(cd "${ROOT}" && uv run arx manage migrate --noinput)

# Verify: same two-count-query + floor shape restore.sh's post-restore check
# uses, now shared via lib.sh's verify_restored_db() (#2236 review) — this
# script is a dev laptop/devcontainer tool (unlike restore.sh, which is
# deployed standalone to the prod box, where lib.sh is never shipped; see
# infra/scripts/restore.sh's own inline copy — the THIRD location — for the
# "why 50" reasoning it still carries independently).
log "verifying restore…"
verify_restored_db "${DB_HOST}" "${DB_PORT}" "${DB_NAME}" "${DB_USER}"
log "pull complete."
