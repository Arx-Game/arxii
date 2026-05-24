#!/bin/bash
# init-firewall.sh — egress firewall for the arxii devcontainer.
#
# Runs at every container start via postStartCommand (iptables rules are not
# persistent across restarts). Requires NET_ADMIN + NET_RAW capabilities
# (set in docker-compose.yml) and passwordless sudo for this exact path
# (set in the Dockerfile sudoers.d entry).
#
# Adapted from the upstream Anthropic reference:
#   https://raw.githubusercontent.com/anthropics/claude-code/main/.devcontainer/init-firewall.sh
# Structure preserved; allowlist replaced; IP-range gathering uses the same
# "fetch published ranges before lockdown" philosophy as the upstream reference,
# extended to cover all four logical destination groups.

set -euo pipefail
IFS=$'\n\t'

# ---------------------------------------------------------------------------
# 1. Flush the filter (and mangle) tables and destroy existing ipsets.
#    We do NOT touch the nat table: Docker injects PREROUTING/OUTPUT rules
#    into nat that redirect DNS to the embedded resolver (127.0.0.11).
#    Flushing nat breaks container-internal DNS and cannot be safely restored
#    via iptables-save/xargs.  Leaving nat untouched means Docker's DNS keeps
#    working across every container restart.
# ---------------------------------------------------------------------------
iptables -F
iptables -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Baseline ACCEPT rules (must come before default-deny policies).
# ---------------------------------------------------------------------------

# Loopback — always unrestricted.
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# DNS — needed to resolve the allowlist domains below.
# Both UDP (standard) and TCP (fallback for large responses, e.g. CDN TXT/A sets).
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT  -p udp --sport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A INPUT  -p tcp --sport 53 -m state --state ESTABLISHED -j ACCEPT

# SSH — allows git-over-SSH and inbound responses.
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT  -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT

# Docker compose bridge — allows the app container to reach the db service.
# Docker assigns bridge IPs from 172.16.0.0/12 at runtime (the exact address
# can shift between restarts), so we allow the entire RFC-1918 172.x range
# rather than a single resolved IP.  This covers Docker's default bridge
# pool (172.17–172.31.x.x) and any custom bridge networks in that range.
iptables -A OUTPUT -d 172.16.0.0/12 -j ACCEPT

# ---------------------------------------------------------------------------
# 3. Build the ipset of allowed egress destinations.
#    hash:net supports both single IPs (/32) and CIDR prefixes.
#
# IP-range data is gathered HERE — before the default-deny OUTPUT policy is
# applied — while the chain still defaults to ACCEPT.  If any required fetch
# or resolve fails (zero entries returned), we exit 1 immediately, before the
# policy flip.  Fail-closed during setup: the container retains its default
# ACCEPT policy and is never locked out of its own dependencies.
#
# Four logical destination groups, each resolved robustly for its delivery
# infrastructure:
#
#   a) Small/stable hosts (Anthropic API, Sentry, Statsig, PyPI index) —
#      resolved via dig A records; these hosts have small, stable IP sets.
#
#   b) GitHub — resolved via the official GitHub meta API, which publishes
#      the full set of CIDRs used by git, api, web, and packages endpoints.
#      Covers github.com, api.github.com, codeload.github.com, and
#      objects.githubusercontent.com (GitHub's CDN) robustly.
#
#   c) Fastly published ranges — covers objects.githubusercontent.com
#      (GitHub's Fastly CDN) and files.pythonhosted.org (PyPI file downloads,
#      also Fastly-backed).  Fastly serves from a large rotating pool;
#      a one-shot dig resolves only one of many edge nodes.
#
#   d) Cloudflare published ranges — covers registry.npmjs.org, which sits
#      behind Cloudflare and rotates IPs aggressively.
#
# Sources b–d use -exist so duplicate CIDRs across ranges don't error.
# ---------------------------------------------------------------------------
ipset create allowed-domains hash:net

# Strict validation: all four octets must be 0-255; optional prefix must be /0-/32.
is_valid_ipv4_cidr() {
    [[ "$1" =~ ^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])(/(3[0-2]|[12]?[0-9]))?$ ]]
}

# ---- a) Small/stable hosts via dig ----
resolve_and_add() {
    local domain="$1"
    echo "Resolving ${domain}..."
    local ips
    ips=$(dig +noall +answer +time=5 +tries=2 A "$domain" | awk '$4 == "A" {print $5}')
    if [ -z "$ips" ]; then
        echo "ERROR: Failed to resolve ${domain}"
        exit 1
    fi
    local count=0
    while read -r ip; do
        if ! is_valid_ipv4_cidr "$ip"; then
            echo "ERROR: Invalid IP for ${domain}: ${ip}"
            exit 1
        fi
        echo "  Adding ${ip} for ${domain}"
        ipset add allowed-domains "${ip}" -exist
        count=$((count + 1))
    done <<< "$ips"
    echo "  Resolved ${count} address(es) for ${domain}"
}

resolve_and_add "api.anthropic.com"
resolve_and_add "sentry.io"
# statsig.anthropic.com is NXDOMAIN; statsig.com covers the actual Statsig
# endpoint that Claude Code reaches.
resolve_and_add "statsig.com"
resolve_and_add "pypi.org"

# ---- b) GitHub meta API (git + api + web + packages CIDRs) ----
echo "Fetching GitHub IP ranges via meta API..."
GITHUB_META=$(curl -sf --connect-timeout 15 --max-time 30 https://api.github.com/meta)
if [ -z "$GITHUB_META" ]; then
    echo "ERROR: Failed to fetch https://api.github.com/meta"
    exit 1
fi
GITHUB_COUNT=0
while read -r cidr; do
    if is_valid_ipv4_cidr "$cidr"; then
        echo "  Adding GitHub CIDR: ${cidr}"
        ipset add allowed-domains "$cidr" -exist
        GITHUB_COUNT=$((GITHUB_COUNT + 1))
    fi
done < <(echo "$GITHUB_META" | jq -r '(.git[], .api[], .web[], .packages[]) | select(test("^[0-9]"))')
if [ "$GITHUB_COUNT" -lt 10 ]; then
    echo "ERROR: GitHub meta API returned only ${GITHUB_COUNT} IPv4 CIDRs (minimum 10); aborting" >&2
    exit 1
fi
echo "  Added ${GITHUB_COUNT} GitHub CIDRs."

# ---- c) Fastly published ranges (objects.githubusercontent.com + files.pythonhosted.org) ----
echo "Fetching Fastly IP ranges..."
FASTLY_LIST=$(curl -sf --connect-timeout 15 --max-time 30 https://api.fastly.com/public-ip-list)
if [ -z "$FASTLY_LIST" ]; then
    echo "ERROR: Failed to fetch https://api.fastly.com/public-ip-list"
    exit 1
fi
FASTLY_COUNT=0
while read -r cidr; do
    if is_valid_ipv4_cidr "$cidr"; then
        echo "  Adding Fastly CIDR: ${cidr}"
        ipset add allowed-domains "$cidr" -exist
        FASTLY_COUNT=$((FASTLY_COUNT + 1))
    fi
done < <(echo "$FASTLY_LIST" | jq -r '.addresses[]')
if [ "$FASTLY_COUNT" -lt 5 ]; then
    echo "ERROR: Fastly IP list returned only ${FASTLY_COUNT} IPv4 CIDRs (minimum 5); aborting" >&2
    exit 1
fi
echo "  Added ${FASTLY_COUNT} Fastly CIDRs."

# ---- d) Cloudflare published ranges (registry.npmjs.org) ----
echo "Fetching Cloudflare IPv4 ranges..."
CF_LIST=$(curl -sf --connect-timeout 15 --max-time 30 https://www.cloudflare.com/ips-v4)
if [ -z "$CF_LIST" ]; then
    echo "ERROR: Failed to fetch https://www.cloudflare.com/ips-v4"
    exit 1
fi
CF_COUNT=0
while read -r cidr; do
    cidr="${cidr//[$'\r']}"   # strip any Windows-style CR
    [ -z "$cidr" ] && continue
    if is_valid_ipv4_cidr "$cidr"; then
        echo "  Adding Cloudflare CIDR: ${cidr}"
        ipset add allowed-domains "$cidr" -exist
        CF_COUNT=$((CF_COUNT + 1))
    fi
done <<< "$CF_LIST"
if [ "$CF_COUNT" -lt 5 ]; then
    echo "ERROR: Cloudflare ips-v4 returned only ${CF_COUNT} IPv4 CIDRs (minimum 5); aborting" >&2
    exit 1
fi
echo "  Added ${CF_COUNT} Cloudflare CIDRs."

# ---------------------------------------------------------------------------
# 4. Default-deny policies and final ACCEPT/REJECT rules.
#
#    ACCEPT-rule ordering: ESTABLISHED/RELATED first, then ipset-match, then
#    final REJECT.  The ordering matters only relative to the REJECT at the
#    end of the OUTPUT chain — earlier ACCEPTs short-circuit it.
#
#    NOTE: flipping OUTPUT to DROP here intentionally drops any in-flight
#    connections that were open during the setup phase above.  That is the
#    expected behaviour for a security tool applied on container restart;
#    callers should reconnect after firewall initialization completes.
# ---------------------------------------------------------------------------
iptables -P INPUT   DROP
iptables -P FORWARD DROP
iptables -P OUTPUT  DROP

# Allow return traffic for already-approved connections.
iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow outbound traffic to the allowlist.
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Reject everything else with an immediate ICMP response (better than silent DROP).
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

echo "Firewall configuration complete."

# ---------------------------------------------------------------------------
# 5. Verification.
#
# We assert the key invariants:
#   (a) A host that is NOT on the allowlist cannot be reached.
#   (b) A host that IS on the allowlist can be reached.
#
# Verification failures due to *firewall* misconfiguration are fatal (exit 1).
# Failures due to external network unavailability (e.g. CI with no internet,
# transient DNS) only emit a warning — the firewall rules themselves are still
# enforced.
# ---------------------------------------------------------------------------
echo "Verifying firewall rules..."

# (a) Blocked host must be unreachable. Use www.google.com — Google's own
# IPs (142.250.0.0/15, 142.251.0.0/16) are not in any of our allowlist
# sources (Anthropic, Sentry, Statsig, PyPI, GitHub meta, Fastly,
# Cloudflare), so reachability here means a firewall miss. Avoid
# example.com / example.org as test targets: both now resolve to
# Cloudflare IPs (104.20.x.x, 172.66.x.x) that are legitimately in our
# allowlist because Cloudflare fronts the npm registry.
if curl --connect-timeout 5 https://www.google.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification FAILED — reached https://www.google.com (should be blocked)"
    exit 1
else
    echo "OK: https://www.google.com is blocked as expected."
fi

# (b) Allowed host should be reachable.  Treat external-network failure as a
#     warning rather than a hard error so the container still starts in
#     air-gapped CI environments where the firewall is correct but the
#     upstream host is simply unavailable.
if curl --connect-timeout 10 https://api.github.com/zen >/dev/null 2>&1; then
    echo "OK: https://api.github.com is reachable as expected."
else
    echo "WARNING: Could not reach https://api.github.com — firewall rules are in place"
    echo "         but external connectivity may be absent (air-gapped environment?)."
    echo "         This is not a firewall failure; continuing."
fi

echo "Firewall initialization complete."
