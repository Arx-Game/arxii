# Review evidence

- Reviewed revision: `45ccfb9bddd5ec7edf250f3441ec1744b9ab8702`
- Reviewer: Claude Code adversarial diff reviewer (read-only pass over `main..HEAD`), findings resolved in 45ccfb9
- Reviewer verdict: PASS
- Application/build identity: production Vite bundle from `pnpm build` at 45ccfb9, served by `vite preview` on :4173 (the same bundle Django/TwistedWeb serves)
- Environment: devcontainer, Linux 6.6 (WSL2), Node 20, pnpm; Chromium via Playwright; Vitest 5 on jsdom
- Viewports/themes: Chromium default desktop viewport, the application's default theme (this change alters no styling, markup or layout)
- Approved design: Not applicable. #3784 is a tech-debt refactor with no demo or design attached to the issue; the composer's rendered markup is byte-identical apart from where its `value` is read from.
- Visual review: Not applicable. There is no approved design to compare a render against, and the change moves where the composer's text is stored, not what it draws. Behaviour was exercised in a real browser instead (see Tested interactions).
- Visual verdict: NOT_APPLICABLE
- Screenshots: Not applicable
- Comparison notes: Not applicable
- Tested interactions: In a real Chromium against the production bundle — typing a draft during "Entering world" and confirming it survives the first `room_state` broadcast; a say dispatched, dropped and retried under the same `client_request_id`; an unrelated concurrent `action_result` arriving before this send's own; a reconnect reauthorizing before the composer returns to ready; travelling between rooms with an unsent draft in each; switching conversation tabs with an unsent draft in each. In jsdom — every clear-on-success path (REST pose, WS ack, companion emote, the legacy WS fallback, the reconnect lookup), a newer edit typed while a request is in flight, a rejected send keeping its text, ArrowUp recall, the `@target` append, a `draftScope` change between rooms, and a provisional scope settling both into its own room and into a different conversation.
- Fixture/live boundary: Every browser journey is fixture-backed — REST is mocked with `page.route`, the game WebSocket with `page.routeWebSocket`; no Django/Evennia process, no database, no real wire serialization. The Vitest suites are jsdom with mocked `useGameSocket`, store and query hooks. This pass proves the browser-side draft contract only; nothing here exercises a live backend.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | `arx:play-draft:v1` is gone from `frontend/src` (grep); `draft.content` is the textarea's `value` and `setContent` its only write path. New test "writes typed text straight to the draft row, with no second key alongside it" advances fake timers past the retired 500ms debounce and asserts exactly one persisted key. | |
| A02 | PASS | All 83 pre-existing `CommandInput.test.tsx` tests pass unchanged once the duplicate v1 seeds are removed; 973 tests green across `src/game`, `src/hooks`, `src/scenes`. The deleted `commandRef.current === trimmed` guard is subsumed by `acknowledge`'s id match at all five call sites — reviewed explicitly and confirmed equivalent-or-stricter, since `setContent` nulls `clientRequestId` on every edit. | |
| A03 | PASS | `e2e/game-entry.spec.ts` ("a quiet-room entry preserves an editable draft until structured presence arrives") goes from red to green. It was verified red against main's `frontend/src` at 2d966b8 with the same build and runner, so this is a fix, not a new guard. | |
| A04 | PASS | Reviewer finding: the first carry-forward could move a room pose into a whisper tab opening mid-entry. Fixed in 45ccfb9 by requiring the conversation identity to match; `DraftScopeSettling` is a union so the pair cannot be half-declared. Two tests ("never carries a provisional draft into a different conversation", "does not carry a provisional draft into a conversation tab that opens first") both fail when the identity half of the gate is removed. | |
| A05 | PASS | #3760's "travel preserves separate drafts per room" and "per conversation tab" journeys still pass, so the carry did not weaken room/tab isolation. | |
| A06 | PASS | `pnpm typecheck` clean; ESLint and Prettier clean on all five changed frontend files; the repo pre-commit hook set (ESLint, TypeScript Check, Prettier, ty) passed on every commit. | |
| A07 | PASS | Full local `pnpm exec playwright test`: 80 passed, 18 failed. The same 18 fail identically against main's `frontend/src` (17 need the Django backend on :4001, which is not running here; 2 encounter-reachability specs fail on main too). The only delta this branch makes is `game-entry` red to green. | |

## Unresolved findings

- None

## Notes carried to the PR body, not blocking this pass

- No workflow in `.github/workflows` runs Playwright, so these journeys gate locally
  only. That is how a red `game-entry.spec.ts` reached main.
- Two `narrative-play-encounter-reachability` specs and the backend-dependent
  `user-journey`/`account-settings`/`smoke` login specs fail on main as well, for
  reasons unrelated to drafts. Not touched here.
- Pre-existing and unchanged by this PR: a draft key that changes while a send is
  genuinely in flight leaves that request's `.then()` holding an `acknowledge` bound
  to the old key. The textarea is disabled while `pending`, so it is not reachable by
  typing; a reconnect's `reconcileStoredDrafts` scan or "Check status" resolves it.
