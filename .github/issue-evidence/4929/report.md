# Review evidence

- Reviewed revision: 77fba1c675ab260a28e6192d88b9695fbf711059
- Reviewer: demo-fidelity-reviewer (Claude Sonnet 5.5), vision comparison of rendered app against rendered demo at the same viewport and theme
- Reviewer verdict: PASS
- Application/build identity: Arx II branch feature-4929-players-choose-vow-picks-every-pick-by-l at the reviewed revision, checked out as a throwaway detached worktree (git rev-parse confirmed the same sha); real React app served by Vite dev server on localhost port 3101; real Django/DRF/action stack run through the test runner. This is the second pass: the first pass at f01e9640b9256ecbe9f15e0325ffda1dacd1df8a found F1 and F2, fixed in this revision
- Environment: Linux devcontainer, PostgreSQL private test database test_arxii_dfr4929b (new name, one schema build with just build-test-schema, run with arx test --keepdb), Chromium via Playwright 1.58; worktree, Vite server and test database removed afterwards
- Viewports/themes: desktop 1280x900 and phone 390x844, each in dark and light (colorScheme emulation through next-themes)
- Approved design: Demo "Style and Vow Picks" (issue 4929 spec link https://claude.ai/artifact/XW1VAkFTajFhwGp2EvcXRt), local copy read in full and rendered here: screens 7, 8 and 10; rulings from the issue and plan (picks open only with the vow thread so a fresh joiner hears nothing; a sub-role holder sees one panel with a heading per vow and one budget line per level; Change picks is slice 7 and absent)
- Visual review: completed, screens 7, 8 and 10 compared element by element against the real VowPicksPanel on the real CharacterSheetPage Ties section, and the real ImbuePanel on the real ThreadDetailPage
- Visual verdict: PASS
- Screenshots: ![demo screen 8 light desktop](.github/issue-evidence/4929/demo-screen8-light-desktop.png) ![build sheet Ties light desktop](.github/issue-evidence/4929/sheet-ties-vow-picks-light-desktop.png) ![build sheet Ties dark desktop](.github/issue-evidence/4929/sheet-ties-vow-picks-dark-desktop.png) ![build sheet Ties dark phone](.github/issue-evidence/4929/sheet-ties-vow-picks-dark-phone.png) ![build sheet Ties light phone](.github/issue-evidence/4929/sheet-ties-vow-picks-light-phone.png) ![demo screen 7 dark desktop](.github/issue-evidence/4929/demo-screen7-dark-desktop.png) ![build imbue result dark desktop](.github/issue-evidence/4929/imbue-result-dark-desktop.png) ![build imbue result light phone](.github/issue-evidence/4929/imbue-result-light-phone.png) ![demo screen 10 dark desktop](.github/issue-evidence/4929/demo-screen10-dark-desktop.png)
- Comparison notes: see the Comparison notes section below; every in-scope element of screens 7, 8 and 10 matches, F1 and F2 from the first pass are closed
- Tested interactions: see the Tested interactions section below; web dispatch choices including an over-budget refusal, another account refused, sub-role holder catalog, imbue crossing and no crossing on web and telnet, telnet vow picks and vow pick, Choose button click in the browser, Choose picks link from the imbue result, joining
- Fixture/live boundary: see the Fixture and live boundary section below; backend payloads are real responses from the real stack on Postgres, browser pages are the real app with those recorded responses replayed, no live game server
- Overall outcome: PASS

## Fixture and live boundary

Live (real code, real Postgres test database, factories for rows, no mocks on the request path):
the catalog endpoint, the action dispatch endpoint, the telnet command handler, the ritual perform endpoint and the imbue finisher, the induction rite for joining. Every payload in `payloads/` was recorded at the reviewed revision from that stack. Rows were authored with factories to mirror the demo's Quicksilver example (names, prices, limits, budget 4 per level) and are example data, not the production catalog.

Replayed (fixture boundary): the browser pages. No game server was started (the shared devcontainer rules forbid arx start). The real, unmodified frontend at this revision was served by Vite and every `/api/` call was answered by Playwright route interception from the recorded real payloads (`payloads/*.json` and the sheet, roster, thread and account payloads recorded in the same run). So the DOM, CSS, React logic and the click paths are real; the server answers are recordings. Requests the sheet makes for unrelated panels (kin, relationships, titles and similar) were answered with an empty list, which is why those blocks read as empty. The Choose click is real; the dispatch answer it receives is the recorded real answer to choosing Read the Feint over HTTP, and the catalog re-read after it is the recorded real catalog after that choice. The imbue click is real; the finisher answer is the recorded real one for imbuing a vow thread from level 1 to 2 (and, for the within-level screenshot, from 20 to 25). The unrelated Pull Preview panel on the thread page was answered with a 404 and is not shown in any screenshot.

Incident, first pass: a second `build_schema.py` run against a new database exhausted shared memory and put the shared Postgres into crash recovery for several minutes (the known #4669 shape). It recovered by itself. This pass built exactly one new private schema, with a new name, and touched no existing database.

## Tested interactions

All through real interfaces, expected values taken from the issue, plan and rulings, not from the code. The catalog, dispatch and telnet vow picks payloads were re-recorded at this revision and compared with the first pass after normalising ids and timestamps: identical.

1. Catalog for a vow holder at vow level 2, level 3 locked: [payloads/01-catalog-level2-before-any-pick.json](payloads/01-catalog-level2-before-any-pick.json). Expected: levels 1 and 2 open with budget 4, level 3 not open with every pick saying "opens at vow level 3". Saw exactly that.
2. Choosing through the web dispatch endpoint, in order Strike from the Flank, Quick Recovery, Light on Your Feet (over budget), Hold the Line (level 3), Bleeding Cut, Quick Recovery again: [payloads/02-web-dispatch-choices.json](payloads/02-web-dispatch-choices.json). Saw "You take Strike from the Flank. Level 1: 2 of 4.", "You take Quick Recovery. Level 1: 4 of 4.", refusal "'Light on Your Feet' costs 4, and this character has already spent 4 of the 4 points for level 1 picks.", refusal "'Hold the Line' is a level 3 pick, and this character's vow is at level 2.", "You take Bleeding Cut. Level 2: 3 of 4.", refusal "You have already chosen Quick Recovery." Prices 2, 2, 3 follow max(1, value x frequency / 10 - reductions) with the authored limits.
3. Catalog after those picks (level 2 at 3 of 4, Read the Feint choosable, Through the Gap "costs more than is left"): [payloads/03-catalog-after-three-picks.json](payloads/03-catalog-after-three-picks.json). After the telnet pick: [payloads/08-catalog-after-telnet-pick.json](payloads/08-catalog-after-telnet-pick.json) (level 2 at 4 of 4, Read the Feint chosen).
4. Telnet vow picks, vow pick Read the Feint, vow pick Through the Gap, and three refusals (already chosen, no such pick, above level): [payloads/telnet-transcripts.json](payloads/telnet-transcripts.json) entries 04 to 07. Saw "You take Read the Feint. Level 2: 4 of 4." and "'Through the Gap' costs 4, and this character has already spent 4 of the 4 points for level 2 picks."
5. Another account: reading the catalog gives 404 ([payloads/09-other-account-reads-catalog.json](payloads/09-other-account-reads-catalog.json)); dispatching as the other character's sheet gives 403 ([payloads/10-other-account-dispatches-as-ysmay.json](payloads/10-other-account-dispatches-as-ysmay.json)); dispatching as itself naming her pick id gives "You hold no vow." ([payloads/11-other-account-dispatches-as-self-naming-her-pick.json](payloads/11-other-account-dispatches-as-self-naming-her-pick.json)); telnet gives "You hold no vow with focus picks." (transcripts entry 12). In the browser the other viewer's Ties section shows no vow picks block and made zero catalog requests: [sheet-ties-other-viewer-dark-desktop.png](sheet-ties-other-viewer-dark-desktop.png).
6. Sub-role holder at vow level 3: [payloads/21-subrole-catalog.json](payloads/21-subrole-catalog.json), web choices [payloads/20-subrole-web-choices.json](payloads/20-subrole-web-choices.json) (Riposte takes level 1 to 2 of 4, Strike from the Flank then 4 of 4: one budget shared across both vows), telnet entry 22. Catalog lists vows Quicksilver and Quicksilver Duelist, one budget line per level.
7. Imbue crossing through the web finisher (1 to 2): [payloads/30-web-imbue-crossing-1-to-2.json](payloads/30-web-imbue-crossing-1-to-2.json), message "You complete the rite, imbuing Quicksilver. Quicksilver is now level 2.\nVow level 2: 4 pts of new picks.", opened_pick_levels [2], new_picks one entry with level 2 and points 4. No crossing (20 to 25): [payloads/31-web-imbue-no-crossing-within-level-2.json](payloads/31-web-imbue-no-crossing-within-level-2.json), message "You complete the rite, imbuing Quicksilver.", no new-picks line, opened_pick_levels and new_picks empty. Telnet imbue: crossing 1 to 2 "Quicksilver is now level 2." then "Vow level 2: 4 pts of new picks." (transcripts entry 35), crossing 2 to 3 the same with level 3 (entry 33), no level change only the rite line (entry 32), past level 3 "Quicksilver is now level 4." and no picks line (entry 34), a non-vow thread "Moth Silk is now level 2." and no picks line (entry 36).
8. Joining: a joiner whose vow thread already stands at level 2 is told "Vow level 1: 4 pts of new picks." and "Vow level 2: 4 pts of new picks." (entry 41); a fresh joiner is told only "You have joined ritual session #1." (entry 40).
9. Browser: Choose click on Read the Feint then the line "You take Read the Feint. Level 2: 4 of 4." and the level 2 meter filling to 4 of 4: [sheet-ties-after-choose-dark-desktop.png](sheet-ties-after-choose-dark-desktop.png), payloads 71 and 72. Imbue click then result, with the page reporting the bold element text "4 pts" in all four viewport and theme combinations, then the Choose picks link, which landed on the Ties section at /characters/2?section=ties with the picks panel: [imbue-choose-picks-lands-on-ties-dark-desktop.png](imbue-choose-picks-lands-on-ties-dark-desktop.png). Within-level imbue result: [imbue-result-within-level-dark-desktop.png](imbue-result-within-level-dark-desktop.png), reading "You complete the rite, imbuing Quicksilver." and "Now level 2" with no picks band.

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| C1-catalog-by-level | PASS | Catalog lists every pick by level with budget, spent, left, chosen flag and locked reason (payloads/01, 03, 72) | none |
| C2-choose-within-budget | PASS | Web dispatch and telnet choose picks, unspent budget stays left, prices match the stated formula (payloads/02, transcripts 05) | none |
| C3-over-budget-refused | PASS | Refusal text quotes cost and spent for web and telnet (payloads/02, 73, transcripts 06) | none |
| C4-level-gate | PASS | Level 3 pick refused at vow level 2 and shown locked "opens at vow level 3" (payloads/01, 02) | none |
| C5-self-only | PASS | Another account gets 404 on the catalog, 403 dispatching as her sheet, "You hold no vow." as itself; the browser sends no catalog request for another viewer (payloads/09, 10, 11, other-viewer screenshot) | none |
| C6-sub-role-one-panel | PASS | One panel, a heading per vow, one budget line per level, budget shared across both vows (payloads/20, 21, sub-role screenshots) | none |
| C7-imbue-new-picks-line | PASS | Crossing 1 to 2 and 2 to 3 print the line on web and telnet; no crossing, past level 3 and a non-vow thread print none (payloads/30, 31, transcripts 32 to 36) | none |
| C8-joining-line | PASS | Rejoiner at level 2 told levels 1 and 2; fresh joiner told nothing (transcripts 40, 41) | none |
| C9-telnet-verbs | PASS | vow picks and vow pick text compared with screen 10 (transcripts 04 to 07) | none |
| C10-change-picks-absent | PASS | No Change picks control on the panel (all sheet screenshots) | none |
| C11-screen-8-fidelity | PASS | Every drawn element of screen 8 present in dark, light, desktop and phone (visual checklist) | none |
| C12-screen-7-fidelity | PASS | New-picks band with bold points, Choose picks link and "Quicksilver is now level 2." all match; the demo's leaf header belongs to the existing surface the demo labels today (comparison notes) | none |
| C13-result-levels-coherent | PASS | The level lines no longer disagree: "Quicksilver is now level 2." and "1 level gained, now level 2" for a 1 to 2 imbue; "Now level 2" within a level (imbue-result screenshots, payloads/30, 31) | none |

## Visual checklist

Screen 7 (Rite of Imbuing, a level opens new picks), compared with [demo-screen7-dark-desktop.png](demo-screen7-dark-desktop.png) and [demo-screen7-light-desktop.png](demo-screen7-light-desktop.png) against [imbue-result-dark-desktop.png](imbue-result-dark-desktop.png), [imbue-result-light-desktop.png](imbue-result-light-desktop.png), [imbue-result-dark-phone.png](imbue-result-dark-phone.png) and [imbue-result-light-phone.png](imbue-result-light-phone.png). Screen 8 (sheet Covenant block), compared with [demo-screen8-light-desktop.png](demo-screen8-light-desktop.png), [demo-screen8-dark-desktop.png](demo-screen8-dark-desktop.png), [demo-screen8-light-phone.png](demo-screen8-light-phone.png) and [demo-screen8-dark-phone.png](demo-screen8-dark-phone.png) against [sheet-ties-vow-picks-light-desktop.png](sheet-ties-vow-picks-light-desktop.png), [sheet-ties-vow-picks-dark-desktop.png](sheet-ties-vow-picks-dark-desktop.png), [sheet-ties-vow-picks-light-phone.png](sheet-ties-vow-picks-light-phone.png) and [sheet-ties-vow-picks-dark-phone.png](sheet-ties-vow-picks-dark-phone.png). Screen 10 (telnet), compared with [demo-screen10-dark-desktop.png](demo-screen10-dark-desktop.png) and [demo-screen10-light-desktop.png](demo-screen10-light-desktop.png) against [payloads/telnet-transcripts.json](payloads/telnet-transcripts.json).

| Element | Expected | Result | Evidence |
|---|---|---|---|
| S7 result line | "Quicksilver is now level 2." | MATCH | Build shows "You complete the rite, imbuing Quicksilver. Quicksilver is now level 2." with the demo's sentence word for word, imbue-result-dark-desktop.png |
| S7 new-picks line text | "Vow level 2: 4 pts of new picks" | MATCH | Build shows "Vow level 2: 4 pts of new picks" with no trailing full stop, same as the demo, imbue-result-light-desktop.png |
| S7 bold on "4 pts" | The number of points drawn bold | MATCH | "4 pts" is bold in the build in all four viewport and theme shots, imbue-result-dark-desktop.png and imbue-result-light-phone.png |
| S7 new-picks band | A band with a left accent rule holding the line on the left | MATCH | Build has a left accent rule, the line on the left, on its own row under the rite line, imbue-result-light-desktop.png |
| S7 Choose picks button | Outlined button at the right end of the band | MATCH | Build shows an outlined Choose picks button at the right end, wrapping under the line on phone, imbue-result-light-phone.png |
| S7 Choose picks destination | Leads to where picks are chosen (spec: the Covenant block on the sheet) | MATCH | The click landed on the Ties section with the picks panel, imbue-choose-picks-lands-on-ties-dark-desktop.png |
| S7 no crossing | No new-picks band when no pick level opens | MATCH | Within-level imbue shows the rite line and "Now level 2" only, imbue-result-within-level-dark-desktop.png |
| S8 header | "Quicksilver . vow picks" with tag "Vow level 2" | MATCH | Build heading "Quicksilver . vow picks" and tag "Vow level 2", the tag wraps under the heading in the narrow right column, sheet-ties-vow-picks-light-desktop.png |
| S8 level heads | "Level 1", "Level 2" with a four-square meter and "4 of 4" / "3 of 4" right-aligned | MATCH | Level 1 four filled squares "4 of 4"; level 2 three filled and one empty "3 of 4", sheet-ties-vow-picks-light-desktop.png |
| S8 chosen marker | Filled diamond on chosen picks, accent coloured | MATCH | Filled gold diamonds on Quick Recovery, Strike from the Flank, Bleeding Cut, same image |
| S8 unchosen marker | Hollow diamond | MATCH | Hollow diamonds on Feint and Vanish, Light on Your Feet, Read the Feint, Through the Gap, same image |
| S8 pick name and price | Small-caps name left, price right ("2 pts", "1 pt") | MATCH | "2 pts", "4 pts", "3 pts", "1 pt" right-aligned, singular for 1, same image |
| S8 description line | One plain sentence under the name | MATCH | Each pick shows its description, for example "Your cut lands harder on someone already busy with an ally." |
| S8 mechanics line | Effect summary then the limit line, ending "costs more than is left" where over budget | MATCH | "Damage +1 per thread level . Target limit: an ally is engaging them, met 6 times in 10"; "Cost limit: 1 anima per use, price less 1"; Through the Gap ends "costs more than is left" (effect wording is the app's own generated line, the demo's is example text) |
| S8 Choose button | Outlined Choose button, right-aligned, on Read the Feint only | MATCH | One Choose button on Read the Feint and none on any other row, sheet-ties-vow-picks-light-desktop.png |
| S8 level 3 | Heading "Level 3", "opens at vow level 3", picks dimmed and not choosable, no meter | MATCH | Three dimmed picks each saying "opens at vow level 3", no meter, no button, sheet-ties-vow-picks-dark-desktop.png |
| S8 note line | "Chosen picks change only through the Rite of Re-swearing." | MATCH | Present as the last line of the panel, same image |
| S8 Change picks button | Drawn in the demo, absent in this slice by ruling (slice 7) | MATCH | Absent, as the ruling requires, same image |
| S8 dark and phone | Same structure at 390 px and in dark | MATCH | Single column, meters and Choose buttons intact, sheet-ties-vow-picks-dark-phone.png and sheet-ties-vow-picks-light-phone.png |
| S8 sub-role panel | One panel, a heading per vow, one budget line per level (card "Sub-role holder at vow level 3") | MATCH | Vow headings Quicksilver and Quicksilver Duelist inside each level under one "4 of 4" line, sheet-ties-subrole-light-desktop.png and sheet-ties-subrole-dark-phone.png |
| S10 vow picks header | "Quicksilver, vow level 2." | MATCH | Build prints "Quicksilver, vow level 2." (04-telnet-vow-picks-raw) |
| S10 vow picks level line | "Level 2: 3 of 4." | MATCH | Build prints "Level 2: 3 of 4." on its own line, after Level 1 which the demo's abbreviated transcript leaves out (04-telnet-vow-picks-raw) |
| S10 vow pick result | "You take Read the Feint. Level 2: 4 of 4." | MATCH | Identical text (05-telnet-vow-pick-raw) |

## Comparison notes

Matches, screen by screen. Screen 8: the build reproduces the demo's panel in structure and in every drawn element except the Change picks button, which the ruling removes. The panel sits in the right column of the Ties section directly under the Covenant block, which is where the plan puts it; the demo draws the panel alone, so its placement is not contradicted. Screen 10: the pick line is word for word the demo's. Screen 7: the result sentence, the new-picks band with its bold points, and the Choose picks control are present and work end to end.

First-pass findings, now closed at this revision: F1 (the points were not bold) is fixed, the finisher now carries new_picks and the panel draws the points in a bold element beside Choose picks. F2 (the existing result line read "10 levels gained - now level 2") is fixed, the result now speaks in shown levels.

One element is not in the checklist table on purpose: the demo's leaf header "Rite of Imbuing" with the tag "Quicksilver thread". The demo's own annotation labels the imbuing surface and its result as existing today, and this slice's scope (issue spec) covers only the new-picks line. The real surface is the existing thread page, which carries the thread's name as the page heading and the panel titled "Imbue Thread"; this slice did not change that wording. It is a difference between the demo's drawing and the existing surface, not a defect of the diff, and is raised here for the maintainer as a scope question only.

Differences judged not to be defects, with reasons:
- Pick order inside a level is alphabetical by the server, while the demo draws chosen picks first. The demo's own order is not alphabetical or by price, so it reads as example layout, not a rule.
- At level 1, unchosen picks also say "costs more than is left" (budget spent), where the demo leaves level 1 bare. The demo shows that same reason on Through the Gap, so the build applies the demo's own rule consistently.
- Level 3 lists each real pick dimmed; the demo draws one placeholder row "Three example picks. Shown, not choosable." The spec says every pick is shown with why it is locked.
- The header tag wraps under the heading in the right column at desktop width; the demo has both on one row because it is drawn full width. Same elements, responsive wrap.
- The telnet list prints every level; the demo's transcript is abbreviated. Header and level text are identical.
- Effect wording is generated from the authored rows ("Damage +1 per thread level"); the demo's "+damage on your strikes" is example prose and no authored row produces it.

Not drawn in the demo and checked anyway: another viewer's sheet shows no picks block and sends no catalog request; a fresh joiner is told nothing about picks; a rejoiner at level 2 is told levels 1 and 2.

Unbuilt demo affordance: Change picks (slice 7, ruled out of scope in the issue).

Mechanical companion proposal: a test that renders the real VowPicksPanel and asserts the class hooks it emits (vowpicks-head, vowpicks-level, vowpicks-meter, vowpicks-entry, vowpicks-chosen, vowpicks-locked, vowpicks-vow, vowpicks-choose) each have a rule in the CSS the sheet page loads. The existing VowPicksPanel test already reads sheet.css from disk, so extending it to every emitted class is the cheap form. No class here lacks a rule: all of them are styled in the screenshots, and the page imports sheet.css itself.

## Unresolved findings

None
