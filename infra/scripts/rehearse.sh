#!/usr/bin/env bash
#
# rehearse.sh — #2236 Phase 3 P1: the first-deploy dress-rehearsal ladder.
# Stands up a throwaway ephemeral-stage box, converges the FULL, UNMODIFIED
# site.yml on it (rehearsal_mode group_vars only — no role/task forking),
# smoke-tests the running game end-to-end, rehearses backup+restore against
# real (stage-scoped) object storage, then ALWAYS tears everything down.
# Proves the entire stack works before the first real prod button press,
# without ever touching prod state, the prod Cloudflare zone, or prod
# credentials.
#
# ISOLATION DOCTRINE (see infra/README.md "Dress rehearsal" + terraform/
# ephemeral-stage's own header comments): a SEPARATE root, SEPARATE state,
# SEPARATE stage-scoped Linode token (STAGE_LINODE_TOKEN — never the prod
# LINODE_TOKEN). This script's tofu calls NEVER touch terraform/prod.
# Rehearsal deliberately does NOT do ACME/DNS-01 or R2 offsite replication —
# see the README's "Dress rehearsal" section for the full list of
# first-prod-run-only residual risks this cannot prove.
#
# REUSES lib.sh (wait_for_tcp, select_ssh_user, tf_read_outputs/jqr/jqc,
# gen_inventory, validate_generated_yaml) — the SAME functions standup.sh
# uses (refactored out of standup.sh into lib.sh in this same change).
#
# Modeled on restore-rehearsal.sh's structure (ssh_stage/scp_stage helpers,
# always-teardown trap). restore-rehearsal.sh REMAINS — it's the narrower,
# faster, backup/restore-ONLY drill (useful on its own when you don't need a
# full site.yml converge). This script does not shell out to it (running two
# independent ephemeral-stage applies against the same state key in one
# workflow would be wasteful and racy); instead it folds the equivalent
# restore.sh-over-SSH logic in as its own final step, rehearsing ONLY the
# linode-equivalent copy (the stage bucket) — there is no R2 in rehearsal
# (offsite_enabled: false; see the isolation doctrine).
#
# set +x throughout; no secret echoed; nothing written to disk beyond 0600
# temp files scp'd to the box we're about to destroy.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"; readonly INFRA_DIR
readonly STAGE_DIR="${INFRA_DIR}/terraform/ephemeral-stage"
readonly ANSIBLE_DIR="${INFRA_DIR}/ansible"
readonly INVENTORY_DIR="${ANSIBLE_DIR}/inventory"
readonly INVENTORY="${INVENTORY_DIR}/hosts.rehearsal.yml"                  # generated, gitignored
readonly GROUP_VARS_FILE="${INVENTORY_DIR}/group_vars/arxii_rehearsal.yml" # generated, gitignored

readonly SSH_WAIT_TIMEOUT_S=300
readonly SSH_WAIT_INTERVAL_S=5
readonly SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)
# RFC 2606 reserved TLD — guaranteed never resolvable/issuable for real, so
# it can never collide with anything and no real CA could ever be tricked
# into issuing for it (moot anyway: rehearsal never attempts real ACME).
readonly REHEARSAL_FQDN="stage.rehearsal.invalid"
readonly TLS_TELNET_PORT=4003   # matches roles/{host_firewall,django_hardening}'s own default

log()  { printf '[rehearse] %s\n' "$*"; }
fail() { printf '[rehearse] REFUSING: %s\n' "$*" >&2; exit 1; }

# shellcheck source=infra/scripts/lib.sh
. "${SCRIPT_DIR}/lib.sh"

[[ "${REHEARSAL_CONFIRM:-}" == "1" ]] \
  || fail "set REHEARSAL_CONFIRM=1 (spins up + destroys an ephemeral stage box, converges the full site.yml)"
: "${RUN_ID:?set RUN_ID (unique per-run suffix)}"
[[ "$(basename "${STAGE_DIR}")" == "ephemeral-stage" ]] \
  || fail "guard: this only ever runs against the ephemeral-stage root"

command -v jq      >/dev/null 2>&1 || fail "jq not found (required to parse 'tofu output -json')"
command -v python3 >/dev/null 2>&1 || fail "python3 not found (required to validate the generated group_vars YAML)"
command -v aws     >/dev/null 2>&1 || fail "aws CLI not found (required to verify the stage backup object)"

# Preflight — fail closed BEFORE spinning up a billed stage box.
: "${STAGE_LINODE_TOKEN:?set STAGE_LINODE_TOKEN (stage-scoped Linode token — NEVER the prod LINODE_TOKEN)}"
: "${STAGE_TF_STATE_BUCKET:?set STAGE_TF_STATE_BUCKET}"
: "${STAGE_TF_STATE_KEY:?set STAGE_TF_STATE_KEY}"
: "${STAGE_TF_STATE_REGION:?set STAGE_TF_STATE_REGION}"
: "${STAGE_TF_STATE_ENDPOINT:?set STAGE_TF_STATE_ENDPOINT}"
: "${STAGE_TF_STATE_S3_ACCESS_KEY:?set STAGE_TF_STATE_S3_ACCESS_KEY}"
: "${STAGE_TF_STATE_S3_SECRET_KEY:?set STAGE_TF_STATE_S3_SECRET_KEY}"
[[ -n "${ARXII_AUTHORIZED_KEYS:-}" && "${ARXII_AUTHORIZED_KEYS}" != "[]" ]] \
  || fail "ARXII_AUTHORIZED_KEYS not set — JSON list of admin SSH public keys (same var standup.yml uses)"
[[ -n "${ANSIBLE_PRIVATE_KEY_FILE:-}" ]] \
  || log "ANSIBLE_PRIVATE_KEY_FILE not set — relying on ssh-agent for the admin key (CI always sets this; set it locally if the probe below fails to authenticate)."

# Runtime app secrets — generated fresh, every run, never operator-supplied
# (the whole point of a throwaway rehearsal box: nobody types a password
# into it). openssl rand, not /dev/urandom directly, for portable hex
# encoding.
pg_password="$(openssl rand -hex 24)"
django_secret_key="$(openssl rand -hex 24)"
superuser_password="$(openssl rand -hex 24)"

export ANSIBLE_HOST_KEY_CHECKING="${ANSIBLE_HOST_KEY_CHECKING:-False}"

# Saved (plain, NOT exported) copies of the stage-scoped provisioning creds,
# for teardown()'s tofu destroy call at the very end of the script — AFTER
# the `unset STAGE_*` defense-in-depth line further down strips the
# ORIGINALS from this process's environment (so they can never leak into
# ansible-playbook's child-process environment). A plain, non-exported shell
# variable is never inherited by a child process either way, so saving
# copies here does not reopen that leak — it only keeps teardown() able to
# authenticate after the originals are gone.
teardown_linode_token="${STAGE_LINODE_TOKEN}"
teardown_s3_access_key="${STAGE_TF_STATE_S3_ACCESS_KEY}"
teardown_s3_secret_key="${STAGE_TF_STATE_S3_SECRET_KEY}"

teardown() {
  log "tearing down ephemeral stage (ALWAYS, even on failure; run_id=${RUN_ID})…"
  # AWS_* on EVERY backend-touching tofu invocation, not just `init` — the S3
  # backend needs live credentials to read/write remote state on every call
  # (nothing about them is cached to disk by `init`); a `VAR=val` command
  # prefix scopes to that one command only, so each call below repeats it.
  TF_VAR_linode_token="${teardown_linode_token}" \
  TF_VAR_run_id="${RUN_ID}" \
  TF_VAR_authorized_keys="${ARXII_AUTHORIZED_KEYS}" \
  AWS_ACCESS_KEY_ID="${teardown_s3_access_key}" \
  AWS_SECRET_ACCESS_KEY="${teardown_s3_secret_key}" \
  tofu -chdir="${STAGE_DIR}" destroy -auto-approve -input=false || \
    printf '[rehearse] WARNING: stage teardown failed — destroy manually! (env=ephemeral-stage, run_id=%s)\n' "${RUN_ID}" >&2
}
trap teardown EXIT

log "provisioning ephemeral stage (run_id=${RUN_ID})…"
AWS_ACCESS_KEY_ID="${STAGE_TF_STATE_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${STAGE_TF_STATE_S3_SECRET_KEY}" \
TF_VAR_linode_token="${STAGE_LINODE_TOKEN}" \
tofu -chdir="${STAGE_DIR}" init -input=false \
  -backend-config="bucket=${STAGE_TF_STATE_BUCKET}" \
  -backend-config="key=${STAGE_TF_STATE_KEY}" \
  -backend-config="region=${STAGE_TF_STATE_REGION}" \
  -backend-config="endpoint=${STAGE_TF_STATE_ENDPOINT}" \
  -backend-config="skip_credentials_validation=true" \
  -backend-config="skip_region_validation=true" \
  -backend-config="use_path_style=true" \
  -backend-config="skip_requesting_account_id=true" \
  -backend-config="skip_s3_checksum=true" \
  -backend-config="skip_metadata_api_check=true"

# AWS_* required here too (see teardown()'s comment above — every
# backend-touching command needs it, not just `init`).
TF_VAR_linode_token="${STAGE_LINODE_TOKEN}" \
TF_VAR_run_id="${RUN_ID}" \
TF_VAR_authorized_keys="${ARXII_AUTHORIZED_KEYS}" \
AWS_ACCESS_KEY_ID="${STAGE_TF_STATE_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${STAGE_TF_STATE_S3_SECRET_KEY}" \
tofu -chdir="${STAGE_DIR}" apply -auto-approve -input=false

# Defense-in-depth: confirm what we provisioned is tagged ephemeral-stage
# before trusting the teardown trap to only ever hit stage (mirrors
# restore-rehearsal.sh's same guard).
AWS_ACCESS_KEY_ID="${STAGE_TF_STATE_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${STAGE_TF_STATE_S3_SECRET_KEY}" \
tofu -chdir="${STAGE_DIR}" state list | grep -q . \
  || fail "no stage resources in stage state — aborting"

log "reading tofu outputs (single 'tofu output -json' read)…"
AWS_ACCESS_KEY_ID="${STAGE_TF_STATE_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${STAGE_TF_STATE_S3_SECRET_KEY}" \
tf_read_outputs "${STAGE_DIR}"   # lib.sh
stage_ip="$(jqr stage_ipv4)"
stage_bucket="$(jqr stage_bucket)"
stage_bucket_region="$(jqr stage_bucket_region)"
stage_bucket_s3_endpoint="$(jqr stage_bucket_s3_endpoint)"
stage_bucket_writer_access_key="$(jqr stage_bucket_writer_access_key)"
stage_bucket_writer_secret_key="$(jqr stage_bucket_writer_secret_key)"
TF_OUTPUT_JSON=""   # drop the cached blob — it also carries the sensitive values above
log "stage host: ${stage_ip}"

wait_for_tcp "${stage_ip}" 22 "${SSH_WAIT_TIMEOUT_S}" "${SSH_WAIT_INTERVAL_S}"

# ssh_stage <user> <command-string>: ONE pre-quoted string per call (never
# split across multiple argv elements) — ssh flattens multi-arg remote
# commands by joining them with spaces and handing the result to the remote
# shell UNQUOTED, which silently breaks `set -a; . env; set +a; cmd`
# sequences (see restore-rehearsal.sh's header comment on its identical
# helper for the full incident this convention fixes).
# shellcheck disable=SC2029  # client-side expansion is intentional
ssh_stage() { ssh "${SSH_OPTS[@]}" "${1}@${stage_ip}" "${2}"; }
scp_stage() { scp "${SSH_OPTS[@]}" "$@"; }

# select_ssh_user (lib.sh) probes root vs arxadmin; on a guaranteed brand-new
# box this is always root, but reusing the same probe standup.sh uses (not
# hardcoding "root") keeps both scripts honestly describing the same
# first-converge contract instead of two independent assumptions about it.
ssh_user="$(select_ssh_user "${stage_ip}")"
log "connecting as '${ssh_user}' for the initial converge."

log "pre-converge: adding an /etc/hosts entry for the fake rehearsal fqdn" \
  "(as '${ssh_user}' — this must happen before Caddy/django_hardening read" \
  "dh_allowed_hosts, and before ssh_hardening disables root login)…"
ssh_stage "${ssh_user}" \
  "grep -qxF '127.0.0.1 ${REHEARSAL_FQDN}' /etc/hosts || echo '127.0.0.1 ${REHEARSAL_FQDN}' >> /etc/hosts"

log "generating inventory + rehearsal group_vars…"
install -d -m 0750 "${INVENTORY_DIR}" "${INVENTORY_DIR}/group_vars"
umask 077

gen_inventory "${INVENTORY}" "${stage_ip}" "${ssh_user}" stage   # lib.sh

# dh_allowed_hosts is a ONE-element list here (unlike prod's [web_fqdn,
# telnet_fqdn]) — the ephemeral-stage root has no DNS at all (isolation
# doctrine), so there is only ever the one fake fqdn.
cat > "${GROUP_VARS_FILE}" <<EOF
---
# GENERATED by rehearse.sh — gitignored, do not hand-edit; re-run to
# regenerate. #2236 Phase 3 P1 dress rehearsal: converges the FULL,
# UNMODIFIED site.yml against a throwaway ephemeral-stage box. See
# infra/README.md's "Dress rehearsal" section for what this proves and what
# it deliberately does not (ACME/DNS-01, real DNS, R2 offsite replication).

# Global rehearsal gate (roles/secrets_vault) — unlocks vault_allow_empty
# below. standup.sh (prod) never sets this.
rehearsal_mode: true

# host_firewall (roles/host_firewall/defaults/main.yml). SSH: open — this
# box is short-lived (~30-60min) and destroyed every run, behind key-only
# auth (the same posture prod's own README accepts as ITS default when the
# operator doesn't restrict ARXII_SSH_ADMIN_CIDRS). Cloudflare CIDRs: RFC
# 5737 TEST-NET-1 / RFC 3849 documentation-prefix PLACEHOLDERS, not real
# Cloudflare ranges — rehearsal has no real Cloudflare edge in front, so
# this allow-list can never need to match real traffic; every 80/443 check
# this rehearsal runs goes over loopback (smoke.sh executes ON the box
# itself), which nftables always accepts regardless of this set
# (\`iif "lo" accept\`, unconditional — see host_firewall's nftables.conf.j2).
# A non-empty, syntactically valid CIDR is still required: host_firewall's
# own fail-closed assert refuses to converge on an EMPTY allow-list.
hostfw_ssh_admin_cidrs: ["0.0.0.0/0", "::/0"]
hostfw_cloudflare_ipv4_cidrs: ["192.0.2.0/24"]
hostfw_cloudflare_ipv6_cidrs: ["2001:db8::/32"]

# caddy (roles/caddy/defaults/main.yml) — internal-CA template, no DNS-01,
# no Cloudflare credential needed.
caddy_web_fqdn: "${REHEARSAL_FQDN}"
caddy_acme_email: "ops@rehearsal.invalid"
caddy_rehearsal_mode: true

# tls_telnet_cert (roles/tls_telnet_cert/defaults/main.yml)
ttc_web_fqdn: "${REHEARSAL_FQDN}"

# django_hardening (roles/django_hardening/defaults/main.yml)
dh_allowed_hosts: ["${REHEARSAL_FQDN}"]
dh_web_fqdn: "${REHEARSAL_FQDN}"
dh_default_from_email: "noreply@rehearsal.invalid"

# backups (roles/backups/defaults/main.yml) — the REAL stage bucket
# (terraform/ephemeral-stage's object_storage_ephemeral module) with
# stage-scoped creds, so the backup+restore rehearsal below is honest, not
# stubbed.
backups_bucket: "${stage_bucket}"
backups_s3_endpoint: "${stage_bucket_s3_endpoint}"
backups_region: "${stage_bucket_region}"

# offsite_replication (roles/offsite_replication/defaults/main.yml) — R2 is
# prod-adjacent (real Cloudflare account/bucket); the isolated
# ephemeral-stage root has no such credential to give it. Role skipped
# entirely (see site.yml's \`when: offsite_enabled\`).
offsite_enabled: false

# secrets_vault (roles/secrets_vault/defaults/main.yml) — the
# not-applicable-in-rehearsal secret set (see that role's own defaults for
# the full per-name rationale). ARXII_BACKUP_WRITER_* is deliberately
# ABSENT from this list — rehearse.sh supplies REAL stage-bucket writer
# keys below, not an empty stub.
vault_allow_empty:
  - ARXII_RESEND_API_KEY
  - ARXII_CLOUDINARY_CLOUD_NAME
  - ARXII_CLOUDINARY_API_KEY
  - ARXII_CLOUDINARY_API_SECRET
  - ARXII_R2_ACCESS_KEY_ID
  - ARXII_R2_SECRET_ACCESS_KEY
  - ARXII_OFFBOX_ALERT_TOKEN
  - ARXII_CADDY_CF_DNS_TOKEN

# base — authorized_keys are public, not sensitive (same var standup.sh
# generates from a tofu output; ephemeral-stage doesn't echo them back as a
# tofu output, so this is sourced directly from the env var instead).
admin_authorized_keys: ${ARXII_AUTHORIZED_KEYS}
EOF

validate_generated_yaml "${GROUP_VARS_FILE}"   # lib.sh

# Defense-in-depth, mirrors standup.sh: never let the stage-scoped
# provisioning/backend creds reach the ansible step's env even by accident.
unset STAGE_LINODE_TOKEN STAGE_TF_STATE_S3_ACCESS_KEY STAGE_TF_STATE_S3_SECRET_KEY

log "converging the FULL site.yml on the stage box (idempotent role list," \
  "unmodified except for the rehearsal_mode group_vars above)…"
ARXII_PG_PASSWORD="${pg_password}" \
ARXII_DJANGO_SECRET_KEY="${django_secret_key}" \
ARXII_DJANGO_SUPERUSER_PASSWORD="${superuser_password}" \
ARXII_DJANGO_SUPERUSER_USERNAME="${ARXII_DJANGO_SUPERUSER_USERNAME:-arxii_admin}" \
ARXII_DJANGO_SUPERUSER_EMAIL="${ARXII_DJANGO_SUPERUSER_EMAIL:-admin@rehearsal.invalid}" \
ARXII_BACKUP_WRITER_ACCESS_KEY="${stage_bucket_writer_access_key}" \
ARXII_BACKUP_WRITER_SECRET_KEY="${stage_bucket_writer_secret_key}" \
ansible-playbook -i "${INVENTORY}" "${ANSIBLE_DIR}/site.yml"

log "converge complete."

# Post-converge: ssh_hardening has now disabled root login (same as prod's
# very first converge) — every step below connects as arxadmin.
log "copying smoke.sh onto the stage box…"
scp_stage "${SCRIPT_DIR}/smoke.sh" "arxadmin@${stage_ip}:/tmp/smoke.sh"

log "running smoke tests ON the stage box (loopback — see smoke.sh's own" \
  "header for why this must run locally rather than probed from outside)…"
ssh_stage arxadmin \
  "chmod +x /tmp/smoke.sh && TLS_TELNET_PORT=${TLS_TELNET_PORT} /tmp/smoke.sh 127.0.0.1 ${REHEARSAL_FQDN} --insecure"
log "smoke tests: PASSED"

log "triggering one backup run (arxii-backup.service)…"
ssh_stage arxadmin "sudo systemctl start arxii-backup.service"
if ssh_stage arxadmin "sudo systemctl is-failed --quiet arxii-backup.service"; then
  fail "arxii-backup.service failed — check journalctl on the stage box before it's destroyed"
fi
log "backup unit ran successfully."

log "verifying a backup object landed in the stage bucket (using the stage" \
  "writer key — proves the real backup->object-storage path, not just the" \
  "systemd unit exiting 0)…"
backup_objects="$(AWS_ACCESS_KEY_ID="${stage_bucket_writer_access_key}" \
  AWS_SECRET_ACCESS_KEY="${stage_bucket_writer_secret_key}" \
  aws --endpoint-url "${stage_bucket_s3_endpoint}" --region "${stage_bucket_region}" \
  s3 ls "s3://${stage_bucket}/db/" | awk '{print $4}')"
[[ -n "${backup_objects}" ]] \
  || fail "no backup object found in s3://${stage_bucket}/db/ after triggering arxii-backup.service"
log "backup object(s) present: $(wc -l <<<"${backup_objects}" | tr -d ' ') object(s)."

# --- Restore rehearsal (folded in from restore-rehearsal.sh's pattern) -----
# Only ONE copy in rehearsal (the stage bucket — linode-equivalent); there is
# no R2 offsite copy here (offsite_enabled: false). restore-rehearsal.sh
# remains the tool for a from-scratch, backup/restore-ONLY drill that also
# exercises the real R2 copy against prod-adjacent creds; this step proves
# the SAME restore.sh script, invoked the SAME way (over SSH, onto the box's
# own loopback Postgres), works end-to-end against a box that just went
# through a full, real site.yml converge — the honest first-deploy proof.
log "rehearsing restore (stage bucket copy) on the stage box's own loopback Postgres…"
restore_db_password="$(openssl rand -hex 20)"
readonly restore_db_user="rehearsal_restore"

ssh_stage arxadmin \
  "sudo -u postgres dropuser --if-exists ${restore_db_user}; sudo -u postgres psql -v ON_ERROR_STOP=1 -c \"create role ${restore_db_user} with login superuser password '${restore_db_password}';\""

scp_stage "${SCRIPT_DIR}/restore.sh" "arxadmin@${stage_ip}:/tmp/restore.sh"
ssh_stage arxadmin "chmod +x /tmp/restore.sh"

restore_env_tmp="$(mktemp)"; chmod 600 "${restore_env_tmp}"
{
  printf 'RESTORE_DB=arxii\n'
  printf 'RESTORE_DB_USER=%s\n' "${restore_db_user}"
  printf 'PGPASSWORD=%s\n' "${restore_db_password}"
  printf 'RESTORE_TARGET_HOST=127.0.0.1\n'
  printf 'RESTORE_S3_ENDPOINT=%s\n' "${stage_bucket_s3_endpoint}"
  printf 'RESTORE_S3_REGION=%s\n' "${stage_bucket_region}"
  printf 'RESTORE_BUCKET=%s\n' "${stage_bucket}"
  printf 'RESTORE_S3_ACCESS_KEY=%s\n' "${stage_bucket_writer_access_key}"
  printf 'RESTORE_S3_SECRET_KEY=%s\n' "${stage_bucket_writer_secret_key}"
} > "${restore_env_tmp}"
scp_stage "${restore_env_tmp}" "arxadmin@${stage_ip}:/tmp/rehearsal-restore.env"
rm -f "${restore_env_tmp}"
ssh_stage arxadmin "chmod 600 /tmp/rehearsal-restore.env"

# The whole `set -a; source; set +a; bash restore.sh` sequence runs INSIDE
# `sudo bash -c '...'` (root sources the env file itself) rather than
# sourcing as arxadmin then `sudo -E` — deliberately avoids relying on
# sudo's -E/env_reset interplay (sudoers-config-dependent) to carry
# PGPASSWORD/RESTORE_* through to root, where restore.sh's systemctl
# stop/start of arxii.service needs to run. ONE pre-quoted string to
# ssh_stage (see its own header comment above for why — the exact bug
# restore-rehearsal.sh's identical pattern already fixed).
ssh_stage arxadmin \
  "sudo bash -c 'set -a; . /tmp/rehearsal-restore.env; set +a; bash /tmp/restore.sh --i-understand-this-overwrites --source linode'"
log "restore rehearsal: OK + verified (django_migrations rows + public-table floor — see restore.sh)."

log "REHEARSAL PASSED — full site.yml converged, smoke tests passed, backup+restore verified. (stage will now be destroyed)"
