# Arx I archival and Linode retirement

End state (ruled 2026-08-21): the Arx I Linode is deleted; its data survives as
checksummed, twice-replicated archives in object storage; a read-only static
copy of the Arx I website is served from the Arx II box at
`<web_fqdn>/arxmush-archive`, behind an Arx II account login; and making Arx I
*playable* again someday stays possible via a "resurrection kit" - without
keeping any zombie process running today.

The archive shipped behind one shared basic-auth password (ADR-0225). Since
#3320 / **ADR-0232** it is gated on Arx II accounts instead: staff and anyone
holding a `GMProfile` read it outright, everyone else needs a per-account grant
a staffer ticks in the Django admin. That bought per-person revocation, which a
shared password cannot have, at the price of the archive no longer being
independent of the app.

Cost after retirement: ~$0/month. The compressed archive rides the flat-rate
Linode backups bucket the Arx II box already pays for, plus Cloudflare R2
(10 GB-month free tier, $0.015/GB-month past it, zero egress). The static site
costs the Arx II box only disk and two routes on the web vhost. The $50/month Arx I
Linode goes away entirely.

Decision record: ADR-0225. Content policy (ruled 2026-08-21): **everything
written with the intent of being read by staff is fair game for the archive**
- black journals, secrets, clues, actions, events, spoilers - all were always
staff-viewable and explicitly known to be so. **The boundary is IC
communication players did not intend staff to read: messengers**
(player-to-player mail) carried an expectation of privacy and are never
surfaced. Verified: messengers have no web view in arxcode (model + telnet
handler + Django admin only, and the crawler skips /admin), so they exist
only inside the private sqlite backup - if anyone ever builds NEW archive
surfaces from that DB, messengers stay excluded. The GM/OOC rpevent logs are
likewise backup-only (player OOC information). The site is login-gated so
previously login-gated content is not crawlable or stranger-readable.

## Moving parts (all in this repo)

| Piece | Where | Runs on |
| --- | --- | --- |
| Freeze script | `infra/scripts/arx1/arx1-freeze.sh` | the Arx I box |
| Upload + verify script | `infra/scripts/arx1/arx1-upload.sh` | the Arx I box |
| Static-site exporter (DRAFT) | `infra/scripts/arx1/arx1_static_export.py` | the Arx I venv |
| Archive routes on the web vhost | `roles/caddy` (`caddy_archive_*` vars) | Arx II box, every converge |
| Authorization endpoint | `src/web/api/views/arx1_archive_views.py` | the Arx II app |
| Access grant flag | `PlayerData.arx1_archive_access` (Django admin) | per account, by staff |
| Link-prefix rewriter | `infra/scripts/arx1/arx1_prefix_rewrite.py` | Arx II box, each sync |
| Content sync (bucket -> web root) | `roles/arx1_archive` (`--tags arx1_archive`) | Arx II box, on demand |
| DNS record `archive.<domain>` (301 only) | `terraform/modules/cloudflare_dns` | tofu apply (the button) |

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
the list), events, crises, boards, help topics, and news. It also writes a
**synthetic `/lore/` appendix rendered straight from the DB** (ruled in
2026-08-21): all mysteries, revelations, and clues - never-discovered ones
and gm_notes included - because none of that had a crawlable surface in
Arx I (telnet investigation commands + Django admin only). Skippable with
`--skip-lore-appendix` for tuning runs. Still test a run against real data
before trusting it; the summary prints errors and skipped URLs to guide
tuning.

Two things to know before running:

- **Crawl as a staff account** (the default: first superuser). Ruled
  2026-08-21: black journals, secrets, clues, and GM notes all belong in the
  archive - everything staff-intended is in (see the content policy above).
  The staff journal list includes every black journal because a fresh
  account has read nothing, so its "unread" list is the full permitted set.
  Messengers cannot leak in regardless: they have no web view.
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

There is no archive credential to create. Press the button ("Stand up infra")
with **Also pull the static Arx I archive export** checked:

- the caddy role mounts `/arxmush-archive/*` on the web vhost behind a
  `forward_auth` subrequest to `/api/arx1-archive/authorize/`, plus an ungated
  `/arxmush-archive/static/*` for assets;
- the `arx1_archive` role pulls the export from the bucket, verifies its
  checksum, re-points its root-relative links under the prefix, and installs it
  at `/srv/arx1-archive`;
- the tofu step creates the `archive.<domain>` DNS records, which now serve a
  301 onto the path above so any link already handed out keeps working.

Then, as a staffer:

1. Browse `https://<web_fqdn>/arxmush-archive/` while logged out - it must
   bounce you to `/login`, and log in must land you back on the page you asked
   for.
2. Browse it logged in and spot-check an event page and a journal.
3. Grant a reader: Django admin -> Player data -> the account -> **Arx I
   Archive** -> tick `arx1_archive_access`. Untick to revoke; the next request
   is refused. Staff and GMs need no tick.

Re-running after a re-uploaded export: press the button with the same checkbox
again (the sync is a re-runnable oneshot, and the link rewrite is idempotent).
The routes themselves need no checkbox; they converge every deploy.

**Retiring the shared password.** `ARXII_ARX1_ARCHIVE_BASICAUTH_HASH` is dead.
Delete it from the gated `prod` Environment - nothing reads it, and leaving a
retired credential in an Environment is how it gets reused by mistake.

**Why a path and not the subdomain.** Reaching the archive with an Arx II
session means the session cookie has to arrive with the request. The cookie is
host-only (`SESSION_COOKIE_DOMAIN` unset), so `archive.<domain>` never saw it.
Widening the cookie to `.<domain>` would have fixed that by handing the Arx II
session to *every* future subdomain; mounting the archive as a path fixes it by
never raising the question. `/arxmush-archive` rather than `/archive` because
`/archive` is wanted for in-game use.

**Why the links get rewritten.** The export was crawled from a site served at a
host root, so its pages carry root-relative links (`href="/lore/"`,
`src="/static/..."`). Under a prefix those escape the archive - `/lore/` would
hit the Arx II SPA and `/static/` would serve Arx II's own collected static.
`arx1_prefix_rewrite.py` re-points them during the sync. It runs there rather
than in the exporter because the exporter only ever ran on the Arx I box, which
is retired: fixing it at export time would mean the tarball already in the
bucket could not be corrected without reviving that box.

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
