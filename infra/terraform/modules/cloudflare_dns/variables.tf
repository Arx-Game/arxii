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
  default     = "mud"
  description = "Subdomain for TLS-telnet. DNS-only (NOT proxied) — telnet bypasses Cloudflare straight to origin."
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
  description = "Initial DMARC policy for a FRESH sending domain. Start 'none' (or 'quarantine') with rua reporting, then tighten. NEVER 'reject' initially (blackholes legit mail before traffic is observed)."
  validation {
    condition     = contains(["none", "quarantine"], var.dmarc_policy)
    error_message = "dmarc_policy must start at 'none' or 'quarantine' — not 'reject' on a fresh domain (tighten later, deliberately)."
  }
}

variable "dmarc_rua" {
  type        = string
  description = "DMARC aggregate-report mailbox, e.g. mailto:dmarc@arxii.example."
}

variable "resend_spf_include" {
  type        = string
  default     = "_spf.resend.com"
  description = "SPF include host for Resend. CONFIRM the exact value against Resend's domain-setup page for this sending domain (do not assume)."
}

variable "resend_records" {
  type = list(object({
    type  = string
    name  = string
    value = string
  }))
  default     = []
  description = "Resend domain-verification + DKIM records EXACTLY as Resend's dashboard shows them for this sending domain (DKIM here is the PUBLIC record only; the private key is Resend-managed). Operator pastes these; kept generic so the provider/account specifics aren't guessed."
}
