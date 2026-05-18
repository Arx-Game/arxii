# Arx II Infrastructure — "the button"

This directory is the **turnkey production stand-up** for Arx II: OpenTofu (Linode + Cloudflare) +
Ansible, driven by one command. It is **built and statically validated with no cloud account**;
nothing here can run against real infrastructure until the prerequisites below are satisfied.

## What the button is

`scripts/standup.sh` = validate prerequisites → `tofu apply` (apply-only) → `ansible-playbook site.yml`.

- **Apply-only and safe to re-run.** It never runs `tofu destroy`, never restores data, never
  re-initialises an existing database. Pressing it twice is a no-op, not a reset.
- **Restore is deliberately separate.** Disaster recovery is `scripts/restore.sh`, a distinct,
  human-gated tool that refuses to run without an explicit `--i-understand-this-overwrites` flag.
  It is *not* reachable from the button.
- **Telnet:** TLS-only. A TLS-capable MUD client (Mudlet, TinTin++, etc.) is required; the bare
  `telnet` command-line binary is intentionally unsupported. Plaintext telnet is closed.

## Human prerequisites checklist (do these once, before pressing the button)

- [ ] LLC formed.
- [ ] **Accounts created, each with 2FA enabled:** Linode, Cloudflare (with R2 enabled),
      Resend (transactional email), GitHub.
- [ ] **Domain registrar:** 2FA enabled **and registrar lock on**.
- [ ] API tokens placed in their documented secret locations — **never committed to the repo**.
- [ ] **The Linode API token is used only operator/CI-side to run the button. It is NEVER placed
      on the production box.**
- [ ] **The single Ansible Vault passphrase** stored in a password manager (never in the repo).
      This is the only secret the operator types at button-time.
- [ ] **DECISION — SSH admin source CIDR allowlist:** defaults to `0.0.0.0/0` (open to the
      internet, behind key-only auth + fail2ban). Consciously decide whether to restrict it to a
      known admin CIDR. This is a real decision, not a default to ignore.
- [ ] Domain nameservers delegated to Cloudflare.
- [ ] Resend sending domain will be verified automatically via the DNS records this IaC creates
      (SPF/DKIM/DMARC + Resend verification) once nameservers are delegated.
- [ ] One-time Terraform remote-state bootstrap run (`terraform/bootstrap/`, see its README).

## Layout

- `terraform/bootstrap/` — one-time, idempotent: creates the remote-state bucket (no Object Lock).
- `terraform/modules/` — compute, linode_firewall, cloudflare_dns, object_storage, r2_offsite.
- `terraform/prod/` — production composition; remote backend; full `prevent_destroy` set.
- `terraform/ephemeral-stage/` — separate state + credential scope (blast-radius isolation).
- `ansible/` — `site.yml`, roles, and `group_vars/secrets.vault.yml` (ansible-vault encrypted).
- `scripts/standup.sh` — the button. `scripts/restore.sh` — separate gated disaster recovery.

## Status

Account-gated, built incrementally. The full task breakdown lives in the (gitignored) plan
`docs/superpowers/plans/2026-05-17-arxii-turnkey-infra-iac.md` — that plan is a disposable
artifact; **this `infra/` tree is the deliverable.**
