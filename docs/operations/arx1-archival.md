# Arx I archival and Linode retirement

End state (ruled 2026-08-21): the Arx I Linode is deleted; its data survives as
checksummed, twice-replicated archives in object storage; a read-only static
copy of the Arx I website is served from the Arx II box behind basic auth at
`archive.<domain>`; and making Arx I *playable* again someday stays possible via
a "resurrection kit" - without keeping any zombie process running today.

Cost after retirement: ~$0/month. The compressed archive rides the flat-rate
Linode backups bucket the Arx II box already pays for, plus Cloudflare R2
(10 GB-month free tier, $0.015/GB-month past it, zero egress). The static site
costs the Arx II box only disk and an extra Caddy vhost. The $50/month Arx I
Linode goes away entirely.

Decision record: ADR-0225. Rulings baked in: spoilers/secrets/clues may all
appear in the archive (anyone with archive access may see anything), the site
is basic-auth gated (previously-private content should not be crawlable or
stranger-readable), and the GM/OOC rpevent logs are backup-only - they contain
player OOC information and are NEVER served, not even behind the auth gate.

## Moving parts (all in this repo)

| Piece | Where | Runs on |
| --- | --- | --- |
| Freeze script | `infra/scripts/arx1/arx1-freeze.sh` | the Arx I box |
| Upload + verify script | `infra/scripts/arx1/arx1-upload.sh` | the Arx I box |
| Static-site exporter (DRAFT) | `infra/scripts/arx1/arx1_static_export.py` | the Arx I venv |
| Archive vhost (basic auth, TLS) | `roles/caddy` (`caddy_archive_*` vars) | Arx II box, every converge |
| Content sync (bucket -> web root) | `roles/arx1_archive` (`--tags arx1_archive`) | Arx II box, on demand |
| DNS record `archive.<domain>` | `terraform/modules/cloudflare_dns` | tofu apply (the button) |

## Step 1 - freeze the data (on the Arx I box)

Copy `infra/scripts/arx1/arx1-freeze.sh` to the Arx I host and run it there:

```sh
ARX1_GAME_DIR=/path/to/game \
ARX1_LOG_DIR=/path/to/rpevent/logs \
ARX1_VENV=/path/to/venv \
ARX1_GM_LOG_GLOB='*_gm*' \
bash arx1-freeze.sh
```

Check `ARX1_GM_LOG_GLOB` against the real filenames FIRST - a wrong glob
silently misfiles GM logs into the public tarball. The script warns loudly if
the glob matches nothing.

It produces, under `~/arx1-freeze`: a vacuumed + integrity-checked sqlite
snapshot, separate public and GM rpevent tarballs, a resurrection kit (game dir
including the venv, pip freeze, python/uname versions, crontab, webserver and
service configs), `SHA256SUMS`, and a `README.txt` manifest. Everything is
zstd level 19 with a long match window; decompression therefore needs
`zstd -d --long=27` (recorded in the manifest).

## Step 2 - upload to both buckets and byte-verify

On the same box (install rclone's static binary first -
https://rclone.org/install.sh - it runs on any distro vintage):

```sh
LINODE_BUCKET=... LINODE_ENDPOINT=... LINODE_ACCESS_KEY=... LINODE_SECRET_KEY=... \
R2_BUCKET=... R2_ENDPOINT=... R2_ACCESS_KEY=... R2_SECRET_KEY=... \
bash arx1-upload.sh
```

Bucket names and endpoints are the `backups_bucket`/`backups_s3_endpoint` and
`r2_offsite_bucket`/`r2_s3_endpoint` tofu outputs. For keys, either reuse the
existing pairs or mint fresh ones in each dashboard (Linode: bucket-scoped
key; Cloudflare: R2 API token scoped to the offsite bucket) and revoke after.
The script re-checks `SHA256SUMS` locally before anything leaves the box, then
`rclone check --download`s every object from BOTH remotes - actual bytes, not
etags. That re-download IS the "verified before the Linode dies" gate.

Everything lands under the `arx1/` prefix in both buckets, beside (never
touching) the Arx II `db/` and `media/` objects.

## Step 3 - build and upload the static site export

`arx1_static_export.py` is a DRAFT crawler: it walks the Arx I site through
Django's test client (no webserver involved - it renders views directly
against the sqlite DB) logged in as an account you choose, and writes a
plain-HTML tree. Its seeds and skip rules were written against arxcode's
actual urls.py, so coverage includes the big lore surfaces: rosters and
character sheets (every roster state, so departed characters too), **actions**
(`/character/sheet/<id>/actions/` lists + per-action pages, force-enqueued
for every discovered sheet rather than trusting the sheet template's links),
**journals** (`/comms/journals/list/`, paginated - entries render inline in
the list), events, crises, boards, help topics, and news. Still test a run
against real data before trusting it; the summary prints errors and skipped
URLs to guide tuning.

Two things to decide/know before running:

- **The crawl account decides the content.** A staff account sees secrets,
  clues, GM notes - AND every **black (private) journal**, because the
  journal list shows all journals the viewer is permitted. A fresh non-staff
  account gets white journals only but loses the sheet secrets/clues too.
  There is no URL-level way to split the difference; pick via `--username`.
- **Runtime: hours, plan for overnight.** Six years of data is plausibly
  50k-150k pages at ~100-500ms each, single-threaded. The exporter streams
  every page to disk immediately (flat memory) and supports `--resume`
  (re-parses already-saved files for links instead of re-rendering), so run
  it under `tmux`/`screen` and an interruption costs minutes, not the run.

It runs wherever the Arx I Django environment exists: on the old box before
retirement (easiest - SSH in, tmux, run), or later anywhere the resurrection
kit + db snapshot are restored - so this step does NOT block Step 5. It does
NOT run on the Arx II box, which never gets Arx I code; the Arx II box only
receives the finished tarball in Step 4.

```sh
cd <arx1 game dir>
<venv>/bin/python arx1_static_export.py --out ~/arx1-site --resume
# spot-check ~/arx1-site in a browser (python -m http.server), then pack:
tar -C ~/arx1-site -cf - . | zstd -19 --long=27 -T0 -o arx1-site-export.tar.zst
sha256sum arx1-site-export.tar.zst > arx1-site-export.tar.zst.sha256
```

Upload both files to the PRIMARY bucket as `arx1/arx1-site-export.tar.zst` and
`...tar.zst.sha256` (rclone as in Step 2; copy them to R2 too for safety). The
sync role expects `index.html` at the tarball ROOT and refuses a tree without
it.

## Step 4 - serve it from the Arx II box

1. Generate the shared credential's hash: `caddy hash-password` (any machine
   with caddy; the password itself goes wherever you share such things).
2. Set the gated `prod` Environment secret `ARXII_ARX1_ARCHIVE_BASICAUTH_HASH`
   to that hash. This secret is the vhost's enable switch: while it is unset,
   converges render no archive vhost at all (optional posture, like
   `ARXII_SENTRY_DSN` - a clean converge, not a refused one).
3. Press the button ("Stand up infra") with **Also pull the static Arx I
   archive export** checked. The tofu step creates the `archive.<domain>` DNS
   records; the caddy role renders the basic-auth vhost (login `archive`,
   password per the hash) and issues its cert; the `arx1_archive` role pulls
   the export from the bucket, verifies its checksum, and installs it at
   `/srv/arx1-archive`.
4. Browse `https://archive.<domain>/`, authenticate, spot-check an event page.

Re-running after a re-uploaded export: press the button with the same checkbox
again (the sync is a re-runnable oneshot). The vhost itself needs no checkbox;
it converges every deploy once the secret exists.

## Step 5 - retire the Arx I Linode

Gate deletion on ALL of:

- [ ] `arx1-upload.sh` finished green (both remotes byte-verified), and the
      objects are visible in both dashboards under `arx1/`.
- [ ] The GM tarball's file list was eyeballed (`zstd -dc --long=27 <gm>.tar.zst
      | tar -tf - | head`) and really is the GM set, and the public tarball
      really is the public set.
- [ ] Optionally: a third copy pulled to a personal machine (a full 3-2-1 for
      data that will never change again).

Then: power the Linode off, wait a short grace window if wanted (a powered-off
Linode still bills - keep it short or skip it; the verified copies are the real
safety), and delete the instance. Cancel any Arx I-only ancillary services
(its backups add-on, orphaned volumes/IPs).

## Making it playable again someday (deliberately deferred)

The resurrection kit preserves the option without keeping anything running:
game code + venv (actual bytes, not just a pip freeze that trusts PyPI
forever), interpreter version, service/webserver configs, crontab, plus the db
snapshot and logs beside it. Standing it back up means: restore kit + db onto
any box (the Arx II host has headroom - mind the port map), point its settings
at the restored sqlite, run it read-only or live. No part of the archive
pipeline needs to be undone first. If people actually start playing there
again, revisit backups - "frozen forever" stops being true at that point.
