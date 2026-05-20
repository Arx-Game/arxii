# Default-deny inbound; explicit allowlist only. The host_firewall Ansible
# role mirrors this (defense-in-depth). The PLAINTEXT telnet port is
# deliberately ABSENT from every rule below — it is closed at the network
# edge here AND disabled in Evennia (TELNET_ENABLED=False) by django_hardening.
#
# Provider-schema caveat: `linode_firewall` inbound/outbound rule block shape
# (ports as string, ipv4/ipv6 lists, action/policy) has varied across provider
# majors. Written for ~> 2.20; CI `tofu validate` against the pinned provider
# is the authority — fix there, do not guess around a validate failure.

resource "linode_firewall" "this" {
  label = var.label
  tags  = var.tags

  inbound_policy  = "DROP" # default-deny
  outbound_policy = "ACCEPT"

  # SSH — operator-decided source allowlist (defaults open; see variables.tf).
  inbound {
    label    = "ssh"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "22"
    ipv4     = [for c in var.ssh_admin_cidrs : c if can(cidrhost(c, 0))]
    ipv6     = [for c in var.ssh_admin_cidrs : c if !can(cidrhost(c, 0))]
  }

  # HTTP/HTTPS — ONLY from Cloudflare ranges (origin not web-reachable direct).
  inbound {
    label    = "web-cloudflare-only"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "80,443"
    ipv4     = var.cloudflare_ipv4_cidrs
    ipv6     = var.cloudflare_ipv6_cidrs
  }

  # TLS-telnet — open to all, layer-protected. (No plaintext-telnet rule.)
  inbound {
    label    = "tls-telnet"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = tostring(var.tls_telnet_port)
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  linodes = [var.linode_id]

  # No prevent_destroy: a firewall is reconstructible config, not stateful
  # data — it is intentionally NOT in the plan's prevent_destroy set.
}
