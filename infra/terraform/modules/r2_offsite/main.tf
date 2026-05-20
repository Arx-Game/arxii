# The 3-2-1 OFFSITE copy: Cloudflare R2 — a DIFFERENT provider, account, and
# credential than Linode, so a Linode-account/token compromise or region loss
# cannot reach or delete it. Its OWN object-lock immutability is the backstop
# (symmetric with the Linode primary; NOT the R2 key's permissions).
#
# CREDENTIAL (deliberate, by design): the R2 S3 access key used by the on-box
# replication job is created OUT-OF-BAND (Cloudflare dashboard / API token),
# SEPARATE from Linode, and never enters Terraform state — same pattern as the
# state-backend key. It is NOT modelled as a TF resource here (don't fabricate
# a resource the provider may not expose). README/runbook documents creating
# it scoped to this bucket only.
#
# §4.9 IMPLEMENTATION-VERIFY (don't guess): confirm R2 object-lock support +
# the exact resource/argument shape against the pinned provider in CI; if the
# provider can't set object lock on R2, it is enabled via the S3 API at bucket
# creation and Terraform manages the bucket + documents that step.

resource "cloudflare_r2_bucket" "offsite" {
  account_id = var.account_id
  name       = var.bucket_name
  location   = var.location

  lifecycle {
    prevent_destroy = true
  }
}
