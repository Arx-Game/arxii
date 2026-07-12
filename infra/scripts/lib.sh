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
