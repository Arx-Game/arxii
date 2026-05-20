terraform {
  required_version = ">= 1.6"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40" # v4 idiom; CI is the authority (see cloudflare_dns/versions.tf note)
    }
  }
}
