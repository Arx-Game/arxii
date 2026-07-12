#!/usr/bin/env bash
#
# smoke.sh <host> <fqdn> [--insecure]
#
# END-TO-END smoke test for a converged Arx II box: systemd units up, HTTPS
# serves the REAL built frontend (not the "Frontend not built" 500
# fallback — see src/web/views.py FrontendAppView), static assets, a
# websocket upgrade handshake, a TLS-telnet handshake, the admin login page.
# Named PASS/FAIL line per check; exits nonzero if ANY check FAILs. Never
# mutates anything — read-only checks throughout.
#
# Reusable in two contexts (#2236 Phase 3 P1):
#   - Rehearsal: rehearse.sh scp's this script onto the ephemeral stage box
#     and runs it there, ON the box, over SSH (host=127.0.0.1, fqdn=the fake
#     rehearsal hostname, --insecure — Caddy's local_certs internal CA has
#     no public trust chain to verify against).
#   - A future real-prod smoke test: an operator SSHes onto the prod box and
#     runs this locally too (host=127.0.0.1, fqdn=the real domain, no
#     --insecure — Caddy's real ACME cert IS publicly trusted).
# Running locally-ON-the-box (not probed from the outside network) is
# deliberate, not incidental: host_firewall's nftables only opens 80/443 to
# Cloudflare's published edge ranges — `iif "lo" accept` is the one
# unconditional rule that lets loopback traffic through regardless (see
# roles/host_firewall/templates/nftables.conf.j2). A probe from the outside
# network would be DROPPED by the very firewall this rehearsal exists to
# prove works — true in rehearsal (no real Cloudflare in front at all) and
# equally true against real prod (an arbitrary operator/CI IP is never one
# of Cloudflare's edge IPs either).
set -uo pipefail   # deliberately NOT -e: every check below must still run
                    # so the report is complete even after an early FAIL
set +x

usage() {
  cat <<'EOF'
Usage: smoke.sh <host> <fqdn> [--insecure]
  host        IP/hostname to connect to (curl --resolve / openssl -connect).
              Run this script ON the target box; host is normally 127.0.0.1.
  fqdn        The site's fqdn (SNI / Host header / --resolve name).
  --insecure  Accept an untrusted TLS cert (rehearsal's Caddy local_certs
              internal CA). Omit against a real ACME-issued cert.
Env overrides:
  TLS_TELNET_PORT   default 4003 (must match dh_tls_telnet_port / tofu's
                     tls_telnet_port output).
  CURL_TIMEOUT_S    default 15.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; exit 0; fi
HOST="${1:?$(usage)}"
FQDN="${2:?$(usage)}"
INSECURE=0
[[ "${3:-}" == "--insecure" ]] && INSECURE=1

TLS_TELNET_PORT="${TLS_TELNET_PORT:-4003}"
CURL_TIMEOUT_S="${CURL_TIMEOUT_S:-15}"

fails=0
pass() { printf '[smoke]  PASS  %s\n' "$1"; }
bad()  { printf '[smoke]  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

curl_args=(--resolve "${FQDN}:443:${HOST}" --max-time "${CURL_TIMEOUT_S}" -sS)
[[ "${INSECURE}" -eq 1 ]] && curl_args+=(-k)

echo "== systemd units =="
# arxii-offsite.timer is deliberately NOT in this list: it only exists when
# offsite_enabled is true (see roles/offsite_replication/defaults/main.yml),
# which rehearse.sh sets false (the R2 credential is prod-adjacent — the
# ephemeral-stage root has none to give it). Checking a context-dependent
# unit inside this reusable, context-agnostic script would either false-FAIL
# every rehearsal or false-PASS a real prod box that never installed it;
# rehearse.sh's own orchestration separately confirms offsite_enabled took
# effect (see its own acceptance check).
for unit in arxii.service caddy.service postgresql.service; do
  if systemctl is-active --quiet "${unit}" 2>/dev/null; then
    pass "unit active: ${unit}"
  else
    bad "unit NOT active: ${unit}"
  fi
done

for timer in arxii-backup.timer arxii-telnet-cert.timer arxii-watchdog.timer arxii-heartbeat.timer; do
  if systemctl is-enabled --quiet "${timer}" 2>/dev/null; then
    pass "timer loaded+enabled: ${timer}"
  else
    bad "timer NOT loaded/enabled: ${timer}"
  fi
done

echo "== HTTPS: frontend =="
index_body="$(curl "${curl_args[@]}" -o - -w '\n%{http_code}' "https://${FQDN}/" 2>/tmp/smoke_curl_index.err || true)"
index_code="${index_body##*$'\n'}"
index_html="${index_body%$'\n'*}"
if [[ "${index_code}" == "200" ]]; then
  pass "GET / -> 200"
else
  bad "GET / -> ${index_code:-<no response>} ($(tr -d '\n' </tmp/smoke_curl_index.err 2>/dev/null))"
fi
# id="root" is the React mount point in frontend/index.html — present ONLY
# in the real built bundle, never in FrontendAppView's "Frontend not built"
# 500 fallback (see src/web/views.py). Checking for this string (not merely
# a 200) is the actual "did the real app load" assertion.
if grep -q 'id="root"' <<<"${index_html}"; then
  pass "GET / body contains the built frontend's root mount (id=\"root\")"
else
  bad "GET / body does NOT contain id=\"root\" (frontend not built, or wrong page served)"
fi

echo "== HTTPS: static assets =="
# admin/css/base.css always exists post-collectstatic (Django admin is
# always installed) regardless of app-specific static content — a stable,
# app-independent marker file.
static_code="$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' "https://${FQDN}/static/admin/css/base.css" 2>/dev/null || true)"
if [[ "${static_code}" == "200" ]]; then
  pass "GET /static/admin/css/base.css -> 200"
else
  bad "GET /static/admin/css/base.css -> ${static_code:-<no response>}"
fi

echo "== HTTPS: admin login page =="
admin_code="$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' "https://${FQDN}/admin/login/" 2>/dev/null || true)"
if [[ "${admin_code}" == "200" ]]; then
  pass "GET /admin/login/ -> 200"
else
  bad "GET /admin/login/ -> ${admin_code:-<no response>}"
fi

echo "== websocket upgrade (wss://.../ws/) =="
# Evennia's own WEBSOCKET_CLIENT_URL is "wss://<fqdn>/ws/" (see
# roles/django_hardening/templates/secret_settings.py.j2) — Caddy's @ws path
# matcher (/ws/*) routes it to the localhost-bound portal, which performs
# the actual Upgrade handshake; Caddy itself doesn't need special config for
# it. A raw curl Upgrade request against the https:// URL is the standard
# way to check a WS upgrade without a full WS client — 101 is success.
# Nonce per RFC 6455 (random 16 bytes, base64). Generated at runtime — a
# fixed literal here also false-positives the gitleaks generic-api-key rule.
ws_key="$(openssl rand -base64 16)"
ws_code="$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H "Sec-WebSocket-Key: ${ws_key}" \
  "https://${FQDN}/ws/" 2>/dev/null || true)"
if [[ "${ws_code}" == "101" ]]; then
  pass "GET /ws/ (Upgrade) -> 101"
else
  bad "GET /ws/ (Upgrade) -> ${ws_code:-<no response>} (expected 101)"
fi

echo "== TLS-telnet handshake =="
# openssl s_client completes a full TLS handshake and prints the peer cert;
# `-servername` sends SNI in case Caddy's local_certs ever keys the cert by
# SNI (Evennia's own SSL-telnet listener doesn't use SNI routing today, but
# passing it is harmless and future-proof). A successful handshake writes at
# least one CERTIFICATE PEM block to stdout. `timeout` (#2236 review): unlike
# every curl check above, openssl s_client has no built-in time bound of its
# own — a hung/black-holed connection would otherwise wedge this script
# forever instead of failing this one check.
telnet_cert="$(printf '' | timeout "${CURL_TIMEOUT_S}" openssl s_client -connect "${HOST}:${TLS_TELNET_PORT}" \
  -servername "${FQDN}" 2>/dev/null || true)"
if grep -q 'BEGIN CERTIFICATE' <<<"${telnet_cert}"; then
  pass "TLS handshake on telnet port ${TLS_TELNET_PORT} -> cert received"
else
  bad "TLS handshake on telnet port ${TLS_TELNET_PORT} -> no cert received"
fi

echo
if [[ "${fails}" -gt 0 ]]; then
  echo "SMOKE: ${fails} FAILED"
  exit 1
fi
echo "SMOKE: all checks PASS"
