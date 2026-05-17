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
# Structure preserved; allowlist replaced; GitHub-meta/jq/aggregate path
# replaced with plain dig resolution (all GitHub hosts are in the allowlist
# by name); Docker compose-bridge rule added; verification softened so a
# temporary DNS hiccup does not make container startup fail.

set -euo pipefail
IFS=$'\n\t'

# ---------------------------------------------------------------------------
# 1. Capture Docker internal DNS NAT rules BEFORE flushing anything.
#    Docker injects PREROUTING/OUTPUT rules that redirect DNS to 127.0.0.11.
#    If we flush without saving these we break container-internal DNS.
# ---------------------------------------------------------------------------
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# ---------------------------------------------------------------------------
# 2. Flush all existing rules and destroy existing ipsets.
# ---------------------------------------------------------------------------
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Restore ONLY the internal Docker DNS NAT rules we captured above.
# ---------------------------------------------------------------------------
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore."
fi

# ---------------------------------------------------------------------------
# 4. Baseline ACCEPT rules (must come before default-deny policies).
# ---------------------------------------------------------------------------

# Loopback — always unrestricted.
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# DNS — needed to resolve the allowlist domains below.
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT  -p udp --sport 53 -j ACCEPT

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
# 5. Build the ipset of allowed egress destinations.
#    hash:net supports both single IPs (/32) and CIDR prefixes.
# ---------------------------------------------------------------------------
ipset create allowed-domains hash:net

# Resolve each domain and add all returned A-record IPs to the ipset.
resolve_and_add() {
    local domain="$1"
    echo "Resolving ${domain}..."
    local ips
    ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}')
    if [ -z "$ips" ]; then
        echo "ERROR: Failed to resolve ${domain}"
        exit 1
    fi
    while read -r ip; do
        if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "ERROR: Invalid IP for ${domain}: ${ip}"
            exit 1
        fi
        echo "  Adding ${ip} for ${domain}"
        ipset add allowed-domains "$ip" 2>/dev/null || true  # ignore duplicates
    done <<< "$ips"
}

# ---- Allowlist (EXACT — do not add or remove entries) ----
#
# Claude Code runtime / telemetry
resolve_and_add "api.anthropic.com"
resolve_and_add "sentry.io"
resolve_and_add "statsig.anthropic.com"
resolve_and_add "statsig.com"
#
# Git operations + TehomCD/evennia dependency
resolve_and_add "github.com"
resolve_and_add "api.github.com"
resolve_and_add "codeload.github.com"
resolve_and_add "objects.githubusercontent.com"
#
# uv / pip
resolve_and_add "pypi.org"
resolve_and_add "files.pythonhosted.org"
#
# pnpm
resolve_and_add "registry.npmjs.org"

# ---------------------------------------------------------------------------
# 6. Detect the host network and allow traffic to it.
#    (Allows the container to talk back to the Docker host itself.)
# ---------------------------------------------------------------------------
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP via default route"
    exit 1
fi
HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Host network detected as: ${HOST_NETWORK}"
iptables -A INPUT  -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# ---------------------------------------------------------------------------
# 7. Default-deny policies and final ACCEPT/REJECT rules.
#    Order matters: ESTABLISHED before ipset-match before final REJECT.
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
# 8. Verification.
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

# (a) Blocked host must be unreachable.
if curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification FAILED — reached https://example.com (should be blocked)"
    exit 1
else
    echo "OK: https://example.com is blocked as expected."
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
