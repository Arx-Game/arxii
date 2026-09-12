# Review evidence

Re-stamped again: the PR body's double-backtick Report line was patched via
the REST API (not a push), so the `review-evidence` CI check's first run
validated against the stale pre-patch body captured at the last
`synchronize` event. This commit both re-triggers CI (a new push, since the
PAT has no `Actions:write` to rerun the job directly) and re-points the
reviewed revision at its own new parent, matching CI's
`git rev-parse "${head_sha}^1"` check. No application code changed since the
original `f21195597...` revision this report tested.

- Reviewed revision: `d763c49fd8b3e226345213fd46ed9ef4882f022a`
- Reviewer: Claude Sonnet 5 (self-review; bug fix, no demo/spec — `demo-fidelity-reviewer` does not apply)
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` production bundle served via `vite preview` (Playwright's configured web server); backend via `just test-fast web` (SQLite fast tier)
- Environment: devcontainer (Linux), real Chromium via Playwright, Python 3.13 / Django, Node 20
- Viewports/themes: Not applicable — no visible UI change; default Playwright viewport used for the e2e journeys
- Approved design: Not applicable — bug fix (issue #3781 is `bug`-labeled; user explicitly directed skipping the spec-draft/spec-review/spec:approved gate). No demo link on the issue.
- Visual review: Not applicable — the fix changes only correlation logic inside an existing handler (`CommandInput.tsx`'s `handleActionResult`); no new/changed rendered element
- Visual verdict: NOT_APPLICABLE
- Screenshots: Not applicable (see Visual review)
- Comparison notes: Not applicable
- Tested interactions: Real Chromium browser (Playwright) driving the actual production build through the composer's say/whisper send path: type -> Enter -> "Sending..." pending state -> `ACTION_RESULT` ack carrying a matching `client_request_id` clears the draft. Also exercised: a concurrent, unrelated `ACTION_RESULT` (mismatched `client_request_id`) arriving first is ignored and the pending send stays pending until the real matching ack lands (new regression journey for #3781). Backend: real Django `execute_action` inputfunc (not mocked at the DB layer) exercised via `TestCase`, covering success/error/no-puppet/missing-id/non-string-id paths for the echoed `client_request_id`.
- Fixture/live boundary: The Playwright e2e journeys are fixture-backed (mocked WebSocket + REST via `page.routeWebSocket`/`page.route`), per this spec file's established convention (#3760) — no live Django/Evennia backend or database in that run. The backend echo mechanism itself is proven against real Django code (`web/tests/test_execute_action_inputfunc.py`, SQLite fast tier), calling the actual `execute_action` inputfunc, not a mock of it.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | `src/web/tests/test_execute_action_inputfunc.py` — 5 new tests (echo on success/error/no-puppet, missing id -> None, non-string id -> None); `just test-fast web` — 670 passed | |
| A02 | PASS | `frontend/src/game/components/CommandInput.test.tsx` — 62 passed, incl. new `client_request_id` misattribution-guard test; existing say/whisper ack tests updated to supply a matching id | |
| A03 | PASS | `pnpm vitest run` for `GamePage.test.tsx`, `ItemFocusView.test.tsx`, `WardrobePage.test.tsx`, `ActionAttachment.test.tsx` — 96 passed, unchanged (the other 8 `actionResultBus` consumers are not touched by this fix) | |
| A04 | PASS | `pnpm test:e2e e2e/narrative-play-delivery.spec.ts` (real Chromium against the production build) — 5 passed, incl. new "a concurrent unrelated action_result does not falsely ack a pending send (#3781)" journey | |
| A05 | OUT_OF_SCOPE | | No visible UI/design change — a wire-contract correlation-id fix, not a player-/staff-facing surface; the issue carries no demo link and the user directed a spec-free bug-fix flow, so `demo-fidelity-reviewer` does not apply |

## Unresolved findings

- None
