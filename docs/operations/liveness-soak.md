# Authenticated liveness soak runbook

This runbook is the reusable acceptance harness for #4008. It is an **opt-in
live check**, not a fixture test. The Playwright fixtures under `frontend/e2e`
may prove deterministic UI behavior, but they cannot prove a production or
rehearsal listener stayed connected.

## Safety and scope

- Use a dedicated test account supplied through the environment. Never put its
  username or password in a command line, report, issue, PR, or repository
  file. The account must have a selected character and be allowed to use each
  listener being tested.
- Run only against an approved rehearsal or public deployment. The harness is
  read-only after login: the browser sends no game input, and the Telnet probe
  sends only login lines and protocol negotiation replies.
- Keep reports outside the checkout. They contain endpoint/configuration
  metadata and timing, not credentials or game text; treat hostnames and
  deployment details as private-safe operational evidence.
- The duration is bounded to 3,600 seconds. The acceptance bound should be
  longer than the observed failure interval (the default is 600 seconds).
- A close before the bound is a failure. The report marks
  `manual_reconnect_required: true`; do not reconnect and call the same run a
  pass.

## Identity and configuration

Set the deployed commit and an operator-owned configuration identifier before
starting. The revision is the exact commit running at the target, not merely
the local checkout. `LIVENESS_CONFIG_ID` should identify the rendered listener
configuration (for example, a hash from the deployment system). Do not put
secrets in either value.

```bash
export LIVENESS_DEPLOYMENT_REVISION='<deployed-commit-sha>'
export LIVENESS_CONFIG_ID='<listener-config-id>'
export LIVENESS_SOAK_SECONDS=600
```

If either value is omitted, the browser check refuses to start. The Telnet
probe can derive a local Git SHA for development, but live evidence must set
`LIVENESS_DEPLOYMENT_REVISION` explicitly.

## Authenticated browser

Install Chromium in the frontend environment, then run the dedicated config.
The URL must be the production-equivalent public/rehearsal URL. Do not use the
fixture routes or `playwright.config.ts`'s Vite preview for acceptance.

```bash
export LIVENESS_SOAK_ENABLE=1
export LIVENESS_SOAK_BASE_URL='https://play.example.invalid'
export LIVENESS_SOAK_USERNAME='...'       # environment only
export LIVENESS_SOAK_PASSWORD='...'       # environment only
export LIVENESS_SOAK_SECONDS=600

mkdir -p "${TMPDIR:-/tmp}/arxii-liveness"
chmod 700 "${TMPDIR:-/tmp}/arxii-liveness"
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend exec playwright test \
  --config liveness-soak.playwright.config.ts \
  --output "${TMPDIR:-/tmp}/arxii-liveness/browser-results"
```

The test logs one `LIVENESS_RESULT` JSON line. It records the socket count,
open/close counters, numeric close codes, clean-close count, frame counters,
revision, config id, timestamps, and elapsed time. It never records frame data,
URLs with query strings, cookies, or credentials. Browser JavaScript cannot
observe WebSocket protocol ping/pong; correlate that layer with the Portal
export from #3934 when available.

A socket close fails the run even if the app automatically opens a replacement.
That preserves the acceptance rule: a healthy idle session must not need a
reconnect. If testing recovery is the goal, record that as a separate bounded
experiment and do not reuse this pass/fail result.

## Telnet-family listeners

Run one probe per **enabled** listener. The probe handles Telnet negotiation
(`DO`, `DONT`, `WILL`, `WONT`, and subnegotiation) and counts control frames
without storing payloads. It does not send application commands after login.
Use a TLS-allowed account. If two listeners share the same endpoint, run them
separately and retain both reports.

TLS with normal certificate verification:

```bash
export ARXII_SOAK_TELNET_USERNAME='...'     # environment only
export ARXII_SOAK_TELNET_PASSWORD='...'     # environment only
uv run python tools/telnet_idle_soak.py telnet.example.invalid \
  --port 4003 --tls --seconds "${LIVENESS_SOAK_SECONDS}" \
  --report "${TMPDIR:-/tmp}/arxii-liveness/telnet-tls.json"
```

Plain Telnet is supported only where the deployment intentionally enables it:

```bash
uv run python tools/telnet_idle_soak.py telnet.example.invalid \
  --port 4000 --seconds "${LIVENESS_SOAK_SECONDS}" \
  --report "${TMPDIR:-/tmp}/arxii-liveness/telnet-plain.json"
```

The current infrastructure is TLS-only and closes plaintext Telnet. In that
configuration, do **not** label a rejected plaintext connection as a failed
idle soak or as a passed supported listener. Record it as `not_supported` in
the listener matrix and use the existing read-only smoke check to prove the
plaintext port is closed; run the authenticated soak on port 4003. If a
plaintext listener is advertised as supported, an authenticated `passed`
probe is required for it.

The JSON report has schema `arxii.liveness.telnet.v1`, exact revision/config
metadata, TLS verification mode, timestamps, elapsed seconds,
`control_frames`, `keepalive_frames`, and `manual_reconnect_required`. It does not include login
prompts, account names, passwords, commands, or game output. `--insecure` is
allowed only for an approved rehearsal with an internal certificate and must
be called out in the listener matrix.

## Acceptance record

Keep this matrix with the private acceptance decision record, not in Git:

| Client/listener | Public path | Supported? | Bound | Result | Manual reconnect | Revision/config |
| --- | --- | --- | --- | --- | --- | --- |
| Authenticated browser | HTTPS + WSS | yes | 600s+ | `passed`/`failed` | false/true | exact values |
| Telnet plain | configured endpoint | yes/no | 600s+ | `passed`/`not_supported`/`failed` | false/true/NA | exact values |
| Telnet TLS | configured endpoint | yes | 600s+ | `passed`/`failed` | false/true | exact values |

Attach actual live or rehearsal reports only through the approved private path.
If credentials, a selected character, a listener, Portal diagnostics, or an
approved target are unavailable, leave the acceptance gate open and report the
blocker. Fixture output, a local Vite run, an unauthenticated WebSocket probe,
or a source-only test is not live acceptance evidence.
