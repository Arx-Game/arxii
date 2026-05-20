# Non-secret. Feed these into the PROD root's S3-compatible backend config.
# The backend ACCESS KEY/SECRET are NOT outputs here — they are created
# manually by the operator (see README) so no credential enters this state.

output "state_bucket" {
  value       = linode_object_storage_bucket.state.label
  description = "Bucket name to use as the prod Terraform backend bucket."
}

output "state_region" {
  value       = var.region
  description = "Region of the state bucket."
}

output "state_s3_endpoint" {
  value       = "https://${var.region}.linodeobjects.com"
  description = "S3-compatible endpoint for the prod backend block. Confirm the exact host pattern for the chosen region in CI/docs."
}
