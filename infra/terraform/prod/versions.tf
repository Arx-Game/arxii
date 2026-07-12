terraform {
  required_version = ">= 1.6"

  # Partial S3-compatible backend → the Linode Object Storage state bucket
  # created by terraform/bootstrap. Bucket/endpoint/key supplied at init via
  # `-backend-config=` from the bootstrap outputs (operator-side, never in
  # repo). CI validates with `-backend=false` (no creds needed).
  backend "s3" {
    # Provided via -backend-config: bucket, key, endpoint, region,
    # access_key, secret_key, skip_region_validation, skip_credentials_
    # validation, use_path_style. See terraform/bootstrap/README.md.
  }

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.20"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

provider "linode" {
  token = var.linode_token # TF_VAR_linode_token; operator/CI-only, never on box
  # Bucket versioning/ACL ops need S3 (not Linode API) creds; temp keys are
  # generated per-operation and never persisted to state or disk.
  obj_use_temp_keys = true
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token # operator/CI-only
}
