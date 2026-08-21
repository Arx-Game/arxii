#!/usr/bin/env bash
# arx1-upload.sh — push the arx1-freeze.sh artifacts to BOTH buckets (the
# primary Linode backups bucket and the independent R2 offsite copy) under
# the arx1/ prefix, then verify every object by re-downloading and comparing
# bytes. Runs wherever the freeze artifacts are (the Arx I host, or a
# machine you rsync'd them to). Never deletes remote objects.
#
# Uses rclone: a single static binary that runs on any distro vintage
# (https://rclone.org/install.sh), configured entirely from env vars below —
# no rclone.conf on disk, so no credential is ever written to the old box.
#
# Credentials: create/scoped per docs/operations/arx1-archival.md — the
# Linode pair must reach only the backups bucket; the R2 pair only the
# offsite bucket. Both already exist for the Arx II box; for this one-time
# push either reuse them or mint a fresh pair and revoke after.
set -euo pipefail

ARX1_OUT="${ARX1_OUT:-${HOME}/arx1-freeze}"
: "${LINODE_BUCKET:?e.g. the tofu output backups_bucket}"
: "${LINODE_ENDPOINT:?e.g. https://us-east-1.linodeobjects.com (tofu output backups_s3_endpoint)}"
: "${LINODE_ACCESS_KEY:?bucket-scoped access key}"
: "${LINODE_SECRET_KEY:?bucket-scoped secret key}"
: "${R2_BUCKET:?e.g. the tofu output r2_offsite_bucket}"
: "${R2_ENDPOINT:?https://<account-id>.r2.cloudflarestorage.com (tofu output r2_s3_endpoint)}"
: "${R2_ACCESS_KEY:?R2 S3 access key}"
: "${R2_SECRET_KEY:?R2 S3 secret key}"

command -v rclone >/dev/null 2>&1 || {
  echo "rclone not found — install the static binary first: https://rclone.org/install.sh" >&2
  exit 1
}
[ -f "${ARX1_OUT}/SHA256SUMS" ] || {
  echo "no SHA256SUMS in ${ARX1_OUT} — run arx1-freeze.sh first" >&2
  exit 1
}

# Local self-check before anything leaves the box: never upload artifacts
# that do not match their own manifest.
(cd "${ARX1_OUT}" && sha256sum -c SHA256SUMS)

# Env-var remote config (rclone reads RCLONE_CONFIG_<NAME>_<KEY>).
export RCLONE_CONFIG_LINODE_TYPE=s3
export RCLONE_CONFIG_LINODE_PROVIDER=Other
export RCLONE_CONFIG_LINODE_ENDPOINT="${LINODE_ENDPOINT}"
export RCLONE_CONFIG_LINODE_ACCESS_KEY_ID="${LINODE_ACCESS_KEY}"
export RCLONE_CONFIG_LINODE_SECRET_ACCESS_KEY="${LINODE_SECRET_KEY}"
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ENDPOINT="${R2_ENDPOINT}"
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="${R2_ACCESS_KEY}"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="${R2_SECRET_KEY}"

for remote in "linode:${LINODE_BUCKET}/arx1" "r2:${R2_BUCKET}/arx1"; do
  echo "== upload -> ${remote%%:*} =="
  rclone copy --progress "${ARX1_OUT}" "${remote}"
  # --download: re-fetch every object and compare actual bytes, not just
  # S3 etags (multipart etags are not md5s, so etag comparison can lie).
  # This IS the "verify by re-download before the Linode dies" step.
  echo "== verify (byte-for-byte re-download) <- ${remote%%:*} =="
  rclone check --download "${ARX1_OUT}" "${remote}"
done

echo
echo "Both copies uploaded and byte-verified under arx1/."
echo "The old box is now safe to retire once the archive site export is"
echo "also up (see docs/operations/arx1-archival.md)."
