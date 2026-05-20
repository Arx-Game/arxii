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
- [ ] **SSH admin keypair generated and pasted into the gated `prod` Environment**
      (see "Generating the SSH admin key" below). Keep the *private* key in your
      password manager — it is your emergency break-glass into the host if Ansible
      ever can't reach it. (The operator does not type any password at button-time;
      the secrets below come from the gated GitHub Environment, gated on a
      required-reviewer approval before the job starts.)
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
- [ ] The **runtime app secrets stay** (`ARXII_PG_PASSWORD`, `ARXII_DJANGO_SECRET_KEY`,
      `ARXII_RESEND_API_KEY`, the R2 credential, the SSH admin private key, etc.).
      Unlike the provisioning tokens above, these are long-lived: the running game needs
      them every day. Rotate only on suspicion of compromise. Do **not** pass them as
      workflow inputs (dispatch inputs are unmasked — they belong in Environment Secrets,
      where they are GitHub-encrypted and exposed only to the approved job).
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
- `ARXII_DJANGO_SUPERUSER_PASSWORD` — password for the first-run Django/Evennia
  superuser; consumed once by `evennia createsuperuser --noinput`, then
  long-lived (it's still the correct password if you ever delete/recreate the
  superuser). Username + email are non-secret Variables (see below) so they
  default sensibly without you touching the Environment Variables page; just
  the password is a Secret.
- `ANSIBLE_SSH_PRIVATE_KEY` — private half of the SSH admin keypair Ansible uses
  to reach the host. See **"Generating the SSH admin key"** below for one-time
  setup steps (this is a chicken-and-egg: you generate the key, Terraform tells
  Linode to inject the matching public half into the new instance at first boot)

**NOT pre-stored — produced by the tofu step at run time and piped into the
ansible step's env in-memory (masked, never to disk/log):**
- `ARXII_BACKUP_WRITER_ACCESS_KEY`, `ARXII_BACKUP_WRITER_SECRET_KEY` — the
  Linode primary-backups writer key (the `object_storage` module emits these
  as sensitive `tofu output`s; the button wires output → ansible env)

**Non-secret config** (domain, bucket labels, `cloudflare_account_id`,
public `authorized_keys`, `dmarc_rua`, `resend_records`, `ssh_admin_cidrs`,
`ARXII_DJANGO_SUPERUSER_USERNAME`, `ARXII_DJANGO_SUPERUSER_EMAIL`) goes in
repo/Environment **Variables**, not Secrets. The superuser username/email
default to `arxii_admin` / `admin@example.invalid` if you leave the
Variables unset — fine for a private playtest box, override for prod.

## What the button actually does to game state (first run vs. re-run)

The deploy is idempotent: re-runs are safe and mostly no-ops. Per release,
after the box itself is provisioned, the app_deploy role runs (in order):

1. **Git checkout** the release ref into `/opt/arxii/releases/<ref>`.
2. **Atomic symlink** `/opt/arxii/current → /opt/arxii/releases/<ref>`.
3. **`uv sync --frozen --no-dev`** — rebuild the project venv from the
   locked `uv.lock` (no implicit resolution drift). Idempotent: a no-op
   if nothing changed.
4. **`evennia migrate --noinput`** — apply Django/Evennia migrations.
   Idempotent: a no-op once everything is applied.
5. **`evennia collectstatic --noinput`** — gather admin/Evennia static
   files for Caddy. Idempotent.
6. **Superuser check + create**. If any superuser already exists in the DB
   (the *common* case after the first run), the create step is **skipped
   entirely** — your existing superuser is untouched, password unchanged.
   Only on a truly first run (or after a manual delete) does it create
   one from the `DJANGO_SUPERUSER_*` env vars.
7. **systemd** brings the service up (`evennia start` under the gated
   service user, in the `arxii.slice` cgroup with the memory cap from
   `base_game_memory_max`). On subsequent deploys it `reloads` instead
   of restarting, so the Portal keeps connected players online across
   code/deps/migration changes.

What the button **does not** do (deliberately, by-design):
- It does not load any game-content fixtures. The plan is to load those
  via the Django admin site once the superuser exists; that's an
  application-layer concern, not the deploy's job.
- It does not run `tofu destroy`, drop the database, reset the
  superuser, or restore from backup. Disaster recovery is the separate,
  `--i-understand-this-overwrites`-gated `scripts/restore.sh`.

## Generating the SSH admin key (one-time)

The button creates a brand-new Linode instance and Ansible needs to SSH into it
to finish setting it up — but the instance does not exist yet, so there is no
host to copy a key onto in advance. The way around the chicken-and-egg: **you
generate the keypair yourself, give Terraform the *public* half, and Linode
injects it into the new instance at first boot** (via cloud-init), so by the
time Ansible tries to connect the matching public key is already in place.

Do this once, on your own machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/arxii_admin -N '' -C 'arxii-admin'
```

That produces two files:

- `~/.ssh/arxii_admin` — the **private** key (multi-line, starts with
  `-----BEGIN OPENSSH PRIVATE KEY-----`). Never share this.
- `~/.ssh/arxii_admin.pub` — the **public** key (single line, starts with
  `ssh-ed25519 AAAA…`). This one is safe to publish; that is its job.

`-N ''` makes the key passphrase-less. A CI runner can't unlock a
passphrase-protected key, so for an automation key this is the right tradeoff;
the *protection* of the key comes from where it is stored, not a passphrase
on the file. (Do not reuse a personal SSH key for this — generate one
dedicated to Arx II.)

Then in GitHub: **repo → Settings → Environments → `prod`**:

| Where it goes              | Name                       | What to paste                                                 |
| -------------------------- | -------------------------- | ------------------------------------------------------------- |
| **Secrets**                | `ANSIBLE_SSH_PRIVATE_KEY`  | the entire contents of `~/.ssh/arxii_admin`                   |
| **Variables** (not secret) | `ARXII_AUTHORIZED_KEYS`    | a JSON array of one line: `["ssh-ed25519 AAAA… arxii-admin"]` |

Two things that catch people out:

- **Public keys go in Variables, not Secrets.** Public keys are not secret by
  definition — that is the entire point of public-key crypto. Variables let
  you see and audit the value in the UI. The Terraform variable is
  `list(string)`, so the value MUST be a JSON array like `["…"]`, not a bare
  line. To add more keys later (your laptop key for break-glass, another
  admin's key), just extend the array:
  `["ssh-ed25519 AAA… key1", "ssh-ed25519 BBB… key2"]`.
- **Back up the private key to your password manager** (1Password, Bitwarden,
  etc.) before you close the terminal. If the GitHub Secret is ever lost or
  the runner can't reach the host for any reason, that file is your only
  emergency way back in short of re-provisioning the box from a fresh
  Terraform apply.

## Layout

- `terraform/bootstrap/` — one-time, idempotent: creates the remote-state bucket (no Object Lock).
- `terraform/modules/` — compute, linode_firewall, cloudflare_dns, object_storage, r2_offsite.
- `terraform/prod/` — production composition; remote backend; full `prevent_destroy` set.
- `terraform/ephemeral-stage/` — separate state + credential scope (blast-radius isolation).
- `ansible/` — `site.yml` and 16 roles. **No committed secret material**: the `secrets_vault`
  role reads `ARXII_*` env vars (set on the ansible step by `standup.yml` from the gated
  Environment) and renders a `0600` on-box `EnvironmentFile` in one `no_log` task.
  `group_vars/secrets.env.example` is the names-only contract.
- `scripts/standup.sh` — the button. `scripts/restore.sh` — separate gated disaster recovery.

## Status

Account-gated, built incrementally. The full task breakdown lives in the (gitignored) plan
`docs/superpowers/plans/2026-05-17-arxii-turnkey-infra-iac.md` — that plan is a disposable
artifact; **this `infra/` tree is the deliverable.**
