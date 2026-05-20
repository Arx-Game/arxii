variable "linode_token" {
  type        = string
  sensitive   = true
  description = "Linode API token. Supply via TF_VAR_linode_token (env). Never commit; never place on the prod box. Revoke at the provider after a successful run (see infra/README.md)."
}

variable "region" {
  type        = string
  default     = "us-east"
  description = "Linode Object Storage region for the remote-state bucket. Confirm the exact valid value against the pinned provider in CI."
}

variable "state_bucket_label" {
  type        = string
  description = "Globally-unique label for the Terraform remote-state bucket (e.g. arxii-tfstate-<something-unique>). No default on purpose — must be chosen and recorded in the prod backend config."

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_label))
    error_message = "state_bucket_label must be a DNS-safe bucket name (lowercase alphanumeric and hyphens, 3-63 chars)."
  }
}
