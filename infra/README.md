# Arx II Infrastructure — "the button"

This directory is the **turnkey production stand-up** for Arx II: OpenTofu (Linode + Cloudflare) +
Ansible, driven by one command. It is **built and statically validated with no cloud account**;
nothing here can run against real infrastructure until the prerequisites below are satisfied.

## What the button is

**Primary (one-click): a GitHub Actions workflow.** On github.com, open this repo →
Actions → "Stand up infra" → **Run workflow**. It pauses for a required-reviewer
approval on the gated `prod` environment, then runs — no local toolchain, no tokens
on your machine, no terminal. It is a thin wrapper that injects the stored
Environment secrets and invokes the exact same script below (one source of truth).

**Equivalent fallback (local):**
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

## After a successful stand-up — credential hygiene (do this every time)

- [ ] **Revoke the Linode and Cloudflare API tokens at the provider** (not just delete
      the GitHub secret — revoke them so any leaked copy is already dead). Generate fresh
      short-expiry, scoped tokens next time you run the button. Stand-ups are rare and
      high-stakes; this removes the "powerful standing token sitting in GitHub forever"
      risk.
- [ ] The **Ansible Vault passphrase stays** the single gated Environment secret
      (GitHub-encrypted, exposed only to the approved job, never logged). Do **not** pass
      it as a workflow input (dispatch inputs are unmasked). Rotate it only if GitHub is
      ever suspected compromised.
- Note: fully keyless (GitHub OIDC, no stored token) is not cleanly available for Linode,
  so short-lived + revoke-after is the realistic best posture, not OIDC.

## GitHub Environment secrets (gated `prod`)

NAMES ONLY below — never values (safe in this public repo). All live in the
gated `prod` GitHub Environment (required-reviewer approval before any run).
They are exposed ONLY to the approved job, never echoed, never `--extra-vars`.

**Pre-stored by the operator — provisioning (tofu step; operator/CI-only,
NEVER reach the box; revoke at the provider after each successful run):**
- `TF_LINODE_TOKEN` — Linode API token
- `TF_CLOUDFLARE_API_TOKEN` — Cloudflare API token
- `TF_STATE_S3_ACCESS_KEY`, `TF_STATE_S3_SECRET_KEY` — the Object Storage key
  for the remote-state bucket (created manually in bootstrap; scoped to that
  bucket only)

**Pre-stored by the operator — runtime app secrets (ansible step → exported
as `ARXII_*` on that step ONLY; rendered to the 0600 on-box EnvironmentFile;
long-lived, rotate on suspicion):**
- `ARXII_PG_PASSWORD`, `ARXII_DJANGO_SECRET_KEY`, `ARXII_CLOUDINARY_URL`,
  `ARXII_RESEND_API_KEY`, `ARXII_OFFBOX_ALERT_TOKEN`
- `ARXII_CADDY_CF_DNS_TOKEN` — Cloudflare **DNS-edit-scoped** token used by
  Caddy for ACME DNS-01 (distinct from the provisioning Cloudflare token;
  needed because Cloudflare proxies the web hostname so HTTP-01 won't work)
- `ARXII_R2_ACCESS_KEY_ID`, `ARXII_R2_SECRET_ACCESS_KEY` — the SEPARATE,
  out-of-band R2 credential (distinct from Linode, scoped to the offsite
  bucket; this is what makes the 3-2-1 independent)
- `ANSIBLE_SSH_PRIVATE_KEY` — key Ansible uses to reach the host

**NOT pre-stored — produced by the tofu step at run time and piped into the
ansible step's env in-memory (masked, never to disk/log):**
- `ARXII_BACKUP_WRITER_ACCESS_KEY`, `ARXII_BACKUP_WRITER_SECRET_KEY` — the
  Linode primary-backups writer key (the `object_storage` module emits these
  as sensitive `tofu output`s; the button wires output → ansible env)

**Non-secret config** (domain, bucket labels, `cloudflare_account_id`,
public `authorized_keys`, `dmarc_rua`, `resend_records`, `ssh_admin_cidrs`)
goes in repo/Environment **Variables**, not Secrets.

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
