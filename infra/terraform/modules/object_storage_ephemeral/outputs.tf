output "bucket" {
  value       = linode_object_storage_bucket.stage.label
  description = "Stage bucket name."
}

output "region" {
  value       = var.region
  description = "Stage bucket region."
}

output "s3_endpoint" {
  value       = "https://${linode_object_storage_bucket.stage.s3_endpoint}"
  description = "S3-compatible endpoint for the stage bucket."
}

output "writer_access_key" {
  value       = linode_object_storage_key.stage_writer.access_key
  sensitive   = true
  description = "Stage-box backup/restore-rehearsal key (bucket-scoped, read_write)."
}

output "writer_secret_key" {
  value       = linode_object_storage_key.stage_writer.secret_key
  sensitive   = true
  description = "Stage-box backup/restore-rehearsal key secret."
}
