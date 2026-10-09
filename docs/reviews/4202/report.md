# Review evidence

- Reviewed revision: `11371fe886a3bf3bf7c6d05bea88e640cac06ef1`
- Reviewer: the implementing agent (Claude Code), with Playwright on the real Upbringing Builder page served by this worktree's Django dev server, and on the real CG Lineage stage from the production bundle; no demo link on the issue (lightweight lane), so no demo-fidelity pass; no migration
- Reviewer verdict: PASS
- Application/build identity: the Builder page from `arx manage runserver` at the reviewed revision on port 4203 against the dev database (last night's production copy), read as a superuser contributor; the CG page from `vite build` at the reviewed revision served by `vite preview` on port 4202
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless
- Viewports/themes: 1280x1000 (the Builder) and 1280x1600 (CG), the default light theme
- Approved design: the issue's own change (lightweight): `max_claim_tier` joins the Builder's Family paths fieldset beside the claim path's other knob, in admin's own fieldset markup; the CG name-path picker reads the picked Family Template's description under its row. The Builder's rows are ApostateCD's real Upbringings (Infernal Nobility, "What the House Never Bought"); the CG templates are placeholder fixtures.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The Builder's Family paths fieldset with the new "Founders may claim up to" row between Claimable kinds and Family templates, blank by default, with the field's own help line](docs/reviews/4202/01-builder-family-paths-1280.png) ![The same fieldset after picking Duchy in the select](docs/reviews/4202/02-builder-fieldset-duchy-1280.png) ![The CG Lineage stage on the name path with two Family Templates offered: the Family template row with Commoner family pressed and its description under the row](docs/reviews/4202/03-cg-name-path-picker-1280.png) ![After picking Fallen house: its description reads under the row](docs/reviews/4202/04-cg-name-path-picked-second-1280.png)
- Comparison notes: The Builder renders the new row through admin's `fieldset.html` like its neighbours: label on the left, the select, the model's help text under it, the same rule lines between rows; the select is a real select element named max_claim_tier whose computed display is not none, and choosing Duchy holds. In CG, the "Family template" row shows both offered templates as pressed/unpressed buttons and the picked one's description as a muted line directly under the row; picking the other swaps the line. With one template offered the row and the line do not render (unchanged behaviour, proved by the unit tests).
- Tested interactions: open `/admin/_upbringing_builder/7/` as a superuser contributor; read the Family paths fieldset; select Duchy and read it held (not saved: the reading is the page, the save is proved by the test below). Open `/characters/create` on a draft at the Lineage stage, "Taken In" on the name path with two templates; read the row and the description; click Fallen house and read its description. No page errors were raised.
- Fixture/live boundary: the Builder page is the real view, form, template and admin stylesheet over the real dev database; nothing was saved there. The CG page, the Lineage stage, the row and the bundle are real; every `/api/**` response is a fixture (the draft on the name path with `family_template_id` 30, the Upbringing with two templates carrying `description`, bare lists for the rest). The save of `max_claim_tier` through the Builder, the stock page remaining able to set it, and the picker's PATCH on pick are proved by `web.admin.tests.test_upbringing_builder` (64) and `LineageStage.test.tsx` (32), not by these captures.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| "Founders may claim up to" row under Family paths, between Claimable kinds and Family templates | present, admin fieldset markup | MATCH | docs/reviews/4202/01-builder-family-paths-1280.png |
| The row's help line | Highest seat tier a founder raised here may define (#3983); blank = any. | MATCH | docs/reviews/4202/01-builder-family-paths-1280.png |
| The select holds a chosen tier | Duchy | MATCH | docs/reviews/4202/02-builder-fieldset-duchy-1280.png |
| CG: the Family template row with both offered templates | Commoner family (pressed), Fallen house | MATCH | docs/reviews/4202/03-cg-name-path-picker-1280.png |
| CG: the picked template's description under the row | the Commoner family line | MATCH | docs/reviews/4202/03-cg-name-path-picker-1280.png |
| CG: picking the other template swaps the description | the Fallen house line | MATCH | docs/reviews/4202/04-cg-name-path-picked-second-1280.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-max-claim-tier-in-the-builder | PASS | the first two captures; `test_the_founder_tier_cap_is_on_the_page_and_saves` (renders, saves "duchy") | issue #4202, lightweight |
| R02-the-field-stays-a-claim-path-knob | PASS | the row sits in the Family paths fieldset beside `claimable_kinds` (`UPBRINGING_FIELDSETS`) | issue #4202 |
| R03-template-description-under-the-picker | PASS | the last two captures; `LineageStage.test.tsx` (the description reads under the row; PATCH on pick unchanged) | issue #4202 |
| R04-docs-in-tandem | PASS | `docs/systems/character_creation.md` (the `OriginTemplate` row), `docs/systems/family-authoring-recipes.md` (Recipe 1) | CLAUDE.md, docs are directives |

## Unresolved findings

- None
