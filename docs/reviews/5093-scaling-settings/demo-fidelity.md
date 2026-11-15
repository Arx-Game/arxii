# Review evidence

- Reviewed revision: 12aa0b1d72d2229bdf7d00e97d21858f112056f3
- Reviewer: demo-fidelity-reviewer (vision-capable agent; compared the rendered panel images against the demo source file)
- Reviewer verdict: PASS
- Application/build identity: Scaling settings panel, htmx fragment `src/web/templates/admin/tuning/_scaling_panel.html` built by `src/web/admin/tuning/scaling_settings.py`, served at /admin/_tuning/scaling/ and loaded into #panel-scaling on /admin/_tuning/, branch feature-5093-scaling-rules-read-aggregate-point-total at the reviewed revision, which now builds the strength and opposition rows and the worked example through the `level_strength` helper
- Environment: live Django server at http://127.0.0.1:8765 (stopped after the review; no other app server was running beforehand) on a scratch SQLite file database built from current models and seeded with the standard seeds (modifier value tables, check scale config, development cost config, level ladder, thread pull cost, resonance environment config, and the check-resolution seed that supplies the result charts), superuser session, headless Chromium through Playwright. Never arxiidev or production.
- Viewports/themes: 1280x900 light, 1280x900 dark (colorScheme dark), 390 wide light (phone)
- Approved design: https://claude.ai/artifact/1ZaA8sR3rXNK1d968fW79k (local source read in full: scaling-settings-demo.html in the session scratchpad). Owner rulings applied: no word "lane" on the panel, read-only with one edit link per row, columns are path-change levels 1, 3, 6, 11, 16, 21, 26, tier row shows the jump on reaching each level, the four other buff kinds render as four small tables, demo tab strip is decoration only.
- Changes since the previous PASS (199914e19): the panel's strength and opposition rows and its worked example now call `level_strength`, the rank label reads "Rank 17" instead of "Rank 17 (rank 17)", and migration 0411 was fixed. The panel prints no rank names, so the label fix is not visible on it; the other two changes were checked by comparing every number against the demo and the previous report.
- Visual review: Completed. Rendered panel compared with the demo section by section at the same theme and width, plus DOM and fragment checks for the word "lane", edit-link targets and panel order.
- Visual verdict: PASS
- Screenshots: ![Light 1280](docs/reviews/5093-scaling-settings/scaling-panel-light.png) ![Dark 1280, full panel](docs/reviews/5093-scaling-settings/review-scaling-dark-panel.png) ![Phone 390](docs/reviews/5093-scaling-settings/scaling-panel-phone.png)
- Comparison notes: Section order, section headings, column headings, row labels and the level columns match the demo. Every strength number (baseline 18, 34, 58, 98, 138, 178, 218; level term 9, 17, 53, 97, 141, 185, 229; opposition 18, 34, 82, 146, 210, 274, 338; width 8) is unchanged from the previous revision and equals the demo, so the `level_strength` switch changed no displayed value. The worked example reads exactly as the demo's: level 5 stands 1 rank above level 4; level 6 stands 4 ranks above level 5 with 1 rank for the level and 3 for the tier bonus of 24 points; level 11 is at the edge of the chart against level 5. That third sentence needs the standard check-resolution seed (result charts); in a first render before that seed ran, the build correctly printed "stands 12 ranks above ... 6 ranks for the level and 6 ranks for the tier bonus of 48 points" instead, and the screenshots cited here were all retaken after the seed. Wording differences, none a defect: the example says "3 ranks for the tier bonus" where the demo says "3 for the tier bonus" in its second sentence (the demo's own phrasing varies); the Tier rows value reads "level 3: +0 · level 6: +24 · ..." where the demo reads "3 · 0, then 6, 11, 16, 21, 26 · 24 each", because the build prints each live row; the Tier rows effect text says "A row at 0 changes nothing, so a jump at that level is one edit away" where the demo says "Level 3 has a row at 0, so a jump there is one edit away" (the build's sentence stays true if the level 3 row is edited, the demo's would not); the Large-buff sentence reads "A Large buff at 0.5 is half a rank" (live value); numbers print without a trailing ".0" ("1" for Paramount, "1 tenths per magnitude"). Pools and caps lists twelve rows where the demo showed six; the extra six (rescue budget, moon tuning, facet effect bonus, vow effect severity, duration and damage) are the pool and cap lanes in spec item 8 of #5093, so the demo's list was a subset. The four small buff tables put the "Size fractions" link in each caption rather than in a row Edit cell, which fits the owner ruling that they render as four tables. Phone width: the panel itself does not overflow (scroll width 358 equals client width 358) and each table sits in an overflow-x auto wrapper wider than the viewport (326 wide, 423 to 607 of content), so tables scroll sideways inside the panel. The whole dashboard page is wider than a 390 phone (scroll width 853) because of the page header buttons and the Checks panel table, neither part of the Scaling panel; that predates this change and is outside this review. The earlier committed scaling-panel-dark.png, an early capture cut off partway, is removed; review-scaling-dark-panel.png is the complete dark view.
- Tested interactions: Opened /admin/_tuning/ and waited for the htmx load of #panel-scaling in light and dark; read the panel top to bottom; resized to 390 wide and confirmed each table scrolls sideways inside its own wrapper as the demo's scroll wrapper does; listed the dashboard panels in order (checks, consequences, conditions, simulation, techniques, capabilities, scaling); read the panel's visible text (saved from the light render) and confirmed zero visible occurrences of "lane" (the only hits are lane__exact in link addresses) and no form, input, button or post; requested the Level tiers edit link and got HTTP 200; measured wrapper and panel scroll widths at 390 wide; stopped the server afterwards and confirmed port 8765 closed.
- Fixture/live boundary: Every value is read live from the scratch SQLite database, seeded with the standard seeds. The demo's values are placeholders and were not used as expected values. No production data was touched and nothing was written to the database.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Panel placement | One more section on /admin/_tuning/ after Capabilities, no tab strip | MATCH | Panel order list ends with panel-scaling; the tab strip was ruled decoration |
| Panel title | "Scaling settings" heading | MATCH | Top of scaling-panel-light.png |
| Lede | "Every number that sets how strong a level is. Each row links to the admin page that edits it." | MATCH | Same text under the title in all three shots |
| Section heading 1 | "How strong each level is on a roll" | MATCH | scaling-panel-light.png, first table heading |
| Strength table columns | "Path change at level", 1, 3, 6, 11, 16, 21, 26, "Edit" | MATCH | Header row of the first table in the light and dark shots |
| Strength row 1 | "Baseline (typical total)" with a "Level baselines" link | MATCH | First body row |
| Strength row 2 | "Tier bonus (the jump on reaching this level)" showing 0, +0, then +24 in bold, link "Level tiers" | MATCH | Second body row, +24 cells bold |
| Strength row 3 | "A character's level term (half the baseline, plus the tier bonus)", link "Check scale" | MATCH | Third body row |
| Strength row 4 | "An NPC's opposition (baseline plus tier bonus)" with "derived" in Edit | MATCH | Fourth body row |
| Strength row 5 | "One level's width (the size buffs are measured against)" with "derived" in Edit | MATCH | Fifth body row |
| Worked example box | Tinted box starting "How the rows play out:" with the level 5 (1 rank above level 4), level 6 (4 ranks: 1 for the level, 3 for the tier bonus of 24) and level 11 (at the edge of the chart) sentences | MATCH | Boxed paragraph under the first table in the light and dark shots, identical to the demo's three sentences once the result charts are seeded |
| Section heading 2 | "Settings" | MATCH | Second table heading |
| Settings columns | Setting, Value, What it changes in play, Edit | MATCH | Header row of the Settings table |
| Settings rows | Level share, Tier rows, Buff sizes on rolls, Value overrides, Development cost, Fatigue, Backfire difficulty, in that order, values in monospace, one edit link each | MATCH | Seven rows in demo order with Check scale, Level tiers, Size fractions, Modifier values, Development cost, Fatigue, Resonance environment links |
| Section heading 3 | "Development cost per step" | MATCH | Third table heading |
| Development cost table | "Value band" with bands 0 to 9 through 50 to 59; rows "Cost of one step" and "Gift thread step (x2)" | MATCH | Two body rows with six band columns |
| Section heading 4 | "Pools and caps" | MATCH | Fourth table heading |
| Pools columns | "Pool or cap", "Grows with", 1, 3, 6, 11, 16, 21, 26, "Edit" | MATCH | Header row of the Pools table |
| Pools rows from the demo | Anima pool, Fatigue level bonus (note "no rows yet, so it adds nothing" spanning the level columns), Soul tether scene cap, Hollow maximum, Outfit trickle, Techniques per gift, each with a "Level baselines" link | MATCH | First six rows of the Pools table; the extra six rows are covered by spec item 8 |
| Section heading 5 | "Buff sizes in points" | MATCH | Fifth heading |
| Buff sizes on rolls | "What the buff adds to" with Minor, Moderate, Large, Exceptional, Paramount, Edit; row "Rolls, at any level" 1, 2, 4, 6, 8 and "Size fractions" | MATCH | First buff table |
| Four other buff kinds | Stats, to-hit, damage and protection each as a small table at levels 1, 3, 6, 11, 16, 21, 26 with a size-fractions link | MATCH | Four captioned tables "At level" by five sizes |
| Word "lane" | Never appears | MATCH | Panel text contains zero visible occurrences |
| Read-only | No form controls, an edit link per row | MATCH | No form, input, button or post in the fragment; the Level tiers link returned 200 |
| Dark theme | Same layout in dark colours | MATCH | review-scaling-dark-panel.png |
| Phone width | Tables scroll sideways inside the panel, nothing overflows the page | MATCH | scaling-panel-phone.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
| --- | --- | --- | --- |
| screen-1-sections | PASS | All five demo sections plus the lede and example box appear in demo order | none needed |
| row-labels-and-columns | PASS | Row labels, column headings and the 1, 3, 6, 11, 16, 21, 26 columns match; tier row shows +0 and +24 | none needed |
| no-lane-word | PASS | Zero visible matches for lane in the panel text | none needed |
| read-only-with-edit-links | PASS | No form controls (count 0); every settings, pool, strength and buff row has an edit link or "derived" | none needed |
| copy-fidelity | PASS | Help lines match the demo except live-value wording noted in the comparison notes | none needed |
| unbuilt-demo-affordances | PASS | Demo tab strip is decoration per the owner; no other affordance is missing | none needed |
| styling-reaches-page | PASS | Rules sit in _panel_css.html, already included by the dashboard, and the screenshots show them applied (monospace values, bold jumps, tinted example box, scroll wrappers) | none needed |
| dark-and-phone | PASS | Dark and phone shots, retaken at this revision, show the same structure and no clipping | none needed |

## Unresolved findings

None
