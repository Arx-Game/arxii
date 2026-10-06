# Review evidence — issue #4032

- Reviewed revision: `2451681fa12027d8da993a6a814c6e316a262f17`
- Reviewer: `4032-final-visual-fidelity-merged` (independent visual-fidelity review); focused code reviewers covered security, privacy, API/mock contract, performance, shared-caller reachability, enumerated sets, operability, and outcome delivery.
- Reviewer verdict: PASS
- Application/build identity: Arx II web frontend and action API at source commit `2451681fa12027d8da993a6a814c6e316a262f17`; `pnpm build` passed before capture. The screenshot suite is Playwright Chromium with fixture-backed REST routes.
- Environment: project devcontainer; SQLite fast-tier Django tests; Vite production build; headless Playwright Chromium. No deployed environment or authenticated live API session was used.
- Viewports/themes: component crops captured at CSS sizes shown in the manifest; app menu/dialog surfaces use the current neutral white/gray sans-serif treatment. Approved demo panels use warm ivory/serif/rust styling.
- Approved design: human-approved issue #4032 spec and the local static demo `tmp/issue-4032-demo.html`; pair/state mapping is in `frontend/e2e/target-menu-approved-states.spec.ts` and `frontend/e2e/target-menu-worn-row.spec.ts`. The demo is local-only, not a hosted live app.
- Visual review: the independent reviewer returned MATCHES WITH NOTED GAPS for all eight matching states. Choices, blocked reasons, labels, and confirmation/risk content match; the visible style and some control representations differ. The gate disposition is PASS because no approved player-facing choice or state is missing or contradicted. The style difference is disclosed for human review on the PR, as authorized by the maintainer.
- Visual verdict: PASS
- Screenshots: ![Loose item menu](.github/issue-evidence/4032/2451681fa-loose-item-menu.png) and seven additional matched component captures are shown below.
- Comparison notes: the app uses white/gray sans-serif surfaces and radio rows where the demo uses warm cream/serif surfaces and compact status/select-like rows. The difference is noticeable and is not claimed as pixel parity. Fixture names/reasons may differ from illustrative demo copy while preserving the required state/affordance. No pair has missing or contradictory choices, blockers, or risk text.
- Tested interactions: right-click menus; touch long-press; keyboard context menu (`Shift+F10`); Escape/focus-close paths; preserved left-click item detail; blocked Go reason; Place Join/Leave; Give, Put in, Use, cosmetic Use, LookDialog/worn-item Look, and authored-action confirm/no-open-dispatch behavior.
- Fixture/live boundary: the Playwright tests intercept/mock REST responses and prove the rendered UI plus fixture dispatch payloads only. The Django test client/action suites exercise the real endpoint and action code against SQLite; they are not a production/live-service test. Production cache configuration was not inspected; target throttle behavior is documented as process-local best effort under LocMemCache unless deployment config supplies a shared backend.
- Overall outcome: PASS

## Requirement ledger

|id|status|evidence|authorizeddecision|
|---|---|---|---|
|gestures|PASS|The 20 Playwright tests include right-click, long-press touch, and Shift+F10 paths; target-menu unit suite has 28 passing tests.|Maintainer-approved context-menu scope; existing left-click stays intact.|
|left-click|PASS|`target-menu-worn-row.spec.ts` verifies right-click server assertion and left-click still drills into item detail; persona menu remains unchanged.|Additive interaction only.|
|candidate-pages|PASS|Django API tests traverse bounded cursor pages and retain the page-size bound; 185 focused backend tests pass.|All candidates remain reachable; no silent truncation.|
|blocked-reasons|PASS|Playwright verifies disabled Go/Out-of-reach and blocked container/option reasons; backend tests exercise action-owned availability.|Blocked visible choices remain visible with the real safe reason.|
|privacy|PASS|Worn-context and menu tests cover hidden layers, viewer-visible masks, stale visibility, and safe candidate labels; independent privacy review found no issue.|Only existing viewer-visible content is exposed.|
|dispatch|PASS|Backend tests cover typed IDs, stale revalidation, authored refs, execution checks, and the UseItemAction/travel shared-caller paths.|Existing action execution remains authoritative.|
|authored-risk|PASS|API test verifies risk projection and one consequence read per unique pool; Playwright confirms risk before authored confirmation.|No invented mechanic or claim about seeded Ignite content.|
|visual-states|PASS|Independent exact-source review matched all eight screenshot/demo pairs and recorded the treatment differences.|Maintainer accepted the disclosed visual difference for PR review; human review is invited.|
|fixture-boundary|PASS|Report separates mocked browser routes from SQLite API/action tests and makes no live-service claim.|No production or live-player evidence is claimed.|

## Screenshots

![Loose item menu](.github/issue-evidence/4032/2451681fa-loose-item-menu.png)
![Give chooser](.github/issue-evidence/4032/2451681fa-give-chooser.png)
![Put-in chooser](.github/issue-evidence/4032/2451681fa-put-in-chooser.png)
![Use-target chooser](.github/issue-evidence/4032/2451681fa-use-target-chooser.png)
![Cosmetic-use chooser](.github/issue-evidence/4032/2451681fa-cosmetic-use.png)
![Look dialog](.github/issue-evidence/4032/2451681fa-look-dialog.png)
![Worn-item menu](.github/issue-evidence/4032/2451681fa-worn-item-menu.png)
![Authored-risk dialog](.github/issue-evidence/4032/2451681fa-authored-risk.png)

## Visual checklist

|element|expected|result|evidence|
|---|---|---|---|
|loose-item-menu|Plain cloak with Look and Get; opening does not execute an action.|MATCH|.github/issue-evidence/4032/2451681fa-loose-item-menu.png|
|give-chooser|Selected item, visible recipient, and Cancel/Give controls.|MATCH|.github/issue-evidence/4032/2451681fa-give-chooser.png|
|put-in-chooser|Selected item, available container, blocked container with reason, and Cancel/Put in.|MATCH|.github/issue-evidence/4032/2451681fa-put-in-chooser.png|
|use-target-chooser|Available target, out-of-reach target reason, and Use/Cancel.|MATCH|.github/issue-evidence/4032/2451681fa-use-target-chooser.png|
|cosmetic-use|Selected and unlearned options, optional descriptor/blend, and Use/Cancel.|MATCH|.github/issue-evidence/4032/2451681fa-cosmetic-use.png|
|look-dialog|Viewer-visible worn row, appearance sentence, and View sheet affordance.|MATCH|.github/issue-evidence/4032/2451681fa-look-dialog.png|
|worn-item-menu|Visible worn item offers Look without replacing left-click.|MATCH|.github/issue-evidence/4032/2451681fa-worn-item-menu.png|
|authored-risk|Authored action risk and outcomes appear before confirmation.|MATCH|.github/issue-evidence/4032/2451681fa-authored-risk.png|

## Validation

- `uv run arx test actions.tests.test_items_actions actions.tests.test_target_menu_api actions.tests.test_staged_use actions.tests.test_staged_give actions.tests.test_staged_put_in actions.tests.test_place_exit_menu_actions actions.tests.test_consequence_pools world.checks.tests.test_consequence_resolution --sqlite --exclude-tag postgres` — 185 passed.
- `pnpm exec vitest run src/game/target-menu` — 28 passed.
- `pnpm typecheck` — passed.
- Targeted ESLint and `uv run ruff check` — passed.
- `pnpm build` — passed.
- `pnpm exec playwright test e2e/target-menu-approved-states.spec.ts e2e/target-menu-worn-row.spec.ts` — 20 passed; these exact-source runs saved the screenshots above.
- Repository commit and push hooks passed, including TypeScript, ESLint, Prettier, migration, and Ruff checks.

## Review disposition

- Security, privacy, operability, outcome delivery, and performance reviews found no remaining actionable issue.
- The API/mock-contract mismatch was fixed with an exclusive owner/container context union, pre-fetch runtime rejection, and a snapshot-hook guard; focused tests cover the invalid path.
- Performance findings were fixed: candidate hydration/option-label N+1 reads were removed or batched; authored consequence pools and fallback projections are request-cached.
- Shared-caller coverage findings were resolved with tests for safe `UseItemAction` refusal and no-arrival `TravelAction` behavior.
- The enumerated-set review found no stale hand-enumerated target/action/input/candidate families.
- No feature schema or data migration was added. The merge from current `main` carries upstream-only changes and was tested separately.

## Unresolved findings
