# Websocket liveness: the edge closes an idle game session at 125.6s

## The measurement

An idle `wss://play.arx2.com/ws/game/` connection is closed **125.6 seconds**
after the handshake. Two samples on 2026-09-12, from separate Cloudflare rays,
ended at 125.613s and 125.595s — 18ms apart, which is a timer, not a network
event. The close is a **bare TCP FIN with no websocket close frame**, so a
browser reports it as close code 1006 (abnormal) rather than a clean 1000.

A third connection that sent a ping every 30s was still open when its 420s
window ended. The timeout is therefore an **idle timer that any frame resets**,
not a cap on connection age — which is why a keepalive fixes it.

Nothing in our own chain does this:

| Layer | Idle behavior |
| --- | --- |
| Cloudflare (proxied, orange) | closes at 125.6s — the measured one |
| Caddy | no proxy timeouts configured (`roles/caddy/templates/Caddyfile.j2`) |
| Evennia portal | `IDLE_TIMEOUT = -1`; autobahn's auto-ping defaults to off |

The origin's 443 admits only Cloudflare (`modules/linode_firewall`), so the
cut cannot be attributed by bypassing the edge from outside. It does not need
to be: every layer we configure is ruled out by its own configuration, and the
fix works behind any intermediary.

## Why it mattered

Every close sent the SPA down its abnormal-close path, which reconnects after
1s. The reconnect carries the stored autologin uid, so
`ServerSessionHandler.portal_connect` re-logs the account in with `force=True`.
125.6s + 1s backoff + handshake is the **127.0-second re-login cadence** #3745
saw in production — 517 of them in 19 hours, which (before #3743) also spent
the month's entire Sentry quota.

## The fix

`SecureWebSocketClient` sets autobahn's `autoPingInterval` (45s) and
`autoPingTimeout` (25s) as class attributes; see ADR-0291 for why the keepalive
is server-side and why 45s. Two pings fit inside 125.6s, so one lost ping does
not cost the connection.

## The keepalive is Portal-side, and a reload does not activate it

The auto-ping is an attribute on the Portal's protocol class, so it is the
**Portal** process that has to load it, and `evennia reload` never restarts the
Portal: it restarts the Server and leaves the Portal on whatever code it booted
with, which is the whole point of a reload (players stay connected through it).
The deploy role's ordinary path is `systemctl reload` = `evennia reload`. The fix
above went to production through that path in two consecutive stand-ups
(2026-09-13 and 2026-09-14), and a probe run against production on 2026-09-14
showed the same bare FIN at 125.5 s with no ping in the window: every gate was
green and the Portal had never loaded the class (#3863).

Two things now prevent that (#3863):

- **The deploy restarts instead of reloading when Portal-loaded code changed.**
  `roles/app_deploy` fingerprints `src/server/portal/**` and the Portal-read keys
  of `settings.py` (`app_portal_paths`, `app_portal_settings_regex`) in the release
  being deployed, and restarts both daemons when that fingerprint differs from the
  one stamped at the last provable reload or restart, or when none has been stamped
  yet. Players drop once on that path. The button's `full_restart` input forces it
  by hand.
- **The converge probes the public websocket after every reload or restart.** The
  role runs `tools/ws_idle_probe.py` from the controller against the public web
  hostname for `app_ws_probe_seconds` (130 s) and fails the run if the socket is
  closed by the peer or no `PING` arrives. Both stand-ups above would have failed
  here.

A change to anything else the Portal loads (a listener, a protocol class, a
settings key the regex does not match) needs the fingerprint extended in the same
PR; the `portal-code-deploy-reviewer` agent exists to ask that question of a diff.

## Re-measuring

`tools/ws_idle_probe.py` needs no credentials and no server access:

```bash
uv run python tools/ws_idle_probe.py play.arx2.com               # idle: expect survival now
uv run python tools/ws_idle_probe.py play.arx2.com --ping 30     # kept warm by pings
```

After a deploy of the keepalive, the idle run should log an inbound `PING`
roughly every 45 seconds and stay open past 125.6s. If an idle run ever ends at
a bare FIN again, the edge timeout has moved: record the new number, then
re-argue `WEBSOCKET_AUTOPING_INTERVAL` against it (ADR-0291) rather than
guessing a smaller value.

## Related

- ADR-0291 — websocket liveness is a server-side auto-ping
- #3745 — the 127-second reconnect; #3743 — the login exception it multiplied
- #3742 — connected-but-locationless sessions with no recovery path

## Portal correlation diagnostics (#4009)

`SecureWebSocketClient` assigns each transport a random `v1-<UUIDv4>` connection
id at transport open. An alpha diagnostic recorder may send the reserved,
post-open frame `portal_diagnostic_register` with a validated `v1-<UUIDv4>` run
id. Portal intercepts that frame before Evennia parsing and replies with
`portal_diagnostic_ack` containing only `connection_id`; invalid and duplicate
frames are consumed and never become game commands. Registration is limited to
three attempts per connection by default.

Portal records a bounded, redacted structured event window. Events include
transport/websocket open, auth milestone, auto-ping, pong, ping timeout, close
frame send/receive, local disconnect, protocol failure, and `connectionLost`.
They contain dual timestamps, protocol family, opaque ids, numeric close code,
and clean/transport-loss categories. Cookies, credentials, player content, raw
payloads, and close reasons are never recorded. Retention is controlled by
`PORTAL_DIAGNOSTICS_MAX_EVENTS` and `PORTAL_DIAGNOSTICS_MAX_AGE_SECONDS`; the
feature can be disabled with `PORTAL_DIAGNOSTICS_ENABLED`. Its default is on only
for the explicit `DEPLOYMENT_CHANNEL=alpha` or `rehearsal` settings and off for
production/development. The store has no public read endpoint: operators use the Portal process/log sink's existing
access controls, and diagnostic exports remain private incident evidence.

Browser JavaScript cannot observe WebSocket protocol ping/pong. Portal logs are
the source for those events; browser exports contain application-frame metadata
only. Caddy access logging and packet-level attribution are not implemented by
this seam, so a Caddy or peer-initiated TCP-close claim needs separate,
privately retained evidence.
