# The 3-2-1 OFFSITE copy: Cloudflare R2 — a DIFFERENT provider, account, and
# credential than Linode, so a Linode-account/token compromise or region loss
# cannot reach or delete it. That provider/account/credential separation is
# the implemented backstop for this copy (symmetric argument to the Linode
# primary's bucket-scoped writer key — NOT R2 key permissions).
#
# CREDENTIAL (deliberate, by design): the R2 S3 access key used by the on-box
# replication job is created OUT-OF-BAND (Cloudflare dashboard / API token),
# SEPARATE from Linode, and never enters Terraform state — same pattern as the
# state-backend key. It is NOT modelled as a TF resource here (don't fabricate
# a resource the provider may not expose). README/runbook documents creating
# it scoped to this bucket only.
#
# KNOWN GAP (tracked in #2236): R2 Object Lock is NOT implemented. The
# `cloudflare_r2_bucket_lock` resource needs cloudflare provider >= 5.4; this
# repo pins ~> 4.40 (confirmed: no lock resource/argument exists on
# `cloudflare_r2_bucket` at the pinned major). Revisit when the provider pin
# is deliberately bumped past 5.4 — see infra/README.md "Known gap: Object
# Lock" for the compensating posture in the meantime.

resource "cloudflare_r2_bucket" "offsite" {
  account_id = var.account_id
  name       = var.bucket_name
  location   = var.location

  lifecycle {
    prevent_destroy = true
  }
}
