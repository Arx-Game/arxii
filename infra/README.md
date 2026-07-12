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
Local toolchain: `tofu`, `ansible-playbook` (+ collections), `ssh`, **`jq`** (parses the single
`tofu output -json` read into the generated inventory/group_vars — preinstalled on GitHub-hosted
`ubuntu-latest` runners, so the CI button needs no extra install step; a local fallback run may
need `apt install jq`/equivalent), and `python3` with PyYAML (validates the generated group_vars
file parses as YAML before handing it to Ansible — already a transitive dependency of
`ansible-core`, so nothing extra to install if `ansible-playbook` is already set up locally).

- **Apply-only and safe to re-run.** It never runs `tofu destroy`, never restores data, never
  re-initialises an existing database. Pressing it twice is a no-op, not a reset.
- **SSH identity.** The very first converge (brand-new host) connects as `root` — Linode injects
  the operator's key there via cloud-init before `arxadmin` exists. That first run's `base` role
  creates a dedicated `arxadmin` sudo user and installs the admin key(s) there; `ssh_hardening`
  then disables root login. Every later run connects as `arxadmin` instead — `standup.sh` probes
  both (non-destructively, `select_ssh_user()`) and picks whichever answers, so the operator never
  hand-edits the inventory user. The `arxii` service account stays a non-login (nologin) user.
- **Restore is deliberately separate.** Disaster recovery is `scripts/restore.sh`, a distinct,
  human-gated tool that refuses to run without an explicit `--i-understand-this-overwrites` flag.
  It is *not* reachable from the button. It terminates existing connections and drops/recreates the
  target database before restoring (a half-applied plain-SQL restore can otherwise pass a naive
  "has tables" check), then verifies both `django_migrations` row-count and a floor of public
  tables. When restoring into the box's own local Postgres (the default, `RESTORE_TARGET_HOST=
  127.0.0.1`), it stops `arxii.service` first and restarts it afterward — even on failure, via a
  trap.
- **Rehearsal proves restore works, without ever touching prod or your machine.**
  `scripts/restore-rehearsal.sh` spins up an ephemeral stage box (separate Terraform state and
  credentials), installs Postgres on it, then runs `restore.sh` *on that box over SSH* — restoring
  into the stage box's own loopback Postgres, never the operator's local machine (the original bug
  this rework fixed: `RESTORE_TARGET_HOST` defaulting to `127.0.0.1` used to mean "whoever invoked
  the script"). It rehearses both the Linode and R2 copies in one run, then always tears the stage
  down (trap, even on failure).
- **Telnet:** TLS-only. A TLS-capable MUD client (Mudlet, TinTin++, etc.) is required; the bare
  `telnet` command-line binary is intentionally unsupported. Plaintext telnet is closed.
- **Single entry point — state has no locking.** The S3-compatible backend (Linode Object
  Storage) does not support Terraform state locking. Never run the local `standup.sh` fallback
  while the CI button may be running (or vice versa) — a concurrent `tofu apply` against the
  same state can corrupt it. Treat the GitHub Actions button as the one true entry point; use
  the local fallback only when you know the button isn't running (its `concurrency` group
  serializes runs of itself, but cannot see a local run).

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
      the Cloudinary trio, `ARXII_RESEND_API_KEY`, the R2 credential, the SSH admin
      private key, etc.).
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
- `ARXII_PG_PASSWORD`, `ARXII_DJANGO_SECRET_KEY`,
  `ARXII_CLOUDINARY_CLOUD_NAME`, `ARXII_CLOUDINARY_API_KEY`,
  `ARXII_CLOUDINARY_API_SECRET` (three discrete secrets — settings.py's
  `cloudinary.config()` reads each individually via `env()`, so a single
  combined `CLOUDINARY_URL` would be silently ignored, not an error),
  `ARXII_RESEND_API_KEY`, `ARXII_OFFBOX_ALERT_TOKEN`
- `ARXII_PG_PASSWORD` also feeds a *derived*, non-secret-named env var:
  `secrets_vault` renders `DATABASE_URL=postgres://arxii:<urlencoded
  password>@127.0.0.1:5432/arxii` on-box (django-environ's `env.db()` reads
  `DATABASE_URL` directly — settings.py has no discrete-`PG*`-vars path).
  The password is passed through Ansible's `urlencode` filter so special
  characters (`@`, `:`, `/`, etc.) in a generated password survive URL
  parsing intact — if you ever hand-set `ARXII_PG_PASSWORD` yourself rather
  than letting a generator produce it, any of those characters is safe to
  use; the encoding step handles it. `POSTGRES_PASSWORD` (the discrete var)
  is *also* still rendered — the postgres role's own tasks, the backup
  script, and psql's `PGPASSWORD` all read that key directly, never
  `DATABASE_URL`.
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

**Pre-stored by the operator — OPTIONAL (#2236 Phase 5; missing/empty just
disables the feature, never refuses the converge — `secrets_vault`'s
`secrets_map_optional`, not `secrets_map`; not in `standup.sh`'s
`REQUIRED_ARXII`):**
- `ARXII_SENTRY_DSN` — error tracking. Sentry has a free tier; create a
  project at [sentry.io](https://sentry.io) and grab the project's DSN
  under Settings -> Client Keys (DSN). Leave unset to run without Sentry
  (settings.py only calls `sentry_sdk.init()` when this is non-empty).
  `SENTRY_ENVIRONMENT` (prod: `production`; rehearsal: `rehearsal`) and
  `SENTRY_RELEASE` (the deployed commit SHA, stamped by `app_deploy` after
  checkout) are derived on-box, not operator-supplied.

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

- `ARXII_SSH_ADMIN_CIDRS` — **required**, maps to `TF_VAR_ssh_admin_cidrs`. A
  JSON array of operator CIDRs, e.g. `["203.0.113.10/32"]`. `standup.sh`'s
  preflight refuses to run at all if this is unset/empty — the SSH admin
  allowlist is a conscious decision (see the checklist above), not a
  default to leave unmade.
- `ARXII_ACME_EMAIL` — optional; Caddy's ACME account email. Defaults to
  `admin@<domain>` if unset.

## What the button actually does to game state (first run vs. re-run)

Before touching the box, `standup.sh` reads `tofu output` and writes a gitignored
`ansible/inventory/group_vars/arxii_prod.yml` (0600) — firewall allow-lists, FQDNs,
bucket/endpoint config, the admin's public keys — so none of that needs hand-editing or
living in the repo; every ansible role's fail-closed asserts (host_firewall,
django_hardening, ...) exist because a role must never silently converge against an empty,
ungenerated config.

The deploy is idempotent: re-runs are safe and mostly no-ops. Per release,
after the box itself is provisioned, the app_deploy role runs (in order):

1. **Git checkout** the release ref into `/opt/arxii/releases/<ref>`.
2. **`uv sync --frozen --no-dev`** — rebuild the project venv from the
   locked `uv.lock` (no implicit resolution drift). Idempotent: a no-op
   if nothing changed.
3. **Frontend build, on-box.** Installs Node.js 20.x (NodeSource, signed apt
   keyring) and pnpm (corepack) if not already present, then
   `pnpm install --frozen-lockfile && pnpm build` for the release's frontend
   bundle. Node/pnpm installation only happens once; the frontend rebuild
   recurs every release. **The first deploy takes noticeably longer** than
   subsequent ones as a result.
4. **`evennia migrate --noinput`** — apply Django/Evennia migrations.
   Idempotent: a no-op once everything is applied.
5. **`evennia collectstatic --noinput`** — gather admin/Evennia static
   files for Caddy. Idempotent.
6. **Atomic symlink** `/opt/arxii/current → /opt/arxii/releases/<ref>` — done
   **last** among the release-prep steps, only after the venv, frontend
   build, migrations, and static collection all succeed against the new
   release directory. A failure at any earlier step leaves `current`
   pointing at the last-good release instead of a half-prepared one.
7. **Superuser check + create**. If any superuser already exists in the DB
   (the *common* case after the first run), the create step is **skipped
   entirely** — your existing superuser is untouched, password unchanged.
   Only on a truly first run (or after a manual delete) does it create
   one from the `DJANGO_SUPERUSER_*` env vars.
8. **systemd** brings the service up (`evennia start` under the gated
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

## Ongoing safety nets (after stand-up)

Installed once by the converge, then running unattended on the box:

- **Portal/Server watchdog** (`arxii-watchdog.timer`, every minute). Evennia runs Server +
  Portal as two separate processes; if the unit's supervised process (Server) stays up but
  the Portal alone dies, systemd sees the unit as "active" and does nothing while players
  can no longer connect. The watchdog checks both pidfiles, restarts the unit, and fires an
  off-box alert when either is dead but the unit claims active.
- **Backup-failure alerting.** `arxii-backup.service` and `arxii-offsite.service` both carry
  `OnFailure=` units that fire an immediate off-box alert on failure; the daily heartbeat
  independently re-flags any backup/offsite unit still in a failed state, in case the
  `OnFailure=` alert itself didn't land.
- **Telnet cert renewal** (`arxii-telnet-cert.timer`, daily). Caddy's ACME cert is the
  source of truth; Evennia's SSL-telnet paths are hardcoded and don't reload on `evennia
  reload`, so this timer syncs the cert in and reboots Evennia **only when the cert
  actually changed** (no needless player disconnects). Synced to `GAME_DIR/server/ssl.cert`
  and `ssl.key`, where `GAME_DIR` is `/opt/arxii/current/src` — the `src/` dir nested inside
  the `current` symlink, NOT `current` itself (the same distinction the release-flip step
  above draws for `app_gamedir`; `roles/tls_telnet_cert`'s `ttc_game_dir` and
  `roles/django_hardening`'s `dh_game_dir` both had this off-by-one until #2236 review).
  The heartbeat's cert-expiry and self-signed-issuer checks catch the case where this sync
  has silently stopped working.

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

## Dress rehearsal (run this before the first prod button press)

**#2236 Phase 3 P1.** Before the very first real "Stand up infra" run, run the
dress rehearsal: **Actions → "Dress rehearsal (stage)" → Run workflow.** It
pauses for a required-reviewer approval on the gated `stage` Environment
(separate from `prod`), then stands up a throwaway Linode, converges the
**FULL, real `site.yml`** on it (the same playbook `standup.sh` runs, no
role/task forking — only a rehearsal-only `group_vars` overlay), smoke-tests
the running game end-to-end, rehearses a real backup + restore against real
(stage-scoped) object storage, and **always** tears everything down —
whether it passed or failed. Equivalent local fallback:
`scripts/rehearse.sh` (same preconditions as the workflow: `REHEARSAL_CONFIRM=1`,
`RUN_ID`, the stage-scoped env below).

### What it proves

- The full `ansible/site.yml` role list actually converges, end to end, on a
  brand-new box — not just `ansible-lint`/`--syntax-check` (CI's static
  gate) or a human reading the roles.
- The running game actually serves the real built frontend (not the
  `FrontendAppView` "Frontend not built" fallback), static assets, a
  websocket upgrade, a TLS-telnet handshake, and the admin login page — see
  `scripts/smoke.sh`.
- The nightly backup path (`arxii-backup.service`) actually produces an
  object in real object storage, and `scripts/restore.sh` actually restores
  it back — the SAME script, invoked the SAME way (over SSH, onto the box's
  own loopback Postgres) `restore-rehearsal.sh` already used, but this time
  against a box that just went through a real converge, not a bare
  Postgres-only box.
- Idempotency, fail-closed asserts (`host_firewall`, `django_hardening`,
  `secrets_vault`), and the isolation doctrine below all hold under a real
  `tofu apply`/`ansible-playbook` run, not just a static grep
  (`acceptance.sh`).

### What it deliberately CANNOT prove (first-prod-run-only residual risks)

Rehearsal mode keeps the ephemeral-stage root's isolation absolute: **no
prod refs, no prod-adjacent credential, ever.** That means three real things
are structurally untested here and remain **residual risk on the actual
first prod run**:

- **Real ACME issuance (DNS-01).** Caddy runs with its own internal CA
  (`local_certs`) via `Caddyfile.rehearsal.j2` instead of the real
  `Caddyfile.j2`'s `acme_dns cloudflare` directive — there is no Cloudflare
  DNS-edit token to give it (the ephemeral-stage root holds none, by
  design). The `caddy-dns/cloudflare` plugin build step is skipped
  entirely in rehearsal for the same reason.
- **Real DNS.** The fqdn (`stage.rehearsal.invalid`, an RFC 2606 reserved
  TLD — guaranteed unroutable and unissuable for real) is resolved via a
  single `/etc/hosts` entry written directly on the stage box, not through
  Cloudflare or any real nameserver.
- **R2 offsite replication.** `offsite_replication` is skipped entirely
  (`offsite_enabled: false`) — the R2 credential pair is a real Cloudflare
  account/bucket, prod-adjacent, and the isolated ephemeral-stage root has
  no such credential to give it.

These three should be watched closely on the actual first `standup.sh` /
"Stand up infra" run — they are the only parts of the stack this rehearsal
does not exercise.

### Isolation doctrine

Same blast-radius isolation as `restore-rehearsal.sh` (§4.8): a **separate**
Terraform root (`terraform/ephemeral-stage`), **separate** state (its own
S3-compatible backend key), **separate** stage-scoped Linode token
(`STAGE_LINODE_TOKEN` — never the prod `LINODE_TOKEN`). `rehearse.sh`'s tofu
calls never touch `terraform/prod`; teardown runs via a `trap`, always,
even on failure. Runtime secrets (`ARXII_PG_PASSWORD`,
`ARXII_DJANGO_SECRET_KEY`, the first-run superuser password) are generated
**fresh, every run, via `openssl rand`** — never operator-supplied, never
reused between runs.

Two Terraform modules exist **only** for this isolation: `modules/
compute_ephemeral` and `modules/object_storage_ephemeral` mirror the prod
`modules/compute`/`modules/object_storage` but omit `lifecycle {
prevent_destroy = true }` — a literal that Terraform/OpenTofu cannot
parameterize, so there is no way to flag "skip prevent_destroy in
rehearsal" on the prod modules themselves. (Verified empirically while
building this: `prevent_destroy` blocks `tofu destroy` on ANY root/state
that calls the module, not just "prod usage" — a previous version of
`ephemeral-stage/main.tf` reused the prod `compute` module directly on the
mistaken belief that this didn't matter for a root meant to be destroyed;
left uncorrected, every rehearsal/restore-rehearsal teardown would have
failed to destroy the stage instance+volume, leaking a billed Linode every
run.) The prod modules are untouched.

### The gated `stage` Environment — minimal secret contract

Mirrors `prod`'s contract (see above), stage-scoped:

**Secrets:**
- `STAGE_LINODE_TOKEN` — a Linode API token scoped to a **separate** account
  or a token you are comfortable letting an automated job create/destroy
  instances+volumes+buckets with; never the prod token.
- `STAGE_TF_STATE_S3_ACCESS_KEY`, `STAGE_TF_STATE_S3_SECRET_KEY` — the
  Object Storage key for the stage state key/prefix (scoped so it cannot
  read/list the prod state key — see `docs/operations/observability-baseline.md`
  §4.3/§4.8).
- `ANSIBLE_SSH_PRIVATE_KEY` — reuse the SAME admin keypair prod uses (see
  "Generating the SSH admin key" above); store a copy in the `stage`
  Environment too (GitHub Environments don't inherit secrets from each
  other).

**Variables (non-secret):**
- `STAGE_TF_STATE_BUCKET`, `STAGE_TF_STATE_KEY`, `STAGE_TF_STATE_REGION`,
  `STAGE_TF_STATE_ENDPOINT` — the stage state backend config.
- `ARXII_AUTHORIZED_KEYS` — reuse the same var name/value `prod` uses (the
  public key is not secret by definition).
- `ARXII_DJANGO_SUPERUSER_USERNAME`, `ARXII_DJANGO_SUPERUSER_EMAIL` —
  optional; default to `arxii_admin` / `admin@rehearsal.invalid`.

### Cost note

One small Linode (`g6-standard-1`, smaller than prod's default) plus a
throwaway Object Storage bucket, for roughly the 30–60 minutes the workflow
runs (`timeout-minutes: 60`). Both are destroyed by the trap at the end of
every run, pass or fail.

### restore-rehearsal.sh vs. rehearse.sh

`restore-rehearsal.sh` still exists — it's the narrower, faster,
**backup/restore-ONLY** drill: a bare stage box, Postgres installed by hand,
`restore.sh` rehearsed from BOTH the linode and R2 copies. Use it when all
you need is "does restore still work" without paying for a full converge.
`rehearse.sh` (this section) folds the SAME `restore.sh`-over-SSH logic in
as its own final step, but only rehearses the stage bucket copy (there is no
R2 in rehearsal — see "What it deliberately cannot prove" above) — its value
is proving the restore path against a box that just went through a REAL
site.yml converge, not a bare Postgres install.

## Pull prod data down (dev/local)

`just pull-prod confirm=yes` fetches the LATEST prod DB dump and restores it
into your LOCAL dev Postgres (drop/recreate + `arx manage migrate`) — one
command instead of the previous manual multi-step (#2236 Phase 4). It runs
`infra/scripts/pull_prod_db.sh`, which:

- Uses the READ-ONLY `dev_reader` Object Storage key (§4.9 of
  `docs/operations/observability-baseline.md`) — structurally cannot `Put`/
  `Delete`, so this tool can never write to the bucket and never touches
  prod itself.
- Picks the latest `arxii-*.sql.gz` under the bucket's `db/` prefix by the
  timestamp embedded in the object name (not S3 list order — same technique
  `restore.sh` uses).
- OVERWRITES your local dev DB. Refuses without the explicit
  `--i-understand-this-overwrites-local` flag (mirrors `restore.sh`'s gate
  style); `just pull-prod` with no `confirm=yes` refuses and changes
  nothing.

**One-time setup** — after a successful stand-up, get the dev_reader
credentials and bucket config from Terraform outputs and add them to
`src/.env`:

```bash
cd infra/terraform/prod
tofu output -raw dev_reader_access_key    # -> ARXII_DEV_READER_ACCESS_KEY
tofu output -raw dev_reader_secret_key    # -> ARXII_DEV_READER_SECRET_KEY
tofu output -raw backups_bucket           # -> ARXII_BACKUPS_BUCKET
tofu output -raw backups_s3_endpoint      # -> ARXII_BACKUPS_S3_ENDPOINT
tofu output -raw region                   # -> ARXII_BACKUPS_REGION
```

`DATABASE_URL` (already required for local dev) is the restore target — only
the plain `postgres://user:pass@host:port/dbname` form is supported (no
query string, no surrounding quotes; same restriction the justfile's
`_testdb-url` recipe already imposes on the same variable).

## Media durability (Cloudinary → R2 mirror)

User portraits/crests (`world.roster`'s `PlayerMedia`) live ONLY in
Cloudinary — the nightly DB dump never covers binary media, so a
Cloudinary-account-level loss previously had **no backup at all**.

**Built (#2236 Phase 4):** `arxii-media-mirror.service` (+ weekly
`arxii-media-mirror.timer`), installed by `roles/offsite_replication`
alongside the existing DB offsite job. It pages through every Cloudinary
resource (images/video/raw, all of them — not just `PlayerMedia`) and
uploads any object not yet present in the SAME R2 offsite bucket under a
`media/` prefix, using the existing R2 credential/endpoint. **Incremental,
NEVER deletes** — a Cloudinary-side delete or overwrite never touches the
R2 copy; the mirror is a backup, not a live sync. Cloudinary stays the
primary/serving copy (the app never reads media from R2); R2 is
recovery-only, so:

- **RPO ≈ 7 days on media** (weekly cadence) vs. ~24h on the DB — accepted:
  media is comparatively low-churn (portraits/crests, not gameplay state),
  and this closes a "zero backup" gap, not a tight-RPO requirement.
- Skipped entirely in rehearsal (`offsite_enabled: false` — same gate as
  the DB offsite job; the R2 credential is prod-adjacent, see "Dress
  rehearsal" above).
- Watched by the off-box heartbeat (`roles/offbox_alerting`) alongside
  `arxii-backup.service`/`arxii-offsite.service`.

## Known gap: Object Lock

Both backup copies (the Linode primary bucket and the Cloudflare R2 offsite bucket) have
**versioning enabled but not Object Lock (immutability).** This is a known gap, not an oversight:

- The Linode provider (pinned `~> 2.20`) exposes no Object Lock argument on
  `linode_object_storage_bucket` at all — there is nothing to wire without fabricating a resource
  the provider doesn't support.
- Cloudflare's R2 lock resource (`cloudflare_r2_bucket_lock`) needs provider `>= 5.4`; this repo
  pins `~> 4.40`.

**Compensating posture in the meantime:** the on-box Linode writer key is bucket-scoped
(read/write only to the primary backups bucket, cannot reach any other bucket or account) and
the R2 offsite copy is a genuinely independent second copy — separate provider, separate
account, separate out-of-band credential — so a compromise of one copy's credential cannot
reach or delete the other. Neither backstop is immutability against a compromised credential
with delete rights on *its own* bucket, which is the residual risk Object Lock would close.
Tracked in #2236; revisit when either provider pin is deliberately bumped past the versions
above.

## Layout

- `terraform/bootstrap/` — one-time, idempotent: creates the remote-state bucket (no Object Lock).
- `terraform/modules/` — compute, linode_firewall, cloudflare_dns, object_storage, r2_offsite;
  plus `compute_ephemeral`/`object_storage_ephemeral` (#2236 Phase 3 P1) — ephemeral-only
  mirrors of `compute`/`object_storage` without `prevent_destroy` (see "Dress rehearsal" above).
- `terraform/prod/` — production composition; remote backend; full `prevent_destroy` set.
- `terraform/ephemeral-stage/` — separate state + credential scope (blast-radius isolation);
  now also provisions a throwaway backups bucket (`object_storage_ephemeral`) for the dress
  rehearsal's backup+restore step.
- `ansible/` — `site.yml` and 16 roles. **No committed secret material**: the `secrets_vault`
  role reads `ARXII_*` env vars (set on the ansible step by `standup.yml`/`rehearse.sh` from the
  gated Environment) and renders a `0600` on-box `EnvironmentFile` in one `no_log` task.
  `group_vars/secrets.env.example` is the names-only contract. `roles/caddy` carries TWO
  Caddyfile templates (`Caddyfile.j2` real DNS-01, `Caddyfile.rehearsal.j2` internal CA) —
  edit both together, see either template's header.
- `scripts/standup.sh` — the button. `scripts/restore.sh` — separate gated disaster recovery.
  `scripts/rehearse.sh` — the dress-rehearsal ladder (#2236 Phase 3 P1; see above).
  `scripts/restore-rehearsal.sh` — the narrower backup/restore-only drill. `scripts/smoke.sh` —
  end-to-end HTTP/WS/TLS-telnet checks, reusable against rehearsal or real prod.
  `scripts/lib.sh` — shared helpers (`wait_for_tcp`, `select_ssh_user`, tofu-output caching,
  inventory/YAML generation) used by `standup.sh` and `rehearse.sh`. `scripts/pull_prod_db.sh`
  (#2236 Phase 4; `just pull-prod`) — dev-side prod→local DB pull, deliberately NOT sourcing
  `lib.sh` (a small, cross-referenced duplicate of `restore.sh`'s verification query instead —
  see "Pull prod data down" above).
- `roles/offsite_replication` owns BOTH offsite jobs (#2236 Phase 4): the original DB dump
  mirror (`arxii-offsite.service/.timer`) and the new weekly Cloudinary→R2 media mirror
  (`arxii-media-mirror.service/.timer`, see "Media durability" above) — both gated by the same
  `offsite_enabled` role-level condition in `site.yml`, both using the same R2 credential/bucket.

## Status

Account-gated, built incrementally. The full task breakdown lives in the (gitignored) plan
`docs/superpowers/plans/2026-05-17-arxii-turnkey-infra-iac.md` — that plan is a disposable
artifact; **this `infra/` tree is the deliverable.**
