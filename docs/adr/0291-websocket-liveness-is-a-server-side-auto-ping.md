# Websocket liveness is a server-side auto-ping, not a client heartbeat

A game websocket with no traffic on it is killed by the public edge at a
measured 125.6 seconds (two samples, 125.613s and 125.595s, from separate
Cloudflare rays on 2026-09-12), with a bare TCP FIN and no websocket close
frame. The browser reports that as close code 1006, the SPA's abnormal-close
path reconnects a second later, and the reconnect carries the stored autologin
uid straight into `ServerSessionHandler.portal_connect` ->
`login(..., force=True)`. That is the 127.0-second re-login cadence #3745
recorded in production: 125.6s of silence, ~1s of client backoff, ~0.3s of
handshake. Nothing in the chain keeps an idle connection warm on its own —
autobahn's auto-ping defaults to off and Evennia builds the
`WebSocketServerFactory` itself without ever calling `setProtocolOptions`,
Evennia's `IDLE_TIMEOUT` is `-1`, and Caddy sets no proxy timeouts — so every
silent session re-logged in every two minutes.

The keepalive therefore lives on the **server**, as autobahn's `autoPingInterval`
/ `autoPingTimeout` set as class attributes on `SecureWebSocketClient`
(`src/server/portal/secure_websocket.py`). One change covers every websocket
client we will ever have, including ones that are not the SPA, and it buys
dead-link detection we did not have: with `autoPingTimeout` set, a half-open
connection is dropped through Evennia's own disconnect path instead of dying as
a FIN the server never hears about. The rejected alternative is a client-side
heartbeat in `useGameSocket.ts` — it only ever protects the one client that
implements it, it has to invent an application frame for a transport-level
problem, and it leaves a wedged browser tab indistinguishable from a live one.

The interval is pinned to the measurement, not to a round number: 45s puts two
pings inside the 125.6s window, so a single lost ping does not cost the
connection. If the edge timeout ever moves, re-measure with
`tools/ws_idle_probe.py` and re-argue the interval against the new number; the
tests in `src/server/portal/tests/test_websocket_keepalive.py` assert the
margins against it rather than against the constants themselves. Raising the
edge timeout is not an option we control, and paying Cloudflare to raise it
would be one — a keepalive is cheaper and works behind any intermediary.

> Status: accepted · Source: #3745 (2026-09-12) · Related: #3743, #3742,
> `docs/operations/websocket-liveness.md`
