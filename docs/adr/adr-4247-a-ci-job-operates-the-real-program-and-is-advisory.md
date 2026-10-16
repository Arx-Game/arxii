# ADR-4247: A CI job operates the real program, and it is advisory

**Status:** Accepted (2026-10-16, defaults taken under the maintainer's standing
"adopt a default and mark it overridable" preference; the maintainer may override)
**Issue:** #4247 (child of #4246)
**Related:** ADR-4246, ADR-0083 (CI schema from models), ADR-0021 (merge queue)

## Context

No workflow ran Playwright or started the game server, so the specs that need a live
server on :4001 ran only when a person ran `just fe-e2e`. A small machine records
`BLOCKED: resources` under ADR-4246 and the evidence then has to come from elsewhere;
evidence produced by CI cannot be fabricated by the agent.

## Decision

`.github/workflows/real-test.yml` builds a throwaway Postgres database, builds the
frontend, runs `arx start`, runs the live-server specs with one worker and uploads
screenshots, traces and server logs as one artifact. A run of it is acceptable
evidence under `tools/skills/real-testing/`, cited by run URL and artifact URL
(`docs/testing/real-test-ci.md`).

- **Advisory, not required.** It matches the evidence challenger, and a flaky browser
  job must not block the merge queue while it beds in. It is not in `ci.yml`.
- **Triggers:** PRs touching `frontend/**`, `src/web/**`,
  `src/world/**/views.py` or `serializers.py`; the `real-test` label;
  `workflow_dispatch`.
- **Budget:** one job, one worker, 25 minutes at most, cancel-in-progress per PR.

## Rejected alternatives

- **Required check.** A missing or flaky check hangs the queue (as ADR-4246 found for
  the challenger).
- **Every PR.** Browser installs and a server start for a backend-only PR spend
  runner slots against the org cap for no new evidence; the label covers the rest.
- **A job inside `ci.yml`.** It would share the required aggregators' concurrency
  group and `merge_group` triggers.

## Consequences

The job covers only the two specs that need a live server today. A claim about a
surface they do not visit still needs its own spec or a `BLOCKED` answer.
