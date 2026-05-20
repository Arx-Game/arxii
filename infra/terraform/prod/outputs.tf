# Consumed by standup.sh → the Ansible inventory + the vault EnvironmentFile.
# Key passthroughs are sensitive (route to ansible-vault, never logged).

output "instance_ipv4" {
  value       = module.compute.ipv4
  description = "Prod host IPv4 — Ansible inventory."
}
output "web_fqdn" {
  value = module.dns.web_fqdn
}
output "telnet_fqdn" {
  value = module.dns.telnet_fqdn
}
output "backups_bucket" {
  value = module.object_storage.bucket
}
output "r2_offsite_bucket" {
  value = module.r2_offsite.bucket
}
output "r2_s3_endpoint" {
  value = module.r2_offsite.s3_endpoint
}

output "backup_writer_access_key" {
  value     = module.object_storage.writer_access_key
  sensitive = true
}
output "backup_writer_secret_key" {
  value     = module.object_storage.writer_secret_key
  sensitive = true
}
output "dev_reader_access_key" {
  value     = module.object_storage.dev_reader_access_key
  sensitive = true
}
output "dev_reader_secret_key" {
  value     = module.object_storage.dev_reader_secret_key
  sensitive = true
}
