# Review evidence — issue #4667

Reviewed revision: `03d1c5067fac792fdeffd1db444758b8902abc38` (implementation commit; the report commit is its child).

## Environment and provenance

- Exact source: worktree branch `feature-4667-combat-movement-panel-hides-blocked-wall`; built with `cd frontend && pnpm build` (Vite production bundle), then served by Playwright's Vite preview at localhost:4173.
- Browser: Playwright Chromium, one worker, `frontend/e2e/combat-movement-panel.spec.ts`.
- Data boundary: isolated fixture with mocked auth, WebSocket room entry, encounter, available-actions and dispatch REST responses. No live backend was used. This is client rendering/interaction evidence only; backend request/dispatch integration remains unverified in a live server.
- Captures below were made by that test from the built bundle on the reviewed source. `movement-panel-before.png` shows a normal move and a disabled blocked crossing with its reason. `movement-panel-after.png` shows the new-position move after dispatch and query invalidation.

## Checks performed and observed

1. **Blocked wall visibility:** Opened `/game`, entered the mocked scene, and selected Combat. Expected `Move to Gallery (blocked: Iron Railing)` to appear disabled and explain the gating challenge. Observed the disabled entry and `Gated by challenge: Iron Railing` in the rendered movement panel. Capture: `movement-panel-before.png`.
2. **Successful move refresh:** Clicked the enabled `Move to Middle` action. Expected a dispatch and a fresh available-actions request without waiting for the 10-second poll, with old-position actions replaced. Observed one dispatch, an additional available-actions request, and the panel changed to `Move to West`; the previous move disappeared. Capture: `movement-panel-after.png`.
3. **Automated checks:** `pnpm build` passed; focused Playwright test passed (1 test); focused Vitest tests passed (16); `pnpm typecheck` passed. `just test-fast actions.tests.test_player_action_serializer` passed (9 tests) and `just test-fast actions.tests.test_get_player_actions_enhancements` passed (6 tests).
4. **Backend boundary:** Live isolated-server attempt was blocked before server startup: `seed_test_account` failed in Evennia account first-save because `SESSION_HANDLER` was `None` during cmdset initialization. The temporary `rt_4667` database was dropped. An existing Postgres test DB was stale (`arxii_conditiontemplate.holds_breath` missing) and was not counted as a pass. No production/shared database was touched.

## Mandatory criteria

- Blocked crossing visible and disabled with reason: **PASS (mocked REST fixture; client behavior only)**.
- Successful movement refreshes available actions immediately: **PASS (mocked REST fixture; observed follow-up request and changed panel)**.
- Live backend integration: **BLOCKED** — account seeding failed as described above.

## Unresolved findings

None for the tested client-side behavior. Live backend integration remains blocked and is not claimed as verified.
