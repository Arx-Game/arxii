#!/usr/bin/env bash
#
# lib.sh — small helpers shared by infra/scripts/*.sh. SOURCED, never
# executed directly (`. "${SCRIPT_DIR}/lib.sh"`). Assumes the sourcing
# script has already defined `log()` and `fail()` — kept script-local
# rather than moved here so each script's log/fail lines keep their own
# `[standup]` / `[rehearsal]` prefix instead of a shared generic one.

# wait_for_tcp <host> <port> <timeout_s> <interval_s>
#
# Bounded poll for a TCP port. Used for "wait until SSH answers" on a
# brand-new host (standup.sh's freshly-provisioned prod box,
# restore-rehearsal.sh's ephemeral stage box) — previously two
# byte-identical copies of this loop, one per script (#2236 review).
wait_for_tcp() {
  local host="$1" port="$2" timeout_s="$3" interval_s="$4" waited=0
  log "Waiting for TCP port ${port} on ${host} (up to ${timeout_s}s)…"
  until timeout 5 bash -c "true >/dev/tcp/${host}/${port}" 2>/dev/null; do
    waited=$((waited + interval_s))
    if [[ "${waited}" -ge "${timeout_s}" ]]; then
      fail "TCP port ${port} on ${host} did not open within ${timeout_s}s"
    fi
    sleep "${interval_s}"
  done
  log "Port ${port} open."
}

# select_ssh_user <ip>
#
# First run (brand-new host): Linode injects the admin keypair into ROOT
# (cloud-init has no arxadmin user yet — the base role creates it). Later
# runs: the base role has already created arxadmin+key and ssh_hardening has
# disabled root login, so root no longer answers. Probe non-destructively
# and pick whichever answers; site.yml's base role is idempotent either way.
#
# Shared by standup.sh (the real prod host) and rehearse.sh (#2236 Phase 3
# P1 — the ephemeral stage box goes through the exact same base-role
# bootstrap, since rehearsal converges the FULL, unmodified site.yml).
select_ssh_user() {
  local ip="$1"
  local -a key_args=()
  # Not fatal: CI always sets this (standup.yml/rehearse.yml export
  # ANSIBLE_PRIVATE_KEY_FILE before invoking the script); a local operator
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

# TF_OUTPUT_JSON: the FULL `tofu output -json` object, read ONCE by
# tf_read_outputs() below and cached here — jqr/jqc query it via jq instead
# of each output name triggering its own separate `tofu output <name>`
# process. Not `local`: callers in the sourcing script's top-level scope
# need it, so it must live at file (global) scope.
TF_OUTPUT_JSON=""

# tf_read_outputs <tf_dir>
#
# One `tofu output -json` read for the whole script — shared by standup.sh
# and rehearse.sh (#2236 Phase 3 P1; previously standup.sh-only, ~15
# individual `tofu output <name>` invocations before the single-read change
# — #2236 review).
tf_read_outputs() {
  TF_OUTPUT_JSON="$(tofu -chdir="$1" output -json)"
}

# jqr <name>: raw scalar string for output <name>, from the TF_OUTPUT_JSON
# cached by tf_read_outputs() above.
jqr() { jq -r ".${1}.value" <<<"${TF_OUTPUT_JSON}"; }
# jqc <name>: compact JSON for output <name> — already a valid YAML flow
# sequence/object, embeddable directly into a generated group_vars file.
jqc() { jq -c ".${1}.value" <<<"${TF_OUTPUT_JSON}"; }

# validate_generated_yaml <file>
#
# A malformed heredoc substitution (an unescaped quote/bracket inside a tofu
# output value, say) would otherwise surface only much later as an opaque
# ansible-playbook parse error against a file the operator never looks at
# directly. Fail loudly here instead, against the actual file. Shared by
# standup.sh (group_vars/arxii_prod.yml) and rehearse.sh (group_vars/
# arxii_rehearsal.yml).
validate_generated_yaml() {
  python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "$1" \
    || fail "generated $1 is not valid YAML — this is a bug in the caller's heredoc, not an operator error"
}

# gen_inventory <path> <ip> <ssh_user> [host_key]
#
# Writes the 0600 ansible inventory. The GROUP name must stay `arxii_prod`
# regardless of caller — site.yml hardcodes `hosts: arxii_prod` for its one
# play, and rehearse.sh (#2236 Phase 3 P1) deliberately converges that exact
# same, unmodified playbook against the ephemeral stage box; only the HOST
# key within the group varies (`prod` vs `stage`), which is cosmetic
# (inventory hostname label only — ansible_host below is what actually
# matters for connectivity).
gen_inventory() {
  local path="$1" ip="$2" ssh_user="$3" host_key="${4:-prod}"
  cat > "${path}" <<EOF
arxii_prod:
  hosts:
    ${host_key}:
      ansible_host: ${ip}
      ansible_user: ${ssh_user}
EOF
}
