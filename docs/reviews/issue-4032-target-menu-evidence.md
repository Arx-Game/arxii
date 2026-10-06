# Review evidence — issue #4032

- Reviewed revision: `569112236a7aec02e90cc510e31d55ef212867b1`
- Reviewer: `4032-final-visual-fidelity-api-types` (independent visual review); focused implementation reviewers covered security, privacy, API/mock contract, performance, shared-caller reachability, enumerated sets, operability, and outcome delivery.
- Reviewer verdict: PASS
- Application/build identity: Arx II target-menu implementation and generated API contract at source commit `569112236a7aec02e90cc510e31d55ef212867b1`. `just gen-api-types` generated `src/schema.json` and `frontend/src/generated/api.d.ts`; a second run produced no diff. `pnpm build` passed before screenshots were captured.
- Environment: project devcontainer; Playwright Chromium with mocked REST routes; local SQLite test environment for backend suites. No deployed environment or authenticated live API session was used.
- Viewports/themes: eight component-level crops at sizes in the capture manifest; current app uses neutral white/gray surfaces, dark text, and modern sans-serif controls. The approved walkthrough uses warm cream surfaces, Georgia-led serif type, muted brown borders, red primary, and gold accents.
- Approved design: human-approved issue #4032 spec and local static demo `tmp/issue-4032-demo.html`; pair/state mapping is in `frontend/e2e/target-menu-approved-states.spec.ts` and `frontend/e2e/target-menu-worn-row.spec.ts`. The demo is local-only, not a hosted live app.
- Visual review: independent reviewer passed all eight content/state pairs and found no material behavior/content contradiction. The reviewer judged styling fidelity notably low versus the approved walkthrough. This is not a pixel-parity claim or a claim that the style difference is accepted. The maintainer directed that human review of visual evidence happen on the PR rather than block PR opening; the notable style departure is explicitly handed off for that review.
- Visual verdict: PASS
- Screenshots: ![Loose item menu](.github/issue-evidence/4032/569112236-loose-item-menu.png) and seven additional matched component captures are shown below.
- Comparison notes: state and affordance match in all eight pairs. Fixture recipient/item/blocked-reason labels differ from illustrative demo placeholders. The Give walkthrough paragraph is an annotation rather than live chooser content; the LookDialog worn-item menu is shown in its separately mapped capture; the authored-risk demo says its sample values are illustrative. Styling differs substantially: compact white/gray sans-serif UI versus warm cream/Georgia/brown with red and gold accents. Cropped components are not full-screen comparisons.
- Tested interactions: right-click, touch long-press, keyboard context menu (`Shift+F10`), Escape/focus-close paths, preserved left-click detail, blocked Go reason, Place Join/Leave, Give, Put in, Use, cosmetic Use, LookDialog/worn-item Look, and authored-action risk-before-confirmation/no-dispatch-on-open.
- Fixture/live boundary: Playwright intercepts REST responses and proves rendered UI plus fixture dispatch payloads only. Django test-client/action suites exercise endpoint and action code against SQLite, not a deployed/live service. Production cache configuration was not inspected; LocMemCache throttle limits are documented as process-local best effort unless deployment uses a shared backend.
- Overall outcome: PASS

## Requirement ledger

|id|status|evidence|authorizeddecision|
|---|---|---|---|
|gestures|PASS|The 20 Playwright tests include right-click, touch long-press, and Shift+F10; 28 target-menu Vitest tests pass.|Existing left-click remains intact.|
|left-click|PASS|`target-menu-worn-row.spec.ts` verifies the right-click server assertion and left-click item detail; persona menu remains unchanged.|Additive interaction only.|
|candidate-pages|PASS|Django API tests traverse bounded cursor pages; page size remains bounded and choices are not silently truncated.|All candidates remain reachable.|
|blocked-reasons|PASS|Playwright verifies disabled Go/out-of-reach and blocked container/option reasons; backend tests exercise action-owned availability.|Blocked choices remain visible with safe reasons.|
|privacy|PASS|Worn-context/menu tests cover viewer-visible masks and stale visibility; independent privacy review found no issue.|Only viewer-visible content is exposed.|
|dispatch|PASS|Backend tests cover typed IDs, stale revalidation, authored refs, execution checks, and shared UseItemAction/travel paths.|Existing action execution remains authoritative.|
|authored-risk|PASS|API tests verify risk projection reads once per unique pool; Playwright confirms risk appears before confirmation.|No mechanics or seed-data values are invented.|
|api-schema-types|PASS|`just gen-api-types` adds the menu endpoint to OpenAPI and TypeScript declarations; repeated generation leaves no diff.|Generated contract is committed and reproducible.|
|visual-states|PASS|Independent exact-source review passes all eight content/state pairs; the substantial styling gap is explicitly recorded above.|Maintainer directed human visual review on the PR; no style acceptance is claimed.|
|fixture-boundary|PASS|Report separates fixture-backed browser evidence from SQLite endpoint/action tests and makes no live-service claim.|No production/live-player evidence is claimed.|

## Screenshots

![Loose item menu](.github/issue-evidence/4032/569112236-loose-item-menu.png)
![Give chooser](.github/issue-evidence/4032/569112236-give-chooser.png)
![Put-in chooser](.github/issue-evidence/4032/569112236-put-in-chooser.png)
![Use-target chooser](.github/issue-evidence/4032/569112236-use-target-chooser.png)
![Cosmetic-use chooser](.github/issue-evidence/4032/569112236-cosmetic-use.png)
![Look dialog](.github/issue-evidence/4032/569112236-look-dialog.png)
![Worn-item menu](.github/issue-evidence/4032/569112236-worn-item-menu.png)
![Authored-risk dialog](.github/issue-evidence/4032/569112236-authored-risk.png)

## Visual checklist

|element|expected|result|evidence|
|---|---|---|---|
|loose-item-menu|Plain cloak with Look and Get; opening does not execute an action.|MATCH|.github/issue-evidence/4032/569112236-loose-item-menu.png|
|give-chooser|Selected item, visible recipient, and Cancel/Give controls.|MATCH|.github/issue-evidence/4032/569112236-give-chooser.png|
|put-in-chooser|Selected item, available and blocked container with reason, and Cancel/Put in.|MATCH|.github/issue-evidence/4032/569112236-put-in-chooser.png|
|use-target-chooser|Available target, out-of-reach target reason, and Use/Cancel.|MATCH|.github/issue-evidence/4032/569112236-use-target-chooser.png|
|cosmetic-use|Selected and unlearned options, optional descriptor/blend, and Use/Cancel.|MATCH|.github/issue-evidence/4032/569112236-cosmetic-use.png|
|look-dialog|Viewer-visible worn row, appearance sentence, and View sheet affordance.|MATCH|.github/issue-evidence/4032/569112236-look-dialog.png|
|worn-item-menu|Visible worn item offers Look without replacing left-click.|MATCH|.github/issue-evidence/4032/569112236-worn-item-menu.png|
|authored-risk|Authored action risk and outcomes appear before confirmation.|MATCH|.github/issue-evidence/4032/569112236-authored-risk.png|

## Validation

- `uv run arx test actions.tests.test_items_actions actions.tests.test_target_menu_api actions.tests.test_staged_use actions.tests.test_staged_give actions.tests.test_staged_put_in actions.tests.test_place_exit_menu_actions actions.tests.test_consequence_pools world.checks.tests.test_consequence_resolution --sqlite --exclude-tag postgres` — 185 passed on unchanged backend/action code.
- Full PR backend CI shards passed on the same backend tree before the generated-only API contract commit.
- `pnpm exec vitest run src/game/target-menu` — 28 passed with generated types present.
- `pnpm typecheck` — passed with generated types present.
- `just gen-api-types` — passed twice; the second run left `src/schema.json` and `frontend/src/generated/api.d.ts` unchanged.
- `pnpm build` — passed at the reviewed source commit.
- `pnpm exec playwright test e2e/target-menu-approved-states.spec.ts e2e/target-menu-worn-row.spec.ts` — 20 passed at the reviewed source commit; these runs produced the screenshots above.
- Commit hooks for the generated contract files passed, including TypeScript, ESLint, and Prettier.

## Review disposition

- Security, privacy, operability, outcome delivery, and performance reviews found no remaining actionable issue.
- The API/mock-contract mismatch was fixed with mutually exclusive owner/container contexts, pre-fetch rejection, and a snapshot-hook guard; generated OpenAPI and TypeScript declarations are now committed.
- Performance findings were fixed: candidate hydration/option-label N+1 reads were removed or batched; authored consequence pools/fallback projections are request-cached.
- Shared-caller coverage findings were resolved with `UseItemAction` refusal and no-arrival `TravelAction` tests.
- The enumerated-set review found no stale hand-enumerated target/action/input/candidate families.
- The notable visual-style gap is not represented as accepted. Human review is requested on PR #4184, per maintainer direction.
- No feature schema/data migration was added; `src/schema.json` and frontend declarations are generated API contract artifacts.

## Unresolved findings
