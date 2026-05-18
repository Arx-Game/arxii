variable "region" {
  type        = string
  description = "Linode Object Storage region for the PRIMARY backups bucket."
}

variable "label" {
  type        = string
  description = "Globally-unique backups bucket label."
}

variable "object_lock_retention_days" {
  type        = number
  default     = 30
  description = "Object Lock retention window for backups. Immutable for this many days even to a compromised writer key. This is the cost lever (versions accumulate); keep modest for DB dumps."
}
