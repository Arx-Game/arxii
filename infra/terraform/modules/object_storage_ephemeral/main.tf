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
# throwaway bucket that is destroyed within the hour). Versioning stays on
# (mirrors prod's posture so the backup/restore rehearsal exercises the same
# shape of bucket), but there is intentionally NO Object Lock here either —
# the prod bucket doesn't have it yet either (#2236 "Known gap: Object
# Lock"), and a stage bucket that gets destroyed every run has no use for
# immutability.
resource "linode_object_storage_bucket" "stage" {
  region = var.region
  label  = var.label

  versioning = true

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
