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
