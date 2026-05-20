output "instance_id" {
  value       = linode_instance.host.id
  description = "Linode instance ID (for firewall attachment)."
}

output "ipv4" {
  value       = linode_instance.host.ip_address
  description = "Public IPv4 — for the Ansible inventory and the DNS-only TLS-telnet record."
}

output "ipv6" {
  value       = linode_instance.host.ipv6
  description = "Public IPv6."
}

output "data_volume_id" {
  value       = linode_volume.data.id
  description = "Attached data volume ID."
}
