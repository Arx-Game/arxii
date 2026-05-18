# Zone + records. Web hostnames are PROXIED (orange) for DDoS/WAF/rate-limit;
# the TLS-telnet record is DNS-ONLY (grey) so telnet reaches origin directly
# (Cloudflare free tier does not proxy arbitrary TCP). Resolves the Resend
# "could only email myself until the domain is verified" chicken-and-egg by
# authoring the verification + SPF/DKIM/DMARC records as code.
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

# --- TLS-telnet (DNS-only / grey — bypasses Cloudflare) ---------------------
resource "cloudflare_record" "telnet_a" {
  zone_id = cloudflare_zone.this.id
  name    = var.telnet_hostname
  type    = "A"
  content = var.origin_ipv4
  proxied = false
}

# --- Email auth -------------------------------------------------------------
resource "cloudflare_record" "spf" {
  zone_id = cloudflare_zone.this.id
  name    = "@"
  type    = "TXT"
  content = "v=spf1 include:${var.resend_spf_include} ~all"
}

resource "cloudflare_record" "dmarc" {
  zone_id = cloudflare_zone.this.id
  name    = "_dmarc"
  type    = "TXT"
  # p starts none/quarantine (validated in variables.tf) — tighten later.
  content = "v=DMARC1; p=${var.dmarc_policy}; rua=${var.dmarc_rua}; fo=1"
}

# Resend domain-verification + DKIM (PUBLIC record only; key is Resend-managed)
# — exactly as Resend's dashboard provides them for this sending domain.
resource "cloudflare_record" "resend" {
  for_each = { for r in var.resend_records : "${r.type}:${r.name}" => r }

  zone_id = cloudflare_zone.this.id
  name    = each.value.name
  type    = each.value.type
  content = each.value.value
}
