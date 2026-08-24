# ADR-0232: The Arx I archive is gated on Arx II accounts, not a shared password

**Status:** Accepted (2026-08-24, Tehom in-session). **Supersedes the isolation
and access-control properties of [ADR-0225](0225-arx1-archived-to-object-storage-static-site.md)**;
the rest of that ADR (what is archived, where, and the messenger boundary)
stands unchanged.

ADR-0225 served the static Arx I archive at `archive.<domain>` behind one shared
basic-auth credential, "no backend, no websocket, no Django." One password for
every reader has no per-person revocation and no record of who read what, and
the archive holds black journals, secrets, clues and GM notes - so a password
that spreads cannot be taken back without changing it for everyone. The archive
is therefore **gated on Arx II accounts**: Caddy asks Django's
`/api/arx1-archive/authorize/` via `forward_auth` and serves the file only on a
2xx, so Django is in the authorization path but never in the data path.
**Staff and any account holding a `GMProfile` are admitted outright** (GMs use
Arx I as source material, and a separate tick would be a flag to keep in sync
with GM approval for no benefit); everyone else needs
`PlayerData.arx1_archive_access`, **default `False`** - registering for an Arx II
account is not itself grounds to read the archive.

It is served as a **path on the web vhost** (`/arxmush-archive`, not `/archive`,
which is wanted for in-game use) rather than on its own subdomain. That is the
whole reason the cookie question never arises: the session cookie is host-only,
so a subdomain would have required widening `SESSION_COOKIE_DOMAIN` to
`.<domain>` and handing the Arx II session to every future subdomain. The old
`archive.<domain>` becomes a 301 onto the path. The cost paid knowingly: **the
archive is no longer independent of the app** - it is unreachable while Arx II
is down, which is exactly the property ADR-0225 chose. It is also why the
export's root-relative links must be re-pointed under the prefix at sync time
(`arx1_prefix_rewrite.py`), since the exporter assumed a host root and only ever
ran on the now-retired Arx I box.

**Rejected:** *Cloudflare Access* (Zero Trust free tier covers 50 users, gives
per-person login and an access log, needs no Django change, and would have kept
ADR-0225's isolation intact) - rejected because the goal is to reuse Arx II
accounts, and a second identity system means readers keep a second credential.
*Subdomain plus a widened session cookie* - rejected because it hands the Arx II
session cookie to every future subdomain to solve a problem a path prefix solves
for free. *Default-open access for any registered account* - rejected on the
content: the archive is staff-intended material, not public history.
