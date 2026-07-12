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
output "backups_s3_endpoint" {
  value = module.object_storage.s3_endpoint
}
# roles/backups/defaults/main.yml `backups_region` — the object_storage
# bucket/endpoint are already region-scoped (var.region), but the backup
# script's `aws s3 cp --region` flag needs the value directly, and standup.sh
# has no other way to read a TF_VAR_* value back out (see the echoed-inputs
# block below).
output "region" {
  value = var.region
}
output "r2_offsite_bucket" {
  value = module.r2_offsite.bucket
}
output "r2_s3_endpoint" {
  value = module.r2_offsite.s3_endpoint
}

# Echoed operator inputs — group_vars wiring needs these as `tofu output`s
# too (standup.sh has no other way to read a TF_VAR_* value back out).
output "ssh_admin_cidrs" {
  value = var.ssh_admin_cidrs
}
output "tls_telnet_port" {
  value = var.tls_telnet_port
}
output "authorized_keys" {
  value = var.authorized_keys # public keys — NOT sensitive
}

# Cloudflare's published IP ranges (data source already used by the firewall
# module wiring above) — host_firewall mirrors the same allowlist.
output "cloudflare_ipv4_cidrs" {
  value = data.cloudflare_ip_ranges.cf.ipv4_cidr_blocks
}
output "cloudflare_ipv6_cidrs" {
  value = data.cloudflare_ip_ranges.cf.ipv6_cidr_blocks
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
