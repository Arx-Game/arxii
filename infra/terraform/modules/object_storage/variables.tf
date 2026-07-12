variable "region" {
  type        = string
  description = "Linode Object Storage region for the PRIMARY backups bucket."
}

variable "label" {
  type        = string
  description = "Globally-unique backups bucket label."
}
