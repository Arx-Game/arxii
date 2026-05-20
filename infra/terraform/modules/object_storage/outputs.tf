output "bucket" {
  value       = linode_object_storage_bucket.backups.label
  description = "Primary backups bucket name."
}

output "region" {
  value       = var.region
  description = "Primary backups bucket region."
}

# Keys are SECRET — emitted sensitive so the root can route them to the
# ansible-vault EnvironmentFile path (writer = on-box backup job; dev reader
# = handed to developers). Never logged; never committed.
output "writer_access_key" {
  value       = linode_object_storage_key.backup_writer.access_key
  sensitive   = true
  description = "On-box backup job key (bucket-scoped, read_write)."
}

output "writer_secret_key" {
  value       = linode_object_storage_key.backup_writer.secret_key
  sensitive   = true
  description = "On-box backup job secret."
}

output "dev_reader_access_key" {
  value       = linode_object_storage_key.dev_reader.access_key
  sensitive   = true
  description = "Read-only dev key (§4.9)."
}

output "dev_reader_secret_key" {
  value       = linode_object_storage_key.dev_reader.secret_key
  sensitive   = true
  description = "Read-only dev key secret."
}
