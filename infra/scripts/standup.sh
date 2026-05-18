#!/usr/bin/env bash
#
# standup.sh — "the button". Validate prerequisites, then provision (tofu apply,
# apply-only) and converge (ansible-playbook site.yml).
#
# SAFETY CONTRACT (enforced here; see infra/README.md):
#   - Apply-only. This script NEVER runs `tofu destroy`, never restores data,
#     never re-initialises an existing database. Safe to re-run (idempotent).
#   - Restore is a SEPARATE, human-gated tool: scripts/restore.sh. It is not
#     reachable from here.
#   - Fail-closed: if any prerequisite is missing, refuse and exit non-zero
#     WITHOUT touching anything. (This is why running it today, before the
#     accounts exist, is harmless — it just refuses.)
#
# T1 scaffold: the preflight guards are real and active now. The actual
# `tofu apply` / `ansible-playbook` invocations are wired in task T25.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: standup.sh [--dry-run]

  --dry-run   Print the steps that would run and exit. Performs no changes.

Prerequisites (see infra/README.md). Missing any of these => refuse, exit 1,
change nothing:
  - LINODE_TOKEN        operator/CI Linode API token (NEVER stored on the box)
  - CLOUDFLARE_API_TOKEN operator/CI Cloudflare token
  - ANSIBLE_VAULT_PASS_PROVIDED=1  acknowledgement that the Ansible Vault
                        passphrase will be supplied interactively / via a
                        non-committed --vault-id (never a committed file)
  - TF_STATE_BOOTSTRAPPED=1        the one-time remote-state bootstrap is done
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

# --- Preflight: fail-closed on every missing prerequisite -------------------
# Note: presence checks only. Secret VALUES are never printed; do not add
# `set -x` around this section.
preflight() {
  [[ -n "${LINODE_TOKEN:-}" ]]            || fail "LINODE_TOKEN not set (operator-supplied; never on the box)"
  [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]    || fail "CLOUDFLARE_API_TOKEN not set"
  [[ "${ANSIBLE_VAULT_PASS_PROVIDED:-}" == "1" ]] \
      || fail "Ansible Vault passphrase not acknowledged (set ANSIBLE_VAULT_PASS_PROVIDED=1; supply via prompt or non-committed --vault-id)"
  [[ "${TF_STATE_BOOTSTRAPPED:-}" == "1" ]] \
      || fail "remote-state bootstrap not done (run terraform/bootstrap/ once; then export TF_STATE_BOOTSTRAPPED=1)"
}

main() {
  preflight
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY RUN — would run, in order:"
    log "  1. tofu -chdir='${INFRA_DIR}/terraform/prod' apply   (apply-only; no destroy)"
    log "  2. ansible-playbook '${INFRA_DIR}/ansible/site.yml'   (idempotent; --vault-id supplied)"
    log "No changes made."
    exit 0
  fi
  log "Prerequisites OK. (T25 wires the real apply/converge here.)"
  # TODO(T25): tofu -chdir=.../terraform/prod apply  (apply-only, never destroy)
  # TODO(T25): ansible-playbook .../ansible/site.yml (idempotent)
  fail "stand-up logic not yet wired (T1 scaffold); intentionally refusing to imply success"
}

main "$@"
