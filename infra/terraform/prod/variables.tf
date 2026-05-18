# Secrets: no defaults, sensitive, supplied via TF_VAR_* env (operator/CI),
# never committed, never on the prod box.
variable "linode_token" {
  type      = string
  sensitive = true
}
variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}
variable "cloudflare_account_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east"
}
variable "instance_type" {
  type    = string
  default = "g6-standard-2"
}
variable "instance_label" {
  type    = string
  default = "arxii-prod"
}
variable "authorized_keys" {
  type        = list(string)
  description = "Initial SSH public keys (ssh_hardening later disables root/password)."
}

variable "domain" {
  type = string
}
variable "web_hostname" {
  type    = string
  default = "play"
}
variable "telnet_hostname" {
  type    = string
  default = "mud"
}
variable "tls_telnet_port" {
  type    = number
  default = 4003
}

variable "ssh_admin_cidrs" {
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
  description = "OPERATOR DECISION (README checklist): SSH source allowlist; defaults open."
}

variable "state_bucket_label" {
  type        = string
  description = "Primary backups bucket label (globally unique)."
}
variable "r2_bucket_name" {
  type = string
}

variable "dmarc_policy" {
  type    = string
  default = "none"
}
variable "dmarc_rua" {
  type = string
}
variable "resend_spf_include" {
  type    = string
  default = "_spf.resend.com"
}
variable "resend_records" {
  type = list(object({
    type  = string
    name  = string
    value = string
  }))
  default = []
}
