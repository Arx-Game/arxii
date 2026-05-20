variable "region" {
  type        = string
  description = "Linode region (e.g. us-east). ForceNew — changing it would replace the instance; with prevent_destroy that is a hard fail (fail-closed by design)."
}

variable "instance_type" {
  type        = string
  description = "Linode plan (e.g. g6-standard-2). ForceNew on some providers/changes — treat as fail-closed."
}

variable "image" {
  type        = string
  default     = "linode/ubuntu24.04"
  description = "Base image. ForceNew. Confirm the exact image slug against the pinned provider in CI."
}

variable "label" {
  type        = string
  description = "Instance label."
}

variable "authorized_keys" {
  type        = list(string)
  description = "SSH public keys for initial access. Root password auth is not used; ssh_hardening (Ansible) disables root login + password auth after first converge. Honest note: these keys are the bootstrap path in before hardening applies."
}

variable "data_volume_size_gb" {
  type        = number
  default     = 40
  description = "Size of the attached data volume (Postgres data / app / backup staging) — persists independently of the instance."
}

variable "tags" {
  type        = list(string)
  default     = ["arxii", "prod"]
  description = "Linode tags."
}
