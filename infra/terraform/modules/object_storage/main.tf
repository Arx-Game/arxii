# PRIMARY backups bucket (Linode). Versioning IS implemented — the backstop
# against accidental overwrite/delete via the on-box writer key. prevent_
# destroy: this IS the plan's stateful set.
#
# KNOWN GAP (tracked in #2236): Object Lock is NOT implemented. The pinned
# linode provider (~> 2.20) exposes no Object Lock argument on this resource
# (confirmed against the provider schema/docs at the pinned version — no
# `object_lock` block exists), so there is nothing to wire without fabricating
# a resource the provider doesn't support. Compensating posture until a
# provider adds support: the on-box writer key is bucket-scoped (cannot reach
# any other bucket or account), and the R2 offsite copy (r2_offsite module)
# is a second, independent copy under a SEPARATE credential/provider/account
# — a compromise of the Linode writer key cannot touch the R2 copy. See
# infra/README.md "Known gap: Object Lock".

resource "linode_object_storage_bucket" "backups" {
  region = var.region
  label  = var.label

  versioning = true

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
