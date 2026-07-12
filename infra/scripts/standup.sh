#!/usr/bin/env bash
#
# standup.sh — "the button". Preflight, provision (tofu apply, APPLY-ONLY),
# then converge (ansible-playbook site.yml). Same script the CI
# workflow_dispatch button invokes (DRY — one source of truth).
#
# SAFETY CONTRACT (enforced here; see infra/README.md):
#   - APPLY-ONLY. NEVER runs `tofu destroy`, never restores data, never
#     re-inits an existing DB. Idempotent: safe to re-run (no-op if nothing
#     changed; prevent_destroy makes a ForceNew edit hard-fail, not replace).
#   - Restore is a SEPARATE human-gated tool: scripts/restore.sh. Unreachable
#     from here.
#   - Fail-closed: any missing prerequisite => refuse, exit 1, change nothing.
#   - Secrets: reach the host ONLY as env -> the secrets_vault role's 0600
#     EnvironmentFile. NEVER --extra-vars (process table). No secret echoed;
#     `set +x` around anything secret-adjacent. No secret in the (public) repo.
#   - Provisioning tokens (LINODE_TOKEN, CLOUDFLARE_API_TOKEN, TF_STATE_S3_*)
#     are unset from this process's env before ansible-playbook runs —
#     defense-in-depth so they can never leak onto the box even by accident;
#     secrets_vault asserts their absence from the controller env.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"; readonly INFRA_DIR
readonly TF_DIR="${INFRA_DIR}/terraform/prod"
readonly ANSIBLE_DIR="${INFRA_DIR}/ansible"
readonly INVENTORY_DIR="${ANSIBLE_DIR}/inventory"
readonly INVENTORY="${INVENTORY_DIR}/hosts.yml"                       # generated, gitignored
readonly GROUP_VARS_FILE="${INVENTORY_DIR}/group_vars/arxii_prod.yml" # generated, gitignored

readonly SSH_WAIT_TIMEOUT_S=300
readonly SSH_WAIT_INTERVAL_S=5

DRY_RUN=0

# Runtime app secrets that MUST be pre-supplied (operator env / gated GitHub
# Environment). Mirrors the secrets_vault map. The backup-writer keys are NOT
# here — they are produced by tofu and exported post-apply.
readonly REQUIRED_ARXII=(
  ARXII_PG_PASSWORD ARXII_DJANGO_SECRET_KEY
  ARXII_CLOUDINARY_CLOUD_NAME ARXII_CLOUDINARY_API_KEY ARXII_CLOUDINARY_API_SECRET
  ARXII_RESEND_API_KEY ARXII_R2_ACCESS_KEY_ID ARXII_R2_SECRET_ACCESS_KEY
  ARXII_OFFBOX_ALERT_TOKEN ARXII_CADDY_CF_DNS_TOKEN
  ARXII_DJANGO_SUPERUSER_PASSWORD
)
# S3 backend config for the prod remote state (bootstrap output + the
# manually-created scoped state key). Operator/CI-only.
readonly REQUIRED_BACKEND=(
  TF_STATE_BUCKET TF_STATE_ENDPOINT TF_STATE_REGION TF_STATE_KEY
  TF_STATE_S3_ACCESS_KEY TF_STATE_S3_SECRET_KEY
)

usage() {
  cat <<'EOF'
Usage: standup.sh [--dry-run]
  --dry-run   Print the ordered steps and exit; perform no changes.

Required (missing any => refuse, change nothing):
  LINODE_TOKEN, CLOUDFLARE_API_TOKEN          provisioning (never on the box)
  TF_STATE_BOOTSTRAPPED=1                      one-time bootstrap done
  TF_STATE_*                                   prod S3 backend config
  TF_VAR_ssh_admin_cidrs                       JSON list, operator decision
  ARXII_*                                      runtime app secrets (env-only)
See infra/README.md for the full gated-Environment contract.
EOF
}

log()  { printf '[standup] %s\n' "$*"; }
fail() { printf '[standup] REFUSING: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown argument: $1" ;;
  esac
done

# Presence checks only — never print values; do not add `set -x` here.
preflight() {
  [[ -n "${LINODE_TOKEN:-}" ]]         || fail "LINODE_TOKEN not set (operator/CI-only; never on the box)"
  [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]] || fail "CLOUDFLARE_API_TOKEN not set"
  [[ "${TF_STATE_BOOTSTRAPPED:-}" == "1" ]] \
      || fail "remote-state bootstrap not done (run terraform/bootstrap once; export TF_STATE_BOOTSTRAPPED=1)"
  # SSH admin CIDR allowlist is a conscious operator decision, not a silent
  # default — see infra/README.md "DECISION — SSH admin source CIDR
  # allowlist". An empty/unset value refuses rather than falling back to the
  # Terraform variable's open (0.0.0.0/0, ::/0) default.
  [[ -n "${TF_VAR_ssh_admin_cidrs:-}" && "${TF_VAR_ssh_admin_cidrs}" != "[]" ]] \
      || fail "TF_VAR_ssh_admin_cidrs not set — must be a JSON list of operator" \
              "CIDRs (e.g. '[\"203.0.113.10/32\"]'); a conscious decision, see README.md"
  local v
  for v in "${REQUIRED_BACKEND[@]}" "${REQUIRED_ARXII[@]}"; do
    [[ -n "${!v:-}" ]] || fail "required env '${v}' is missing/empty"
  done
}

# tofu output -raw "$1" against the prod root.
tf_out() { tofu -chdir="${TF_DIR}" output -raw "$1"; }
# tofu output -json "$1" against the prod root — already a valid YAML flow
# sequence, embedded directly into the generated group_vars file below.
tf_out_json() { tofu -chdir="${TF_DIR}" output -json "$1"; }

# Bounded poll for the host's SSH port — brand-new host every run by design
# (Terraform just created the Linode), so there is no "known reachable"
# assumption to make; wait rather than let ansible-playbook's first task
# fail-fast on connection refused.
wait_for_ssh() {
  local ip="$1" waited=0
  log "Waiting for SSH (port 22) on ${ip} (up to ${SSH_WAIT_TIMEOUT_S}s)…"
  until timeout 5 bash -c "true >/dev/tcp/${ip}/22" 2>/dev/null; do
    waited=$((waited + SSH_WAIT_INTERVAL_S))
    if [[ "${waited}" -ge "${SSH_WAIT_TIMEOUT_S}" ]]; then
      fail "SSH port 22 on ${ip} did not open within ${SSH_WAIT_TIMEOUT_S}s"
    fi
    sleep "${SSH_WAIT_INTERVAL_S}"
  done
  log "SSH port open."
}

# First run: Linode injects the admin keypair into ROOT (cloud-init has no
# arxadmin user yet — the base role creates it). Later runs: the base role
# has already created arxadmin+key and ssh_hardening has disabled root
# login, so root no longer answers. Probe non-destructively and pick
# whichever answers; site.yml's base role is idempotent either way.
select_ssh_user() {
  local ip="$1"
  local -a key_args=()
  # Not fatal: CI always sets this (standup.yml exports
  # ANSIBLE_PRIVATE_KEY_FILE before invoking this script); a local operator
  # run may instead rely on ssh-agent already holding the key, which this
  # probe (and ansible-playbook itself) will happily use with no -i flag.
  # Just a nudge in case that assumption is wrong.
  [[ -n "${ANSIBLE_PRIVATE_KEY_FILE:-}" ]] || \
    log "ANSIBLE_PRIVATE_KEY_FILE not set — relying on ssh-agent for the admin key (CI always sets this; set it locally if the probe below fails to authenticate)."
  [[ -n "${ANSIBLE_PRIVATE_KEY_FILE:-}" ]] && key_args=(-i "${ANSIBLE_PRIVATE_KEY_FILE}")
  if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
      "${key_args[@]}" "arxadmin@${ip}" true 2>/dev/null; then
    echo "arxadmin"
  else
    echo "root"
  fi
}

main() {
  preflight

  # Brand-new host every run by design (no prior known_hosts entry can
  # exist) — CI already sets this; this makes the local fallback path
  # equivalent instead of hanging on a host-key prompt.
  export ANSIBLE_HOST_KEY_CHECKING="${ANSIBLE_HOST_KEY_CHECKING:-False}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY RUN — would run, in order (NO destroy, NO restore):"
    log "  1. tofu -chdir='${TF_DIR}' init  (S3 backend from TF_STATE_*, Linode-compatible flags)"
    log "  2. tofu -chdir='${TF_DIR}' apply -auto-approve   (APPLY-ONLY)"
    log "  3. capture all tofu outputs (ip, fqdns, buckets, endpoints, ports, keys) into shell vars"
    log "  4. wait for SSH (port 22) on the new host, up to ${SSH_WAIT_TIMEOUT_S}s"
    log "  5. probe ssh as arxadmin, else root -> resolved ansible_user"
    log "  6. generate ${INVENTORY} (0600)"
    log "  7. generate ${GROUP_VARS_FILE} (0600) from tofu output + env"
    log "  8. unset LINODE_TOKEN CLOUDFLARE_API_TOKEN TF_STATE_S3_ACCESS_KEY TF_STATE_S3_SECRET_KEY"
    log "  9. ansible-playbook -i '${INVENTORY}' '${ANSIBLE_DIR}/site.yml' (writer keys inline env)"
    log "No changes made."
    exit 0
  fi

  log "Provisioning (apply-only)…"
  # S3-backend creds via AWS_* env (NOT -backend-config args) so the secret
  # key never appears in any process argv. Non-secret backend config stays
  # as -backend-config. skip_requesting_account_id/skip_s3_checksum/
  # skip_metadata_api_check: this is a non-AWS S3-compatible store (Linode
  # Object Storage); the AWS SDK's account-id lookup and default checksum
  # headers aren't supported there and break the backend without these.
  AWS_ACCESS_KEY_ID="${TF_STATE_S3_ACCESS_KEY}" \
  AWS_SECRET_ACCESS_KEY="${TF_STATE_S3_SECRET_KEY}" \
  TF_VAR_linode_token="${LINODE_TOKEN}" \
  TF_VAR_cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  tofu -chdir="${TF_DIR}" init -input=false \
    -backend-config="bucket=${TF_STATE_BUCKET}" \
    -backend-config="key=${TF_STATE_KEY}" \
    -backend-config="region=${TF_STATE_REGION}" \
    -backend-config="endpoint=${TF_STATE_ENDPOINT}" \
    -backend-config="skip_credentials_validation=true" \
    -backend-config="skip_region_validation=true" \
    -backend-config="use_path_style=true" \
    -backend-config="skip_requesting_account_id=true" \
    -backend-config="skip_s3_checksum=true" \
    -backend-config="skip_metadata_api_check=true"

  TF_VAR_linode_token="${LINODE_TOKEN}" \
  TF_VAR_cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  tofu -chdir="${TF_DIR}" apply -auto-approve -input=false   # APPLY-ONLY; no destroy path exists

  log "Reading tofu outputs…"
  # Non-sensitive scalars.
  local ip web_fqdn telnet_fqdn backups_bucket backups_s3_endpoint backups_region
  local r2_offsite_bucket r2_s3_endpoint tls_telnet_port
  ip="$(tf_out instance_ipv4)"
  web_fqdn="$(tf_out web_fqdn)"
  telnet_fqdn="$(tf_out telnet_fqdn)"
  backups_bucket="$(tf_out backups_bucket)"
  backups_s3_endpoint="$(tf_out backups_s3_endpoint)"
  backups_region="$(tf_out region)"
  r2_offsite_bucket="$(tf_out r2_offsite_bucket)"
  r2_s3_endpoint="$(tf_out r2_s3_endpoint)"
  tls_telnet_port="$(tf_out tls_telnet_port)"
  # Non-sensitive lists — already valid YAML flow sequences.
  local cf_ipv4_cidrs_json cf_ipv6_cidrs_json ssh_admin_cidrs_json authorized_keys_json
  cf_ipv4_cidrs_json="$(tf_out_json cloudflare_ipv4_cidrs)"
  cf_ipv6_cidrs_json="$(tf_out_json cloudflare_ipv6_cidrs)"
  ssh_admin_cidrs_json="$(tf_out_json ssh_admin_cidrs)"
  authorized_keys_json="$(tf_out_json authorized_keys)"
  # Sensitive — produced by tofu, handed to ansible via env in-memory only.
  local backup_writer_access_key backup_writer_secret_key
  backup_writer_access_key="$(tf_out backup_writer_access_key)"
  backup_writer_secret_key="$(tf_out backup_writer_secret_key)"

  wait_for_ssh "${ip}"

  local ssh_user
  ssh_user="$(select_ssh_user "${ip}")"
  log "Connecting as '${ssh_user}'."

  log "Generating inventory + group_vars from tofu output…"
  install -d -m 0750 "${INVENTORY_DIR}" "${INVENTORY_DIR}/group_vars"
  umask 077

  # ansible_user: resolved by select_ssh_user above. First converge ever:
  # Linode injected the admin key into root (no arxadmin exists yet), so we
  # connect as root; the base role then creates arxadmin+key and
  # ssh_hardening disables root login, so every later run connects as
  # arxadmin instead.
  cat > "${INVENTORY}" <<EOF
arxii_prod:
  hosts:
    prod:
      ansible_host: ${ip}
      ansible_user: ${ssh_user}
EOF

  # dh_allowed_hosts includes both fqdns per django_hardening's own
  # defaults/main.yml contract ("= [web_fqdn, telnet_fqdn]").
  cat > "${GROUP_VARS_FILE}" <<EOF
---
# GENERATED by standup.sh from tofu output + env — gitignored, do not hand-
# edit; re-run the button to regenerate.

# host_firewall (roles/host_firewall/defaults/main.yml)
hostfw_ssh_admin_cidrs: ${ssh_admin_cidrs_json}
hostfw_cloudflare_ipv4_cidrs: ${cf_ipv4_cidrs_json}
hostfw_cloudflare_ipv6_cidrs: ${cf_ipv6_cidrs_json}
hostfw_tls_telnet_port: ${tls_telnet_port}

# caddy (roles/caddy/defaults/main.yml)
caddy_web_fqdn: "${web_fqdn}"
caddy_acme_email: "${ARXII_ACME_EMAIL:-admin@${TF_VAR_domain}}"

# tls_telnet_cert (roles/tls_telnet_cert/defaults/main.yml)
ttc_web_fqdn: "${web_fqdn}"

# django_hardening (roles/django_hardening/defaults/main.yml)
dh_allowed_hosts: ["${web_fqdn}", "${telnet_fqdn}"]
dh_web_fqdn: "${web_fqdn}"
dh_tls_telnet_port: ${tls_telnet_port}
dh_default_from_email: "noreply@${TF_VAR_domain}"

# backups (roles/backups/defaults/main.yml)
backups_bucket: "${backups_bucket}"
backups_s3_endpoint: "${backups_s3_endpoint}"
backups_region: "${backups_region}"

# offsite_replication (roles/offsite_replication/defaults/main.yml)
offsite_r2_bucket: "${r2_offsite_bucket}"
offsite_r2_endpoint: "${r2_s3_endpoint}"

# base — NEW var; authorized_keys are public, not sensitive. Consumed by a
# base-role task (Task B) that provisions the arxadmin login user.
admin_authorized_keys: ${authorized_keys_json}
EOF

  # Defense-in-depth: secrets_vault asserts these are absent from the
  # controller env. Captured into shell vars above (they need backend/
  # provisioning creds via `tofu output`); nothing after this point may call
  # `tofu output` again.
  unset LINODE_TOKEN CLOUDFLARE_API_TOKEN TF_STATE_S3_ACCESS_KEY TF_STATE_S3_SECRET_KEY

  log "Converging host (idempotent)…"
  # Backup-writer keys are handed to ansible via env in-memory — never
  # written to disk/log, never --extra-vars.
  ARXII_BACKUP_WRITER_ACCESS_KEY="${backup_writer_access_key}" \
  ARXII_BACKUP_WRITER_SECRET_KEY="${backup_writer_secret_key}" \
  ansible-playbook -i "${INVENTORY}" "${ANSIBLE_DIR}/site.yml"

  log "Stand-up complete. (Reminder: revoke the provisioning tokens at the provider — see README.)"
}

main "$@"
