# The remote-state bucket for the PROD root. Created exactly once.
#
# CRITICAL — design invariants (see infra plan §idempotency, §4.9):
#   * Versioning ON  — so a bad state write is recoverable.
#   * Object Lock OFF — the S3 backend REWRITES state in place; a locked
#                       state object would brick every future `tofu apply`.
#                       (Object Lock belongs ONLY on the *backup* buckets.)
#   * prevent_destroy ON — losing this bucket = losing the ability to manage
#                          prod state. It must never be destroyed by Tofu.
#
# This root deliberately creates ONLY the bucket. The scoped Object Storage
# access key the PROD backend uses is created MANUALLY by the operator (see
# README) so no long-lived secret ever lands in this local state file.
#
# Provider-schema caveat: the Linode provider's object-storage arguments
# (region vs cluster, the versioning block shape) have changed across major
# versions. The forms below are written for ~> 2.20; CI `tofu validate`
# against the pinned provider is the authority — adjust there if the schema
# differs, do NOT guess around a validate failure.

resource "linode_object_storage_bucket" "state" {
  region = var.region
  label  = var.state_bucket_label

  versioning = true
  # No `object_lock` / object-lock configuration here — intentionally absent.

  lifecycle {
    prevent_destroy = true
  }
}
