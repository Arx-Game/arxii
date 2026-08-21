output "zone_id" {
  value       = cloudflare_zone.this.id
  description = "Cloudflare zone ID."
}

output "web_fqdn" {
  value       = "${var.web_hostname}.${var.domain}"
  description = "Proxied web/websocket hostname."
}

output "telnet_fqdn" {
  value       = "${var.telnet_hostname}.${var.domain}"
  description = "DNS-only TLS-telnet hostname (origin-direct)."
}

output "archive_fqdn" {
  value       = "${var.archive_hostname}.${var.domain}"
  description = "Proxied Arx I static-archive hostname."
}
