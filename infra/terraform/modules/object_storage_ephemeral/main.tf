# EPHEMERAL counterpart to ../object_storage (#2236 Phase 3 P1). Exists as a
# SEPARATE module, not a flag on the prod one, because `prevent_destroy` is a
# literal in a `lifecycle` block — Terraform/OpenTofu does not allow
# interpolating (variablizing) `lifecycle` arguments, so there is no way to
# thread a "rehearsal, please skip prevent_destroy" bool through the prod
# module. The prod module (../object_storage) is UNTOUCHED by this file — do
# NOT weaken it to make this work.
#
# Deliberately minimal versus the prod module: bucket + ONE writer key only
# (no read-only dev-reader key — nothing to hand to developers for a
# throwaway bucket that is destroyed within the hour). Versioning is OFF
# here (unlike prod — see the `versioning` argument below for why: it would
# block rehearse.sh's teardown from ever fully emptying the bucket), and
# there is intentionally NO Object Lock here either — the prod bucket
# doesn't have it yet either (#2236 "Known gap: Object Lock"), and a stage
# bucket that gets destroyed every run has no use for immutability.
resource "linode_object_storage_bucket" "stage" {
  region = var.region
  label  = var.label

  # OFF, unlike the prod module (#2236 review): this is a throwaway
  # rehearsal bucket, destroyed every run, that rehearse.sh's teardown
  # empties before `tofu destroy` (S3 DeleteBucket refuses a non-empty
  # bucket). Versioning would keep every prior version of an object around
  # even after a plain `s3 rm --recursive` (that only adds delete markers),
  # which would ALSO block emptying the bucket — turning the same
  # non-destroyable-bucket problem `prevent_destroy` caused into a
  # version-history-shaped one instead of actually fixing it.
  versioning = false

  # NO prevent_destroy — this bucket MUST be destroyable by rehearse.sh's
  # always-runs teardown trap. That is the entire reason this module exists
  # instead of reusing ../object_storage.
}

resource "linode_object_storage_key" "stage_writer" {
  label = "${var.label}-writer"
  bucket_access {
    bucket_name = linode_object_storage_bucket.stage.label
    region      = var.region
    permissions = "read_write"
  }
}
