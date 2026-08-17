terraform {
  required_version = ">= 1.6"
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
      # v4 idiom, matching modules/cloudflare_dns. The v4 -> v5 rewrite
      # replaced `cloudflare_zone_settings_override` with per-setting
      # resources — if the pin ever moves to v5, this module must be
      # rewritten (CI `tofu validate` against the pinned provider is the
      # authority; do not guess).
      version = "~> 4.40"
    }
  }
}
