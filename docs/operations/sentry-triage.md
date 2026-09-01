# Sentry triage — getting production errors onto the board

Sentry ingest has been live since #2236 Phase 5, but the errors were write-only: the
`SENTRY_DSN` in `src/server/conf/settings.py` can send events and read nothing back. This
is the read side.

## The loop

1. **`.github/workflows/sentry-digest.yml`** runs `tools/sentry_digest.py` daily at
   09:00 UTC (and on `workflow_dispatch`, with a `dry_run` input).
2. The tool fetches unresolved issues for the project and rewrites **one rolling GitHub
   issue** labelled `sentry` — the digest. If a digest is already open it is edited in
   place, so the board carries exactly one card no matter how many errors are live.
3. **If Sentry is clean, no issue is created**, and an open digest is closed with a
   comment. A standing "0 issues" card would only teach people to ignore the label.
4. An agent picks a row, opens it *in Sentry*, fixes it on a branch, and ships a PR.
5. Once merged, `python tools/sentry_resolve.py ARXII-1A` marks it resolved in Sentry.
   Close the digest when every row is handled; the next run opens a fresh one if
   anything is still unresolved.

## The digest deliberately withholds the error

Each row is a short id, a link, the level, event/user counts and first/last-seen dates —
and nothing else. **No message, no culprit path, no stack frames, no request data.** This
repo is public, and a quoted production traceback is a reproduction recipe for a failure
in a live game. The detail lives behind Sentry's auth; the digest only points at it. See
[ADR-0254](../adr/0254-sentry-digest-is-a-pointer-not-a-reproduction.md), and
`test_body_never_leaks_message_or_culprit`, which fails if anything richer creeps into
the body.

The practical cost: you cannot triage from the GitHub issue alone. Working a Sentry row
requires Sentry access. That is the trade, taken on purpose.

## Credentials

`SENTRY_AUTH_TOKEN` is a Sentry **organization auth token** — a different credential from
the ingest DSN, which cannot read. Mint it at
`https://sentry.io/settings/arx2/auth-tokens/` with scopes `org:read`, `project:read`,
`event:read`, and `event:write` (the last is what `sentry_resolve.py` needs).

- **CI:** `gh secret set SENTRY_AUTH_TOKEN --repo Arx-Game/arxii`. The workflow step is
  guarded by `if: env.SENTRY_AUTH_TOKEN != ''`, so before the secret exists the job skips
  rather than going red every morning.
- **Locally:** export it in your shell, or add it to `src/.env`. It is never committed.

The org slug and numeric project id are constants in `tools/sentry_constants.py`; the
project id is the `?project=` value from any Sentry issue-stream URL.

## Commands

```bash
python tools/sentry_digest.py --dry-run     # print the digest, touch no issue
python tools/sentry_digest.py               # create or update the rolling digest
python tools/sentry_resolve.py ARXII-1A     # resolve one (accepts several, or numeric ids)
python tools/sentry_resolve.py ARXII-1A --status ignored
```
