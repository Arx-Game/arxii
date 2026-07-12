variable "region" {
  type        = string
  description = "Linode Object Storage region for the stage bucket."
}

variable "label" {
  type        = string
  description = "Globally-unique stage bucket label (include the run_id — see ephemeral-stage/main.tf)."
}
