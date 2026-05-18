variable "label" {
  type        = string
  description = "Firewall label."
}

variable "linode_id" {
  type        = number
  description = "Instance ID to attach the firewall to."
}

variable "ssh_admin_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0", "::/0"]
  description = <<-EOT
    !!! OPERATOR DECISION (see infra/README.md checklist) !!!
    SSH (22) inbound source allowlist. DEFAULTS OPEN TO THE ENTIRE INTERNET
    (key-only auth + fail2ban are the floor). Consciously decide whether to
    narrow this to a known admin CIDR. This default is intentional but is a
    real risk decision, not a value to ignore.
  EOT
}

variable "cloudflare_ipv4_cidrs" {
  type        = list(string)
  description = "Cloudflare published IPv4 ranges. Web ports 80/443 are allowed ONLY from these (origin not directly reachable for web). Populate from Cloudflare's published list (https://www.cloudflare.com/ips/) — keep current; consider a data source/automation in the prod root."
}

variable "cloudflare_ipv6_cidrs" {
  type        = list(string)
  description = "Cloudflare published IPv6 ranges (same purpose as the v4 list)."
}

variable "tls_telnet_port" {
  type        = number
  description = "Evennia TLS/SSL telnet port. Open to all (layer-protected: TLS + fail2ban + app throttle). The PLAINTEXT telnet port is intentionally NOT represented here."
}

variable "tags" {
  type    = list(string)
  default = ["arxii", "prod"]
}
