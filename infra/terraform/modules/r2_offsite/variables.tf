variable "account_id" {
  type        = string
  description = "Cloudflare account ID (R2 enabled)."
}

variable "bucket_name" {
  type        = string
  description = "R2 offsite backups bucket name (3-2-1 second copy, independent of Linode)."
}

variable "location" {
  type        = string
  default     = "ENAM"
  description = "R2 location hint (e.g. ENAM/WNAM/EEUR). Confirm valid values against the pinned provider in CI."
}

variable "object_lock_retention_days" {
  type        = number
  default     = 30
  description = "R2 object-lock retention for the offsite copy (its OWN immutability, independent of the Linode primary)."
}
