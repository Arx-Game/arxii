# Review evidence

- Reviewed revision: `9527bd70464af596eb6ed10b5402365d053ada6a`
- Reviewer: `demo-fidelity-reviewer agent (two passes: cf8f9d8eb, then f0d2453ce after fixes D1 to D5); author checks by the implementer`
- Reviewer verdict: `PASS`
- Application/build identity: `Django dev server of this branch (feature-4513-trials-slice-2-the-trial-builder-admin-p) on 127.0.0.1:4731, scratch Postgres database rt_4513, page /admin/_trial_builder/1/`
- Environment: `Linux devcontainer, Chromium via Playwright, superuser session, Django runserver with the branch code against a throwaway Postgres database built by tools/build_schema.py; no shared server or database touched`
- Viewports/themes: `1400x1000, light and dark; the demo was rendered at the same viewport and themes`
- Approved design: `Demo of #4343, tab Trial builder (admin), local copy of the private artifact; spec #4343 section 6, The Trial builder page; issue #4513`
- Visual review: `Completed`
- Visual verdict: `PASS`
- Screenshots: ![Built, light, the demo trial saved](docs/reviews/4513/10-full-demo-trial-light-viewport.png) ![Built, dark](docs/reviews/4513/11-full-demo-trial-dark-viewport.png) ![Demo, light](docs/reviews/4513/demo-builder-light-viewport.png) ![Demo, dark](docs/reviews/4513/demo-builder-dark-viewport.png) ![Blocking: no cost](docs/reviews/4513/block-no-cost.png) ![Blocking: cosmetic scar only](docs/reviews/4513/block-cosmetic-only.png) ![Blocking: known below Success](docs/reviews/4513/block-known-below-success.png) ![Blocking: gating entry on a Failure](docs/reviews/4513/block-gating-on-failure.png) ![Save refused, no cost](docs/reviews/4513/save-refused-no-cost.png) ![Save refused, cosmetic only](docs/reviews/4513/save-refused-cosmetic-only.png) ![Save refused, known below Success](docs/reviews/4513/save-refused-known-below-success.png) ![Save refused, gating entry on Failure](docs/reviews/4513/save-refused-gating-on-failure.png)
- Comparison notes: `Every region of the demo builder tab is present in the same arrangement: the read-only Trial fieldset, What it opens, five tier fieldsets with route n of 5 chips and per-tier hidden controls (grant outright only at Critical Success, training absent on Failure and Critical Failure, reward absent below Success, deliberately-free row only where a row can open or train), the submit row, and the right rail (warnings, per tier, where it is taught, same entry made known elsewhere, credit). Stated differences, all judged acceptable by the reviewer: the check line reads base risk 35 (the model field is authored_base_risk) where the demo says difficulty 35; each tier has a consequence label and an entry-for-this-tier picker the demo implies but does not draw; the technique picker cannot hide ultimates (an ultimate is refused on save with slice 1's message); the Opens help under the codex entry fills after the entry is saved, and lists the technique's real prerequisites rather than the demo's fixed Path, techniques and skills wording (a deviation for the owner to accept). The first review found five defects (green refusal banner, slug in the option row, missing technique-cap line, uncoloured Critical Success header, inputs flush to the fieldset edge); all five were fixed and re-checked at the second revision.`
- Tested interactions: `Opened the empty page; picked the entry and technique with the autocompletes and typed a meter size; filled Critical Success, Success, Partial Success, Failure and Critical Failure as in the demo; watched the rail update after each edit; triggered each blocking warning (no cost, cosmetic scar as the only cost, known grant below Success, gating entry on a Failure) and pressed Save and continue, which refused with the slice 1 message under the tier and wrote nothing; saved the valid trial (Saved and credited to you), reloaded and read it back in light and dark; ran a page-built trial through mission resolve in the journey test.`
- Fixture/live boundary: `The page, rail, live check and save are the branch code against a scratch Postgres database; the trial data is typed in on the page using bracketed placeholders; the mission run is the real mission resolve command in src/integration_tests/test_trials_journeys.py with the roll pinned. Nothing reached a shared server or the shared arxiidev database.`
- Overall outcome: `PASS`

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Admin chrome and breadcrumb | Branding bar, breadcrumb Home, Mission options, the option, Trial builder, title Trial builder with the option | MATCH | 10-full-demo-trial-light-viewport.png |
| Refusal banner | Please correct the errors below, in the error style | MATCH | save-refused-cosmetic-only.png |
| Trial fieldset | Read-only chip; mission, node, option label, check line with an Edit option link | MATCH | 10-full-demo-trial-light-viewport.png |
| What it opens | Codex entry picker with the technique it opens, its prerequisites and the cap line; technique picker with its help; meter size with the Academy and teacher comparison | MATCH | 10-full-demo-trial-light-viewport.png |
| Tier fieldsets | Five, Critical Success to Critical Failure, route n of 5 chips, Critical Success header highlighted | MATCH | 10-full-demo-trial-light-viewport.png |
| Tier rows | Next node, label, outcome text, codex effect, training, cost, reward, deliberately free, with the per-tier hidden controls | MATCH | 10-full-demo-trial-light-viewport.png |
| Submit row | Delete trial routes at the left, Save and continue editing, Save | MATCH | 10-full-demo-trial-light-viewport.png |
| Rail warnings | Green all-clear line, informational notes, red Blocks save lines that update on change | MATCH | block-no-cost.png |
| Rail per tier, taught, elsewhere, credit | Summary lines per tier, Academy offer with its meter size, None for elsewhere, credit line | MATCH | 10-full-demo-trial-light-viewport.png |
| Save refused | Each blocking row refused with its message under its tier and nothing saved | MATCH | save-refused-no-cost.png |
| Dark theme | Same page readable under admin's dark variables | MATCH | 11-full-demo-trial-dark-viewport.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | The page builds the demo trial on one page and saves all five tiers in one transaction; src/web/admin/tests/test_trial_builder.py SavingATrialTests, and the saved page in 10-full-demo-trial-light-viewport.png | |
| A02 | PASS | A technique-opening row with no cost, a cosmetic-only cost, a known grant below Success and a gating entry on a Failure are each refused on save with slice 1's message and nothing is written; save-refused screenshots and RefusalTests | |
| A03 | PASS | No second copy of the rules: the page builds unsaved rows and calls ConsequenceEffect.clean and Consequence.trial_rule_errors; the live check returns the same text the save refuses with (TheRailTests.test_the_live_check_says_the_same_thing_the_save_does) | |
| A04 | PASS | The rail lists where the technique is taught with each offer's meter size, and the other consequences that make the entry known (TheRailTests, rail in the screenshots) | |
| A05 | PASS | forms.css and widgets.css are linked by the page and every class it emits has a rule that reaches it (StylingTests) | |
| A06 | PASS | Rows are credited to the operator's linked contributor; an unlinked operator sees the setup guidance and nothing is saved (SavingATrialTests) | |
| A07 | PASS | The page is linked from the mission option's change page and the builder's own index (ThePageTests) | |
| A08 | PASS | A trial saved on the page runs through the real mission resolve command: entry known, 15 of 40 meter, tier 2 scar (ATrialBuiltOnThePage in src/integration_tests/test_trials_journeys.py) | |

## Unresolved findings

- None
