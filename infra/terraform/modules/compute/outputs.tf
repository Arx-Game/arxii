output "instance_id" {
  value       = linode_instance.host.id
  description = "Linode instance ID (for firewall attachment)."
}

output "ipv4" {
  value       = linode_instance.host.ip_address
  description = "Public IPv4 — for the Ansible inventory and the DNS-only TLS-telnet record."
}

output "ipv6" {
  # Linode returns this as a CIDR ("2600:3c03::.../128"), but every consumer
  # wants a bare address: Cloudflare rejects an AAAA record whose content
  # carries a prefix length ("AAAA record must be a valid IPv6 address"),
  # which failed the first real prod apply after the instance already
  # existed. Strip the prefix here, at the source, so no consumer has to
  # remember to.
  value       = split("/", linode_instance.host.ipv6)[0]
  description = "Public IPv6, bare (prefix length stripped — see comment)."
}

output "data_volume_id" {
  value       = linode_volume.data.id
  description = "Attached data volume ID."
}
