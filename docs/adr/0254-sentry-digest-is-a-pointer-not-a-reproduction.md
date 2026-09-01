# The Sentry digest issue is a pointer, never a reproduction

Sentry has been ingest-only since #2236 Phase 5: `src/server/conf/settings.py` calls
`sentry_sdk.init()` from a write-only DSN, and nothing ever read the errors back, so
production exceptions accumulated where no agent could see them. `tools/sentry_digest.py`
plus `.github/workflows/sentry-digest.yml` close that loop on a daily 09:00 UTC schedule,
rewriting a single rolling GitHub issue labelled `sentry` with the currently-unresolved
Sentry issues; `tools/sentry_resolve.py` marks them resolved once the fix ships. Read
access is `SENTRY_AUTH_TOKEN`, structurally a different credential from the DSN, which
can only write - and specifically *not* a Sentry organization auth token, whose fixed
release-management scopes 403 on every issue endpoint (see
`docs/operations/sentry-triage.md`).

**This repo is public, and that decides the digest's content.** Each row carries only
Sentry's own short id, a permalink, the level, event and user counts, and first/last-seen
dates. The exception message, culprit path, stack frames and request data are
deliberately *not* copied across: a public issue that quoted a live production traceback
would hand any reader a step-by-step route to the same failure, on a game whose players
have a standing incentive to find one. The detail stays behind Sentry's auth, where the
agent that picks the row up reads it. `test_body_never_leaks_message_or_culprit` pins
this - the fixture carries a title, culprit and metadata value precisely so the test can
assert none of them reach the body.

**Rejected: one GitHub issue per Sentry issue**, mirroring `tools/sonarcloud_sync.py`.
That shape is better for agents claiming work - a card each, deduped by an embedded
marker - but a per-issue card wants a per-issue title to be claimable at all, and a
useful title *is* the exception and its culprit. The digest sacrifices claimability to
keep the public surface a pure pointer. SonarCloud can afford per-issue cards because
its findings describe our source, which is already public, and it excludes security
findings for the same reason this excludes tracebacks.

**Rejected: creating an empty digest.** When Sentry reports nothing unresolved the tool
opens no issue and closes any open digest, so a clean morning leaves no card on the
board (ruled 2026-09-01). A recurring "0 issues" issue trains agents to ignore the label.

**Rejected: a private mirror repo for the detail.** It would restore claimable per-issue
cards, but it splits the board in two and puts the work items where the project
automation (`docs/project-board-automation.md`) cannot see them. Sentry already is that
private surface; a second one earns nothing.

> Status: accepted · Source: session 2026-09-01 (extends #2236 Phase 5)
