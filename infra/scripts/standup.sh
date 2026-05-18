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
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"; readonly INFRA_DIR
readonly TF_DIR="${INFRA_DIR}/terraform/prod"
readonly ANSIBLE_DIR="${INFRA_DIR}/ansible"
readonly INVENTORY="${ANSIBLE_DIR}/inventory/hosts.yml"   # generated, gitignored

DRY_RUN=0

# Runtime app secrets that MUST be pre-supplied (operator env / gated GitHub
# Environment). Mirrors the secrets_vault map. The backup-writer keys are NOT
# here — they are produced by tofu and exported post-apply.
readonly REQUIRED_ARXII=(
  ARXII_PG_PASSWORD ARXII_DJANGO_SECRET_KEY ARXII_CLOUDINARY_URL
  ARXII_RESEND_API_KEY ARXII_R2_ACCESS_KEY_ID ARXII_R2_SECRET_ACCESS_KEY
  ARXII_OFFBOX_ALERT_TOKEN ARXII_CADDY_CF_DNS_TOKEN
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
  local v
  for v in "${REQUIRED_BACKEND[@]}" "${REQUIRED_ARXII[@]}"; do
    [[ -n "${!v:-}" ]] || fail "required env '${v}' is missing/empty"
  done
}

main() {
  preflight

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY RUN — would run, in order (NO destroy, NO restore):"
    log "  1. tofu -chdir='${TF_DIR}' init  (S3 backend from TF_STATE_*)"
    log "  2. tofu -chdir='${TF_DIR}' apply -auto-approve   (APPLY-ONLY)"
    log "  3. generate ${INVENTORY} (0600) from tofu output instance_ipv4"
    log "  4. export tofu-produced backup-writer keys -> ARXII_BACKUP_WRITER_*"
    log "  5. ansible-playbook -i '${INVENTORY}' '${ANSIBLE_DIR}/site.yml'"
    log "No changes made."
    exit 0
  fi

  log "Provisioning (apply-only)…"
  TF_VAR_linode_token="${LINODE_TOKEN}" \
  TF_VAR_cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  tofu -chdir="${TF_DIR}" init -input=false \
    -backend-config="bucket=${TF_STATE_BUCKET}" \
    -backend-config="key=${TF_STATE_KEY}" \
    -backend-config="region=${TF_STATE_REGION}" \
    -backend-config="endpoint=${TF_STATE_ENDPOINT}" \
    -backend-config="access_key=${TF_STATE_S3_ACCESS_KEY}" \
    -backend-config="secret_key=${TF_STATE_S3_SECRET_KEY}" \
    -backend-config="skip_credentials_validation=true" \
    -backend-config="skip_region_validation=true" \
    -backend-config="use_path_style=true"

  TF_VAR_linode_token="${LINODE_TOKEN}" \
  TF_VAR_cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  tofu -chdir="${TF_DIR}" apply -auto-approve -input=false   # APPLY-ONLY; no destroy path exists

  log "Generating inventory from tofu output…"
  local ip
  ip="$(tofu -chdir="${TF_DIR}" output -raw instance_ipv4)"
  install -d -m 0750 "${ANSIBLE_DIR}/inventory"
  umask 077
  cat > "${INVENTORY}" <<EOF
arxii_prod:
  hosts:
    prod:
      ansible_host: ${ip}
      ansible_user: arxii
EOF

  log "Converging host (idempotent)…"
  # Backup-writer keys are produced by tofu (sensitive outputs) and handed to
  # ansible via env in-memory — never written to disk/log, never --extra-vars.
  ARXII_BACKUP_WRITER_ACCESS_KEY="$(tofu -chdir="${TF_DIR}" output -raw backup_writer_access_key)" \
  ARXII_BACKUP_WRITER_SECRET_KEY="$(tofu -chdir="${TF_DIR}" output -raw backup_writer_secret_key)" \
  ansible-playbook -i "${INVENTORY}" "${ANSIBLE_DIR}/site.yml"

  log "Stand-up complete. (Reminder: revoke the provisioning tokens at the provider — see README.)"
}

main "$@"
