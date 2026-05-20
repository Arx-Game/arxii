variable "linode_token" {
  type        = string
  sensitive   = true
  description = "STAGE-scoped Linode token (separate from prod). Operator/CI-only."
}
variable "region" {
  type    = string
  default = "us-east"
}
variable "instance_type" {
  type        = string
  default     = "g6-standard-1"
  description = "Smaller than prod is fine — stage is short-lived."
}
variable "run_id" {
  type        = string
  description = "Unique per-run suffix (CI run id / random) — isolates this stage box and its state key."
}
variable "authorized_keys" {
  type = list(string)
}
