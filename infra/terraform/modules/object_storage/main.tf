# PRIMARY backups bucket (Linode). Versioning + Object Lock = the authoritative
# backstop against an on-box writer-key compromise (NOT key permissions —
# Linode S3 keys are only read-only/read-write; an RW key CAN delete; see
# §4.9 / focused review). prevent_destroy: this IS the plan's stateful set.
#
# §4.9 IMPLEMENTATION-VERIFY (do not guess): confirm against the pinned
# Linode provider whether Object Lock is settable on the bucket resource and
# its exact argument shape. Object Lock MUST be enabled at bucket creation;
# if the provider does not expose it, it is set via the S3 API/console at
# creation and Terraform manages the bucket + documents that step. CI
# `tofu validate` + the focused review are the authority — flag, don't fake.

resource "linode_object_storage_bucket" "backups" {
  region = var.region
  label  = var.label

  versioning = true

  # Object Lock intent (compliance/governance, retention window). Exact
  # argument name/block is the §4.9 verify item — confirm in CI against the
  # pinned provider; this is the design contract the implementation must meet.
  # object_lock { enabled = true, mode = "GOVERNANCE", retention_days = var.object_lock_retention_days }

  lifecycle {
    prevent_destroy = true
  }
}

# Backup WRITER key — used on-box by the backup job. NOT delete-incapable
# (Linode has no write-but-not-delete scope); Object Lock above is the
# backstop. Bucket-scoped only.
resource "linode_object_storage_key" "backup_writer" {
  label = "${var.label}-writer"
  bucket_access {
    bucket_name = linode_object_storage_bucket.backups.label
    region      = var.region
    permissions = "read_write"
  }
}

# READ-ONLY dev key (§4.9) — lets devs pull backups locally; cannot write or
# delete; cannot reach any other bucket.
resource "linode_object_storage_key" "dev_reader" {
  label = "${var.label}-dev-ro"
  bucket_access {
    bucket_name = linode_object_storage_bucket.backups.label
    region      = var.region
    permissions = "read_only"
  }
}
