#!/usr/bin/env bash
#
# restore-rehearsal.sh — proves the 3-2-1 backups actually RESTORE (an
# untested backup is no backup), WITHOUT touching prod.
#
# Operates STRUCTURALLY on the ephemeral-stage root ONLY (separate state +
# separate credential scope, §4.8) — it cannot enumerate or affect prod.
# apply -> restore-from-BOTH-copies -> sanity -> ALWAYS destroy (trap, so a
# failed test still tears the stage down). set +x, no secret echo.
#
# IMPORTANT — where the restore actually happens: the ephemeral-stage box is
# a bare Linode instance with NO Postgres (terraform/ephemeral-stage/main.tf
# only provisions compute). This script installs Postgres on IT, then runs
# restore.sh ON that box over SSH, restoring into ITS OWN loopback Postgres
# (RESTORE_TARGET_HOST=127.0.0.1 *of the stage box*). The operator's LOCAL
# machine is NEVER a restore target — restore.sh's RESTORE_TARGET_HOST would
# otherwise default to the invoking machine's own 127.0.0.1 and OVERWRITE
# whatever local dev DB happens to be running there while still printing
# PASSED (the original bug this rework fixes). Also: prod Postgres binds
# listen_addresses=localhost only (roles/postgres), so a restore attempted
# over the network from off-box could never have worked in the first place.
#
# Required: REHEARSAL_CONFIRM=1, STAGE-scoped creds (TF_VAR_linode_token =
# stage token), RUN_ID, and the RESTORE_* read envs (see restore.sh) for
# BOTH the linode and r2 sources (this script rehearses both in one run).
# RESTORE_DB_USER's Postgres PASSWORD is NOT operator-supplied — it is
# generated fresh per run and used only to create a throwaway superuser role
# on the disposable stage box, destroyed along with it.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
STAGE_DIR="$(cd "${SCRIPT_DIR}/../terraform/ephemeral-stage" && pwd)"; readonly STAGE_DIR

readonly SSH_WAIT_TIMEOUT_S=300
readonly SSH_WAIT_INTERVAL_S=5
# Brand-new host every run by design (no prior known_hosts entry can exist,
# same reasoning as standup.sh's select_ssh_user) — accept-new instead of a
# host-key prompt or disabling checking outright.
readonly SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

log()  { printf '[rehearsal] %s\n' "$*"; }
fail() { printf '[rehearsal] REFUSING: %s\n' "$*" >&2; exit 1; }

[[ "${REHEARSAL_CONFIRM:-}" == "1" ]] || fail "set REHEARSAL_CONFIRM=1 (spins up + destroys an ephemeral stage box)"
: "${RUN_ID:?set RUN_ID (unique per-run suffix)}"
[[ "$(basename "${STAGE_DIR}")" == "ephemeral-stage" ]] \
  || fail "guard: this only ever runs against the ephemeral-stage root"

# Fail fast on missing creds BEFORE spinning up a stage box for a guaranteed
# failure — both source's full credential sets are required since this
# script rehearses linode AND r2 in the same run.
: "${RESTORE_DB:?set RESTORE_DB}"
: "${RESTORE_DB_USER:?set RESTORE_DB_USER}"
: "${RESTORE_S3_ENDPOINT:?set RESTORE_S3_ENDPOINT (linode source)}"
: "${RESTORE_S3_REGION:?set RESTORE_S3_REGION (linode source)}"
: "${RESTORE_BUCKET:?set RESTORE_BUCKET (linode source)}"
: "${RESTORE_S3_ACCESS_KEY:?set RESTORE_S3_ACCESS_KEY (linode source)}"
: "${RESTORE_S3_SECRET_KEY:?set RESTORE_S3_SECRET_KEY (linode source)}"
: "${RESTORE_R2_ENDPOINT:?set RESTORE_R2_ENDPOINT (r2 source)}"
: "${RESTORE_R2_BUCKET:?set RESTORE_R2_BUCKET (r2 source)}"
: "${RESTORE_R2_ACCESS_KEY:?set RESTORE_R2_ACCESS_KEY (r2 source)}"
: "${RESTORE_R2_SECRET_KEY:?set RESTORE_R2_SECRET_KEY (r2 source)}"

# Rehearsal-only Postgres role password for the stage box — generated here,
# never operator-supplied, never leaves this run (lives only in a 0600 temp
# file scp'd to the box we're about to destroy).
restore_db_password="$(openssl rand -hex 20)"
env_tmp="$(mktemp)"; chmod 600 "${env_tmp}"

teardown() {
  rm -f "${env_tmp}"
  log "tearing down ephemeral stage (always, even on failure)…"
  tofu -chdir="${STAGE_DIR}" destroy -auto-approve -input=false || \
    printf '[rehearsal] WARNING: stage teardown failed — destroy manually!\n' >&2
}
trap teardown EXIT

log "provisioning ephemeral stage…"
tofu -chdir="${STAGE_DIR}" init -input=false
tofu -chdir="${STAGE_DIR}" apply -auto-approve -input=false

# Defense-in-depth: confirm what we provisioned is tagged ephemeral-stage
# before we trust the teardown will only hit stage.
tofu -chdir="${STAGE_DIR}" state list | grep -q . \
  || fail "no stage resources in stage state — aborting"

stage_ip="$(tofu -chdir="${STAGE_DIR}" output -raw stage_ipv4)"
log "stage host: ${stage_ip}"

log "Waiting for SSH (port 22) on ${stage_ip} (up to ${SSH_WAIT_TIMEOUT_S}s)…"
waited=0
until timeout 5 bash -c "true >/dev/tcp/${stage_ip}/22" 2>/dev/null; do
  waited=$((waited + SSH_WAIT_INTERVAL_S))
  if [[ "${waited}" -ge "${SSH_WAIT_TIMEOUT_S}" ]]; then
    fail "SSH port 22 on ${stage_ip} did not open within ${SSH_WAIT_TIMEOUT_S}s"
  fi
  sleep "${SSH_WAIT_INTERVAL_S}"
done
log "SSH port open."

# Linode injects the stage-run keypair straight into root on this throwaway
# box (terraform/modules/compute `authorized_keys` — same mechanism prod's
# very first converge relies on). No arxadmin exists here; unlike prod,
# nothing ever hardens this box, it just gets destroyed.
ssh_stage() { ssh "${SSH_OPTS[@]}" "root@${stage_ip}" "$@"; }
scp_stage() { scp "${SSH_OPTS[@]}" "$@"; }

log "installing postgresql + postgresql-client + awscli on the stage box…"
ssh_stage bash -s <<'REMOTE'
set -euo pipefail
cloud-init status --wait || true
DEBIAN_FRONTEND=noninteractive apt-get update -o DPkg::Lock::Timeout=600
DEBIAN_FRONTEND=noninteractive apt-get install -y -o DPkg::Lock::Timeout=600 \
  postgresql postgresql-client awscli
systemctl enable --now postgresql
REMOTE

log "creating the rehearsal-only Postgres role on the stage box" \
  "(throwaway; destroyed with the box)…"
ssh_stage bash -s <<REMOTE
set -euo pipefail
sudo -u postgres dropuser --if-exists ${RESTORE_DB_USER}
sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
  "create role ${RESTORE_DB_USER} with login superuser password '${restore_db_password}';"
REMOTE

log "copying restore.sh onto the stage box…"
scp_stage "${SCRIPT_DIR}/restore.sh" "root@${stage_ip}:/root/restore.sh"

# All the RESTORE_* env restore.sh needs, forwarded via a 0600 file instead
# of inline ssh command args — avoids re-deriving shell-quoting rules for
# arbitrary credential contents over an ssh argv join.
{
  printf 'RESTORE_DB=%s\n' "${RESTORE_DB}"
  printf 'RESTORE_DB_USER=%s\n' "${RESTORE_DB_USER}"
  printf 'PGPASSWORD=%s\n' "${restore_db_password}"
  printf 'RESTORE_TARGET_HOST=127.0.0.1\n'
  printf 'RESTORE_S3_ENDPOINT=%s\n' "${RESTORE_S3_ENDPOINT}"
  printf 'RESTORE_S3_REGION=%s\n' "${RESTORE_S3_REGION}"
  printf 'RESTORE_BUCKET=%s\n' "${RESTORE_BUCKET}"
  printf 'RESTORE_S3_ACCESS_KEY=%s\n' "${RESTORE_S3_ACCESS_KEY}"
  printf 'RESTORE_S3_SECRET_KEY=%s\n' "${RESTORE_S3_SECRET_KEY}"
  printf 'RESTORE_R2_ENDPOINT=%s\n' "${RESTORE_R2_ENDPOINT}"
  printf 'RESTORE_R2_BUCKET=%s\n' "${RESTORE_R2_BUCKET}"
  printf 'RESTORE_R2_ACCESS_KEY=%s\n' "${RESTORE_R2_ACCESS_KEY}"
  printf 'RESTORE_R2_SECRET_KEY=%s\n' "${RESTORE_R2_SECRET_KEY}"
} > "${env_tmp}"
scp_stage "${env_tmp}" "root@${stage_ip}:/root/rehearsal.env"
ssh_stage chmod 600 /root/rehearsal.env

for src in linode r2; do
  log "rehearsing restore from ${src} onto the stage DB" \
    "(over SSH, on the stage box's OWN loopback Postgres)…"
  ssh_stage bash -c \
    'set -a; . /root/rehearsal.env; set +a;
     bash /root/restore.sh --i-understand-this-overwrites --source '"${src}"
  log "restore from ${src}: OK + verified"
done

log "REHEARSAL PASSED — both 3-2-1 copies restore. (stage will now be destroyed)"
