#!/usr/bin/env bash
#
# dev_reader_env.sh - one-time operator convenience: read the five settings
# `just pull-prod` needs (the read-only dev_reader Object Storage key and the
# backups bucket's address) from the prod Terraform outputs and append them to
# the env file the devcontainer reads. Companion to pull_prod_db.sh; see
# infra/README.md "Pull prod data down".
#
# Why this exists: the README used to say "run `tofu output -raw ...` five
# times and paste". Terraform has only ever run in the CI standup, so on a
# developer machine that meant installing tofu, reconstructing standup.sh's
# backend init by hand, and pasting five values - two of them secrets - into
# the right file. This script does the whole thing without echoing a secret.
#
# Run it on the HOST, not inside the devcontainer: `tofu init` downloads the
# Linode and Cloudflare providers from registry.opentofu.org, which the
# container's egress firewall blocks. Needs `tofu` on PATH
# (`mise use -g opentofu`).
#
# Required: a credentials file OUTSIDE the repo (default
# $HOME/arxii-ops-key/tfstate.env, override with ARXII_TFSTATE_ENV) holding
# the same six values the standup workflow gets from the gated `prod`
# environment - the four backend settings are its Variables, the two keys its
# Secrets:
#   TF_STATE_BUCKET=...        TF_STATE_KEY=...
#   TF_STATE_REGION=...        TF_STATE_ENDPOINT=...
#   TF_STATE_S3_ACCESS_KEY=... TF_STATE_S3_SECRET_KEY=...
#
# Target file: .devcontainer/dev.env when it exists (the devcontainer
# bind-mounts it over src/.env, and sync-env.sh never regenerates an existing
# dev.env, so src/.env is the wrong place on a devcontainer machine);
# otherwise src/.env. Override with --env-file PATH. Existing values are left
# alone; only missing names are appended. The append is in place (same
# inode), so a running container sees the change without a restart.
#
# The init runs against a scratch COPY of infra/terraform/{prod,modules}, so
# the tracked .terraform.lock.hcl never picks up this machine's platform
# hashes. Read-only use of the state: init + output, never plan or apply.
set -euo pipefail
set +x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"; readonly ROOT
readonly TF_ROOT="${ROOT}/infra/terraform"
CREDS="${ARXII_TFSTATE_ENV:-${HOME}/arxii-ops-key/tfstate.env}"
ENV_FILE=""

log()  { printf '[dev-reader-env] %s\n' "$*"; }
fail() { printf '[dev-reader-env] REFUSING: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: dev_reader_env.sh [--env-file PATH]
  --env-file PATH   File to append the ARXII_DEV_READER_* / ARXII_BACKUPS_*
                    lines to. Default: .devcontainer/dev.env if it exists,
                    else src/.env.
Reads the six TF_STATE_* values from $ARXII_TFSTATE_ENV
(default $HOME/arxii-ops-key/tfstate.env). Never prints a secret.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown argument: $1" ;;
  esac
done

if [[ -z "${ENV_FILE}" ]]; then
  if [[ -f "${ROOT}/.devcontainer/dev.env" ]]; then
    ENV_FILE="${ROOT}/.devcontainer/dev.env"
  else
    ENV_FILE="${ROOT}/src/.env"
  fi
fi

[[ -f "${CREDS}" ]] || fail "missing ${CREDS} (six TF_STATE_* lines; see the header of this script)"
[[ -f "${ENV_FILE}" ]] || fail "missing ${ENV_FILE} (copy src/.env.example, or run .devcontainer/sync-env.sh)"
command -v tofu >/dev/null 2>&1 || fail "tofu not on PATH (mise use -g opentofu); run this on the host"
[[ -d "${TF_ROOT}/prod" && -d "${TF_ROOT}/modules" ]] || fail "expected ${TF_ROOT}/prod and ${TF_ROOT}/modules"

set -a
# shellcheck disable=SC1090
. "${CREDS}"
set +a
for name in TF_STATE_BUCKET TF_STATE_KEY TF_STATE_REGION TF_STATE_ENDPOINT \
            TF_STATE_S3_ACCESS_KEY TF_STATE_S3_SECRET_KEY; do
  [[ -n "${!name:-}" ]] || fail "${name} is empty in ${CREDS}"
done

work_root="$(mktemp -d)"
cleanup() { rm -rf "${work_root}"; }
trap cleanup EXIT

# main.tf sources local modules as ../modules/<name>; mirror that layout so a
# copy of prod/ resolves them, and so init writes its lock-file changes and
# .terraform/ into the scratch copy rather than the checkout.
log "copying terraform config to a scratch dir (the checkout's lock file stays untouched)"
cp -r "${TF_ROOT}/modules" "${work_root}/modules"
mkdir -p "${work_root}/prod"
cp "${TF_ROOT}/prod"/*.tf "${work_root}/prod/"
[[ -f "${TF_ROOT}/prod/.terraform.lock.hcl" ]] && cp "${TF_ROOT}/prod/.terraform.lock.hcl" "${work_root}/prod/"
work="${work_root}/prod"

# Same backend init as infra/scripts/standup.sh: creds via AWS_* env so the
# secret never appears in argv; the skip_* flags because Linode Object
# Storage is S3-compatible, not AWS.
log "tofu init against the remote state (read-only: init + output, never plan or apply)"
AWS_ACCESS_KEY_ID="${TF_STATE_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${TF_STATE_S3_SECRET_KEY}" \
tofu -chdir="${work}" init -input=false -no-color \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="key=${TF_STATE_KEY}" \
  -backend-config="region=${TF_STATE_REGION}" \
  -backend-config="endpoint=${TF_STATE_ENDPOINT}" \
  -backend-config="skip_credentials_validation=true" \
  -backend-config="skip_region_validation=true" \
  -backend-config="use_path_style=true" \
  -backend-config="skip_requesting_account_id=true" \
  -backend-config="skip_s3_checksum=true" \
  -backend-config="skip_metadata_api_check=true" \
  >"${work}/init.log" 2>&1 || { tail -20 "${work}/init.log" >&2; fail "tofu init failed (see above)"; }

# An env file whose last line has no newline (a trailing comment is the usual
# culprit) turns the first append into a continuation of that line - and a
# commented-out setting fails silently. Terminate the file first.
if [[ -s "${ENV_FILE}" ]] && [[ "$(tail -c1 "${ENV_FILE}")" != "" ]]; then
  printf '\n' >> "${ENV_FILE}"
fi

added=0
for pair in \
  dev_reader_access_key:ARXII_DEV_READER_ACCESS_KEY \
  dev_reader_secret_key:ARXII_DEV_READER_SECRET_KEY \
  backups_bucket:ARXII_BACKUPS_BUCKET \
  backups_s3_endpoint:ARXII_BACKUPS_S3_ENDPOINT \
  region:ARXII_BACKUPS_REGION; do
  output_name="${pair%%:*}"
  var_name="${pair##*:}"
  if grep -qE "^${var_name}=" "${ENV_FILE}"; then
    log "skip ${var_name} (already present)"
    continue
  fi
  value="$(AWS_ACCESS_KEY_ID="${TF_STATE_S3_ACCESS_KEY}" \
           AWS_SECRET_ACCESS_KEY="${TF_STATE_S3_SECRET_KEY}" \
           tofu -chdir="${work}" output -raw -no-color "${output_name}")"
  [[ -n "${value}" ]] || fail "tofu output ${output_name} came back empty"
  printf '%s=%s\n' "${var_name}" "${value}" >> "${ENV_FILE}"
  log "added ${var_name}"
  added=$((added + 1))
done

log "done: ${added} added to ${ENV_FILE}. Next, inside the devcontainer: just pull-prod yes"
