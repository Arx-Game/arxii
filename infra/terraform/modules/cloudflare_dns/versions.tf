terraform {
  required_version = ">= 1.6"
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
      # NOTE: the Cloudflare provider had a major v4 -> v5 rewrite that
      # renamed/restructured `cloudflare_record` and zone resources. This
      # module is written in the v4 idiom. CI `tofu validate` against the
      # pinned provider is the authority — if v5 is pinned, the record
      # resource shape must be updated there (do not guess).
      version = "~> 4.40"
    }
  }
}
