variable "account_id" {
  type        = string
  description = "Cloudflare account ID (zone owner)."
}

variable "domain" {
  type        = string
  description = "Apex domain, e.g. arxii.example."
}

variable "web_hostname" {
  type        = string
  default     = "play"
  description = "Subdomain for the web/websocket client (proxied through Cloudflare)."
}

variable "telnet_hostname" {
  type        = string
  default     = "telnet"
  description = "Subdomain for TLS-telnet. DNS-only (NOT proxied) — telnet bypasses Cloudflare straight to origin."
}

variable "archive_hostname" {
  type        = string
  default     = "archive"
  description = "Subdomain for the read-only Arx I static archive (proxied through Cloudflare; basic-auth-gated at Caddy)."
}

variable "origin_ipv4" {
  type        = string
  description = "Instance public IPv4 (from the compute module)."
}

variable "origin_ipv6" {
  type        = string
  description = "Instance public IPv6."
}

variable "dmarc_policy" {
  type        = string
  default     = "none"
  description = "Initial DMARC policy for a FRESH sending domain. Start 'none' (or 'quarantine'), then tighten. NEVER 'reject' initially (blackholes legit mail before traffic is observed)."
  validation {
    condition     = contains(["none", "quarantine"], var.dmarc_policy)
    error_message = "dmarc_policy must start at 'none' or 'quarantine' — not 'reject' on a fresh domain (tighten later, deliberately)."
  }
}

variable "dmarc_rua" {
  type        = string
  default     = ""
  description = "DMARC aggregate-report mailbox, e.g. mailto:dmarc@arxii.example. Empty omits rua entirely. Cross-domain reporting requires the RECEIVING domain to publish a <this-domain>._report._dmarc authorisation record, so a plain third-party inbox (gmail.com and friends) does not work — use an address on this domain or a reporting service that publishes its own authorisation."
}

variable "resend_records" {
  type = list(object({
    type     = string
    name     = string
    value    = string
    priority = optional(number)
  }))
  default     = []
  description = "EVERY DNS row Resend's dashboard shows for this sending domain, verbatim — verification/DKIM TXT, the return-path SPF TXT, and the bounce-feedback MX (priority set only on the MX). DKIM here is the PUBLIC record only; the private key is Resend-managed. Operator pastes these from the dashboard's MANUAL SETUP view; do not use Cloudflare auto-configure, which writes records this module then collides with."
}
