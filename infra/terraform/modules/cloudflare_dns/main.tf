# Zone + records. Web hostnames are PROXIED (orange) for DDoS/WAF/rate-limit;
# the TLS-telnet record is DNS-ONLY (grey) so telnet reaches origin directly
# (Cloudflare free tier does not proxy arbitrary TCP). Resolves the Resend
# "could only email myself until the domain is verified" chicken-and-egg by
# authoring the verification + SPF/DKIM records as code.
#
# Provider-schema caveat (v4 idiom; CI is the authority — see versions.tf).

resource "cloudflare_zone" "this" {
  account_id = var.account_id
  zone       = var.domain

  lifecycle {
    prevent_destroy = true
  }
}

# --- Web (proxied / orange) -------------------------------------------------
resource "cloudflare_record" "web_a" {
  zone_id = cloudflare_zone.this.id
  name    = var.web_hostname
  type    = "A"
  content = var.origin_ipv4
  proxied = true
}

resource "cloudflare_record" "web_aaaa" {
  zone_id = cloudflare_zone.this.id
  name    = var.web_hostname
  type    = "AAAA"
  content = var.origin_ipv6
  proxied = true
}

# --- Arx I static archive (proxied / orange) --------------------------------
# Same origin, own hostname: Caddy serves the read-only Arx I archive as a
# separate basic-auth-gated vhost (roles/caddy). The record exists whether or
# not the vhost is enabled yet — an A record pointing at an origin with no
# matching site block is inert (Caddy answers nothing for that SNI).
resource "cloudflare_record" "archive_a" {
  zone_id = cloudflare_zone.this.id
  name    = var.archive_hostname
  type    = "A"
  content = var.origin_ipv4
  proxied = true
}

resource "cloudflare_record" "archive_aaaa" {
  zone_id = cloudflare_zone.this.id
  name    = var.archive_hostname
  type    = "AAAA"
  content = var.origin_ipv6
  proxied = true
}

# --- TLS-telnet (DNS-only / grey — bypasses Cloudflare) ---------------------
resource "cloudflare_record" "telnet_a" {
  zone_id = cloudflare_zone.this.id
  name    = var.telnet_hostname
  type    = "A"
  content = var.origin_ipv4
  proxied = false
}

# --- Email auth -------------------------------------------------------------
# SPF is NOT declared here. Resend fronts Amazon SES and puts both the SPF TXT
# and the bounce-feedback MX on a return-path subdomain (send.<domain>), not on
# the apex — and the include host is SES's, not Resend's own. An apex SPF
# hardcoded here would sit where nothing checks it while the record that
# verification actually requires went missing. Every Resend-authored row,
# SPF included, therefore flows through var.resend_records verbatim.

locals {
  # rua is optional: aggregate reports need a mailbox whose domain authorises
  # this one to report to it, which a plain third-party inbox does not. Omit
  # rather than publish an address whose reports get refused.
  dmarc_reporting = var.dmarc_rua == "" ? "" : " rua=${var.dmarc_rua}; fo=1;"
}

resource "cloudflare_record" "dmarc" {
  zone_id = cloudflare_zone.this.id
  name    = "_dmarc"
  type    = "TXT"
  # p starts none/quarantine (validated in variables.tf) — tighten later.
  content = "v=DMARC1; p=${var.dmarc_policy};${local.dmarc_reporting}"
}

# Resend domain-verification, DKIM and SPF (DKIM here is the PUBLIC record
# only; the private key is Resend-managed) — exactly as Resend's dashboard
# provides them for this sending domain. priority is null except on the MX.
resource "cloudflare_record" "resend" {
  for_each = { for r in var.resend_records : "${r.type}:${r.name}" => r }

  zone_id  = cloudflare_zone.this.id
  name     = each.value.name
  type     = each.value.type
  content  = each.value.value
  priority = each.value.priority
}
