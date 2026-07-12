# Minimal: just a throwaway stage host + (as of #2236 Phase 3 P1) a throwaway
# stage object-storage bucket, for the full dress-rehearsal ladder
# (rehearse.sh) to exercise the backup/restore path against real object
# storage. No DNS, no prod refs: this root cannot enumerate or affect prod by
# construction (separate state + separate credential scope, §4.8). The
# scripted apply->test->destroy + the env=ephemeral-stage tag guard live in
# scripts/ (T25 / rehearse.sh).
#
# BOTH modules below are EPHEMERAL-SCOPED variants (compute_ephemeral,
# object_storage_ephemeral), not the prod modules (compute, object_storage).
# The prod modules hardcode `lifecycle { prevent_destroy = true }` on their
# stateful resources — a literal that Terraform/OpenTofu does NOT allow
# interpolating, so there is no flag to pass that disables it for stage use.
# A prior version of this file reused ../modules/compute directly on the
# belief that prevent_destroy "wouldn't matter" for a root meant to be
# destroyed; that was empirically wrong (verified with a throwaway
# null_resource: `tofu destroy` hard-errors on any prevent_destroy'd
# resource regardless of which root/state called it) and would have leaked a
# billed Linode instance+volume on every rehearsal run. See
# ../modules/compute_ephemeral's header comment for the full account. The
# prod modules are untouched — do NOT weaken them to make this work.

module "stage" {
  source              = "../modules/compute_ephemeral"
  region              = var.region
  instance_type       = var.instance_type
  label               = "arxii-stage-${var.run_id}"
  authorized_keys     = var.authorized_keys
  data_volume_size_gb = 20
  tags                = ["arxii", "ephemeral-stage", var.run_id]
}

# Stage backups bucket — lets rehearse.sh exercise the REAL backup +
# restore-rehearsal path (roles/backups, roles/offsite_replication's sibling
# concept) against real Linode Object Storage with stage-scoped creds,
# instead of merely asserting the systemd units exist. Destroyed with the
# rest of the stage on every run.
module "stage_bucket" {
  source = "../modules/object_storage_ephemeral"
  region = var.region
  label  = "arxii-stage-backups-${var.run_id}"
}

output "stage_ipv4" {
  value = module.stage.ipv4
}

output "stage_bucket" {
  value = module.stage_bucket.bucket
}

output "stage_bucket_region" {
  value = module.stage_bucket.region
}

output "stage_bucket_s3_endpoint" {
  value = module.stage_bucket.s3_endpoint
}

output "stage_bucket_writer_access_key" {
  value     = module.stage_bucket.writer_access_key
  sensitive = true
}

output "stage_bucket_writer_secret_key" {
  value     = module.stage_bucket.writer_secret_key
  sensitive = true
}
