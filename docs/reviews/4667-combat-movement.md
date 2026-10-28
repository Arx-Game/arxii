# Review evidence — issue #4667

- Reviewed revision: `5ba0208372e3dff1ab8303750d96589c573e6f0b`
- Reviewer: TehomCD (implementation review)
- Reviewer verdict: PASS
- Application/build identity: Arx II frontend production bundle (`pnpm build`), served by Vite preview; test: `frontend/e2e/combat-movement-panel.spec.ts`
- Environment: Playwright Chromium, one worker, local worktree, production bundle
- Viewports/themes: Chromium default viewport, default Arx theme
- Approved design: Lightweight bug report #4667 fix shape; show blocked crossing disabled with reason and refresh actions after movement
- Visual review: Compared the actual rendered before/after movement panel to the issue's expected states; blocked crossing is legible, disabled, and includes its reason; post-move list displays the new position action
- Visual verdict: PASS
- Screenshots: ![Movement panel before successful move](docs/reviews/4667-movement-panel-before.png) ![Movement panel after successful move](docs/reviews/4667-movement-panel-after.png)
- Comparison notes: Before: enabled `Move to Middle`, and disabled `Move to Gallery (blocked: Iron Railing)` with `Gated by challenge: Iron Railing`. After: `Move to West`; stale `Move to Middle` and blocked Gallery entry are gone.
- Tested interactions: Entered the mocked scene, opened Combat, checked blocked action visibility/disabled state/reason, dispatched Move to Middle, observed an additional available-actions request and replaced movement action without waiting for the 10-second polling period.
- Fixture/live boundary: Mocked auth, WebSocket room entry, encounter, available-actions, and dispatch REST payloads. Proves actual built-client rendering and interactions only; does not claim live backend or browser-to-server integration. Backend serializer/action availability are separately covered by focused tests. An isolated live-server attempt was blocked before launch because `seed_test_account` failed during Evennia account first-save (`SESSION_HANDLER` was `None`); its temporary database was removed. The stale shared Postgres test schema was not counted as evidence.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Blocked Gallery crossing | Disabled, readable reason visible | MATCH | `4667-movement-panel-before.png` |
| Post-move list | Old actions replaced by current position action | MATCH | `4667-movement-panel-after.png` |

## Requirement ledger

|id|status|evidence|authorizeddecision|
|---|---|---|---|
|blocked-wall|PASS|Built-app Playwright fixture shows disabled Gallery crossing and server reason|Issue #4667|
|move-refresh|PASS|Built-app Playwright dispatch causes new actions request and current-position panel|Issue #4667|
|backend-marker|PASS|Serializer test asserts CHALLENGE backend movement marker; availability suite passes|Issue #4667|

## Verification details

- `cd frontend && pnpm build`: passed.
- `cd frontend && pnpm exec playwright test --config playwright.config.ts --workers=1 e2e/combat-movement-panel.spec.ts`: 1 passed. Screenshot capture run also passed.
- `cd frontend && pnpm exec vitest run src/combat/roundActionHelpers.test.ts src/combat/components/MovementActions.test.tsx`: 16 passed.
- `cd frontend && pnpm typecheck`: passed.
- `just test-fast actions.tests.test_player_action_serializer`: 9 passed.
- `just test-fast actions.tests.test_get_player_actions_enhancements`: 6 passed.
- Browser fixture is mocked; the report does not assert live backend integration.

## Unresolved findings
- None
