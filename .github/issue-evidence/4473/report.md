# Review evidence

- Reviewed revision: f4355dd9c7dcfeab9030196cca9d482808c6be44
- Reviewer: demo-fidelity-reviewer
- Reviewer verdict: PASS
- Application/build identity: branch feature-4473-organization-reputation-slice-2-deeds-na at f4355dd9c7dcfeab9030196cca9d482808c6be44, own dev server and scratch database, rendered in headed Chromium via Playwright
- Environment: Django admin plus React frontend, scratch database (not production)
- Viewports/themes: 1280px wide, light and dark
- Approved design: https://claude.ai/artifact/8JFD7YaJnocdf26LC38dYP (issue #4339 demo). The Artifact tool was not available to this reviewer, so the comparison used the saved copy at /tmp/claude-1000/-workspaces-arxii/0becb4bd-7ff9-4c65-97f3-936ed6f34cc2/scratchpad/designs/4339/demo.html (saved 2026-10-16), not a fresh fetch. Sections 4.1, 4.2, 4.4, 4.6, player Organizations card (slice 2 example) and GM Why column.
- Visual review: completed for 4.1, 4.2, 4.4, 4.6, player card and GM Why column; every cited screenshot was opened and compared with the demo
- Visual verdict: PASS
- Screenshots: ![award light](.github/issue-evidence/4473/award-light.png) ![award dark](.github/issue-evidence/4473/award-dark.png) ![effect light](.github/issue-evidence/4473/effect-light.png) ![effect dark](.github/issue-evidence/4473/effect-dark.png) ![carters light](.github/issue-evidence/4473/org-carters-light.png) ![carters dark](.github/issue-evidence/4473/org-carters-dark.png) ![millwrights light](.github/issue-evidence/4473/org-millwrights-light.png) ![millwrights dark](.github/issue-evidence/4473/org-millwrights-dark.png) ![magnitude light](.github/issue-evidence/4473/magnitude-light.png) ![magnitude dark](.github/issue-evidence/4473/magnitude-dark.png) ![gm light](.github/issue-evidence/4473/gm-light.png) ![gm dark](.github/issue-evidence/4473/gm-dark.png) ![sheet light](.github/issue-evidence/4473/sheet-c-light.png) ![sheet dark](.github/issue-evidence/4473/sheet-c-dark.png)
- Comparison notes: the four first-pass defects are fixed. Estimate text now shows principles with source and the demo's arithmetic; the helped row shows "(helped rows cannot)" and no checkbox; the GM Why shows the Moved by and Source lines; the Principle Overrides fieldset is expanded with society and Effective lines; the 4.6 list is rendered. Remaining differences are scope notes (no FAIL).
- Tested interactions: award and organization pages authored through the real admin forms (rows added in the browser, role set to helped, method override -4 set, saved, reloaded); mission resolved via missions.services.resolution.resolve_option; secret exposed via secrets.services.expose_secret; story consequence applied via mechanics.effect_handlers.apply_effect; sheet Ties tab and GM standoff panel opened; helped-row script read at src/web/templates/admin/societies/_helped_rows_cannot.html
- Fixture/live boundary: organizations, mission template, accounts and magnitude award rows are factory rows in a scratch database; the named organization rows, the relation and the override were authored through the admin forms; secret exposure called the service directly (gossip path covered by a journey test); the story consequence applied through apply_effect
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|----|--------|----------|---------------------|
| D4.1-layout | PASS | award-light.png, award-dark.png: Organizations this act names inline, columns Organization, Role, Only if exposed, Effective principles and estimate, Delete?, add link, approved footer help | none |
| D4.1-estimate-copy | PASS | award-light.png helped row: "method -4 (override; society: 0). Base +250. Adjustment: -3 x -4 = +12, x 3 = +36 (cap 125). Total +286: Unknown to Liked." matches the demo's form (numbers differ only because the scratch magnitude is High) | none |
| D4.1-helped-exposed | PASS | award-light.png and award-dark.png: helped row shows "(helped rows cannot)" and no checkbox; harmed row keeps a ticked box. Script _helped_rows_cannot.html hides the box, unticks it, and re-syncs on role change, formset:added and load | none |
| D4.2-layout | PASS | effect-light.png, effect-dark.png: Legend award fieldset, inline with Base amount and Only if exposed, footer help matches the demo | none |
| D4.4-principle-overrides | PASS | org-carters-light.png, org-carters-dark.png: Principle Overrides expanded, "Blank = use the society's value. Rt Society value: 0. Effective: 0." per field | none |
| D4.4-relations | PASS | org-carters-*.png "Reacts to changes with" (Millwrights, Rival, 50, help copy); org-millwrights-*.png read-only "Organizations that react to Millwrights" list with Carters, Rival, 50 and the one-directional help | none |
| D4.6-column | PASS | magnitude-light.png, magnitude-dark.png: "Named organization award" column with 50/120/250/400 | none |
| Player-card | PASS | sheet-c-light.png, sheet-c-dark.png: tier chips with reason lines, including "Favored, because Millwrights is now Disliked toward you" | none |
| GM-why | PASS | gm-light.png, gm-dark.png: "reputation: Carters holds you in high regard (Favored)", "Moved by: related organization, +125 (50% of Millwrights' -250, rival), Unknown to Favored", and a "Source: secret exposed (...) moved Millwrights by -250, Unknown to Disliked" line | none |

## Visual checklist

| Element | Expected | Result | Evidence |
|---------|----------|--------|----------|
| 4.1 Route, Magnitude help with example pay values, Archetypes help | Route help, "High currently pays: fame 100, prestige 50, named organization 250", archetype help naming organization principles | MATCH | award-light.png |
| 4.1 inline header and columns | Organization, Role, Only if exposed, Effective principles and estimate (read only), Delete? | MATCH | award-light.png |
| 4.1 helped row | Helped, "(helped rows cannot)", estimate text with override source and arithmetic | MATCH | award-light.png |
| 4.1 harmed row | Harmed, ticked Only if exposed, applied-only-if-exposed estimate | MATCH | award-light.png |
| 4.1 add link and footer help | add another organization; Harmed lowers... never flip the direction... Rivals and allies react on their own | MATCH | award-light.png |
| 4.1 dark theme | same layout and copy | MATCH | award-dark.png |
| 4.2 Legend award fieldset and inline | Legend base value, inline Organization/Role/Base amount/Only if exposed, footer help on tier multiplier and reach check | MATCH | effect-light.png, effect-dark.png |
| 4.4 Principle overrides | Per-principle override fields with society value and Effective lines | MATCH | org-carters-light.png, org-carters-dark.png |
| 4.4 Reacts to changes with | Other organization, Kind, Share (%), Delete?, one-step help | MATCH | org-carters-light.png |
| 4.4 Organizations that react (read only) | Organization, Kind, Share (%), one-directional help | MATCH | org-millwrights-light.png, org-millwrights-dark.png |
| 4.6 magnitude awards list | Magnitude, Fame, Prestige, Named organization award | MATCH | magnitude-light.png, magnitude-dark.png |
| Player Organizations card | org name, tier chip, reason line | MATCH | sheet-c-light.png, sheet-c-dark.png |
| GM Why column | Reputation line, Moved by with own amount and share, Source line | MATCH | gm-light.png, gm-dark.png |

## Unresolved findings

None

## Scope notes for the human

- N1: The GM Source line omits the demo's "(base 200 x 1.2 for a success)" parenthetical; the stored change does not keep the multiplier, and the line still names the cause, source organization, amount and tier move. Scope note, not a defect.
- N2: The GM Source line cites the secret ("secret #1, level 1: The truth of what happened...") where the demo cites a deed; the scratch scenario exposed a secret, so this reflects the data, not a divergence. The text is cut at the panel's right edge by the floating action button at 1280px in gm-light.png and gm-dark.png (the long summary wraps under it). Cosmetic.
- N3: The player card heading reads "Thought of as" where the demo renames it "Standing". That heading is slice 1 code, outside this diff.
- N4: The Carters page has no override set, so the "override differs from society" state of 4.4 (demo: Method override -4, Effective -4) is evidenced through the award page's estimate ("method -4 (override; society: 0)") and not on an Organization page. The Effective-line copy itself is shown.
- N5: Build shows six principle override fields; the demo shows three as examples. Harmless superset. 4.2 also adds an estimate column the demo omits.
- N6: The demo's player standoff card ("your angle") and 4.3 secret victims inline are not slice 2 surfaces and were not reviewed here.
- Proposed mechanical companion: a test that renders the Mission renown award change page and asserts the response contains the helped-rows script and the "(helped rows cannot)" string, and that the admin media for the inline includes forms.css-equivalent rules for the inline columns.
