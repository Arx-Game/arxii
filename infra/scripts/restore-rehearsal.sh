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
# Required: REHEARSAL_CONFIRM=1, STAGE-scoped creds (TF_VAR_linode_token =
# stage token), RUN_ID, and the RESTORE_* read envs (see restore.sh).
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
STAGE_DIR="$(cd "${SCRIPT_DIR}/../terraform/ephemeral-stage" && pwd)"; readonly STAGE_DIR

log()  { printf '[rehearsal] %s\n' "$*"; }
fail() { printf '[rehearsal] REFUSING: %s\n' "$*" >&2; exit 1; }

[[ "${REHEARSAL_CONFIRM:-}" == "1" ]] || fail "set REHEARSAL_CONFIRM=1 (spins up + destroys an ephemeral stage box)"
: "${RUN_ID:?set RUN_ID (unique per-run suffix)}"
[[ "$(basename "${STAGE_DIR}")" == "ephemeral-stage" ]] \
  || fail "guard: this only ever runs against the ephemeral-stage root"

teardown() {
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

for src in linode r2; do
  log "rehearsing restore from ${src} onto the stage DB…"
  # Restore.sh, pointed at the STAGE host's DB (operator supplies RESTORE_*
  # read creds + RESTORE_DB/USER for the stage instance over the stage SSH).
  RESTORE_TARGET_HOST="${stage_ip}" \
    bash "${SCRIPT_DIR}/restore.sh" --i-understand-this-overwrites --source "${src}"
  log "restore from ${src}: OK + verified"
done

log "REHEARSAL PASSED — both 3-2-1 copies restore. (stage will now be destroyed)"
