# ADR-0225: Arx I is archived to object storage + a static basic-auth site, not kept running

**Status:** Accepted (2026-08-21, Tehom in-session).

The Arx I Linode ($50/month) is retired. Its durable data - the sqlite database,
the rpevent logs (public and GM/OOC variants), and a "resurrection kit" (code,
venv, configs) - becomes checksummed zstd artifacts under the `arx1/` prefix in
BOTH existing backup buckets (Linode primary + R2 offsite), verified by
re-download before the box dies. History stays browsable as a STATIC export of
the Arx I website (crawled through Django's test client as staff, so
login-gated content renders) served by the Arx II box's Caddy at
`archive.<domain>` behind basic auth: previously-private content should not be
stranger-readable or crawlable, but anyone WITH archive access may see
anything - spoilers included. The GM/OOC logs are the one exception: backup
only, never served (player OOC information, not merely spoilers). The
basic-auth hash secret doubles as the vhost's enable switch (optional-secret
posture); content delivery is an on-demand `never`-tagged role, mirroring
content_repo. **Rejected:** keeping Arx I playable/running on the new box (a
zombie service competing for attention and RAM during the Arx II push - the
resurrection kit preserves the option at zero standing cost), and a
public/unauthenticated archive (crawlers + strangers reading formerly gated
content).
