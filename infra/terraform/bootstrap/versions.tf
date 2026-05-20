# Bootstrap has its OWN LOCAL state (chicken-and-egg: it creates the very
# bucket that holds prod's remote state, so it cannot store state there).
# Run once, ever. See README.md.
terraform {
  required_version = ">= 1.6"

  # Local backend on purpose. Keep the resulting terraform.tfstate safe
  # (it is the only record of the state bucket until you re-import).
  backend "local" {}

  required_providers {
    linode = {
      source = "linode/linode"
      # Provider schema for object-storage args (versioning, region vs
      # cluster) has changed across major versions. Pin and let CI
      # `tofu validate` confirm the exact argument shape.
      version = "~> 2.20"
    }
  }
}

provider "linode" {
  # Supplied via TF_VAR_linode_token (env), never committed, never on the box.
  token = var.linode_token
}
