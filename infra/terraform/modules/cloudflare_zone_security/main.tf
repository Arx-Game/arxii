# Zone security configuration, codified from the live dashboard state on
# 2026-08-17 (#3205). Values below are a FAITHFUL IMPORT of what the zone held
# that day — first apply is a no-op write of identical values. Tightening any
# of them is a deliberate, reviewed diff on this file, never a dashboard edit:
# dashboard-side changes now surface as drift in `tofu plan`.
#
# Why this module exists: #3189 — a dashboard-side rule 403'd lazily-imported
# frontend chunks (`/static/dist/assets/*.js`) before they reached origin,
# breaking every route behind a React lazy import. Both the rule and its
# removal happened on the dashboard, so the repo recorded neither. Enumerating
# the zone on 2026-08-17 found NO surviving custom rule or exception: the fix
# was removal, and the prime suspect lever is Bot Fight Mode, which now sits
# OFF (it is known to 403 programmatic fetch() loads exactly like lazy chunk
# requests). That lever is pinned below.
#
# Also enumerated and deliberately NOT declared (empty on 2026-08-17, nothing
# to manage):
#   - custom WAF rulesets / managed-ruleset overrides (only Cloudflare's three
#     managed defaults exist: Normalization, DDoS L7, Free Managed Ruleset —
#     free-plan defaults, not zone-configurable resources)
#   - page rules, IP access rules, config rules
# If any of these are ever needed (e.g. a real path exception), add the
# resource HERE (cloudflare_ruleset for WAF phases), not on the dashboard.

resource "cloudflare_zone_settings_override" "this" {
  zone_id = var.zone_id

  settings {
    # The #3189-adjacent lever cluster: what stands between a browser request
    # and origin. `medium` challenges only known-bad IPs; `browser_check` is
    # passive header sanity, not a JS challenge.
    security_level = "medium"
    browser_check  = "on"
    challenge_ttl  = 1800

    # TLS/HTTPS posture, as found. KNOWN-WEAK, kept as-is by #3205's
    # faithful-import rule (behavior change = its own reviewed PR):
    #   - ssl "full" accepts any origin cert (not "strict")
    #   - always_use_https off leaves plain HTTP unredirected at the edge
    #   - min_tls_version 1.0 admits legacy clients
    ssl                      = "full"
    always_use_https         = "off"
    min_tls_version          = "1.0"
    tls_1_3                  = "on"
    automatic_https_rewrites = "on"
  }
}

# Bot Fight Mode: OFF, as found on 2026-08-17 — and this module's whole reason
# for being. If a future session flips it on from the dashboard, `tofu plan`
# reports drift here instead of the frontend silently losing its lazy routes
# again (#3189). Free plan exposes only `fight_mode`; the Super-BFM fields are
# paid-tier and unset.
#
# State bootstrap: this resource maps onto zone-level config that always
# exists, so the first apply simply writes the same value; an explicit
# `tofu import 'module.zone_security.cloudflare_bot_management.this' <zone-id>`
# beforehand is equivalent and optional.
resource "cloudflare_bot_management" "this" {
  zone_id    = var.zone_id
  fight_mode = false
}
