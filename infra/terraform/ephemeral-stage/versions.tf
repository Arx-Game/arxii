# Ephemeral stage = blast-radius isolation (§4.8): a SEPARATE root with a
# SEPARATE state key and a SEPARATE credential scope. It contains NO prod
# state and NO prod-scoped credential, so `tofu destroy` here provably cannot
# touch prod. Stage IS meant to be torn down — NO prevent_destroy here.
terraform {
  required_version = ">= 1.6"

  # Separate state key (e.g. key = "ephemeral-stage/<run-id>") supplied via
  # -backend-config; MUST use a stage-scoped Object Storage credential that
  # cannot read/list the prod state key (key separation alone is necessary-
  # not-sufficient — see §4.8 spec).
  backend "s3" {}

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.20"
    }
  }
}

provider "linode" {
  token = var.linode_token
}
