variable "region" {
  type        = string
  description = "Linode region (e.g. us-east)."
}

variable "instance_type" {
  type        = string
  description = "Linode plan (e.g. g6-standard-1). Smaller than prod is fine — stage is short-lived."
}

variable "image" {
  type        = string
  default     = "linode/ubuntu24.04"
  description = "Base image. Confirm the exact image slug against the pinned provider in CI."
}

variable "label" {
  type        = string
  description = "Instance label."
}

variable "authorized_keys" {
  type        = list(string)
  description = "SSH public keys for access. No hardening role ever runs against most stage boxes (they're destroyed within the hour), so these keys are the only access control for the box's whole lifetime."
}

variable "data_volume_size_gb" {
  type        = number
  default     = 20
  description = "Size of the attached data volume — smaller than prod's default; stage doesn't keep data."
}

variable "tags" {
  type        = list(string)
  default     = ["arxii", "ephemeral-stage"]
  description = "Linode tags."
}
