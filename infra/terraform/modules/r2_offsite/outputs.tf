output "bucket" {
  value       = cloudflare_r2_bucket.offsite.name
  description = "R2 offsite backups bucket name."
}

output "s3_endpoint" {
  value       = "https://${var.account_id}.r2.cloudflarestorage.com"
  description = "R2 S3-compatible endpoint for the on-box replication job (uses the separate, out-of-band R2 credential)."
}
