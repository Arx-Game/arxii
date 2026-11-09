# Review evidence

Issue: #5026 (Weapons in combat: one weapon for melee and thrown, and enchantments that add their own damage type). Third review pass; the first two found F1 to F9, all now closed or judged below.

- Reviewed revision: 274680090a048b691ba5102d0a58c42a7c1dd1e2
- Reviewer: demo-fidelity-reviewer (vision-capable, compared each screenshot against the saved demo text and structure)
- Reviewer verdict: PASS
- Application/build identity: branch `feature-5026-weapons-in-combat-one-weapon-for-melee-a` at 274680090; web client built bundle driven by Playwright `frontend/e2e/thrown-strike-picker.spec.ts`; Django admin from the same branch on its own server and throwaway database
- Environment: local devcontainer; Strike picker against a mocked encounter payload (built bundle); round-roll card rendered from rows copied from a live server run on a throwaway database; admin served live from the branch; telnet transcript from the command handler through the journey test
- Viewports/themes: web client 1280x720 light theme (s02) and the narrow combat side-panel crop (s01, s03, s04); admin about 1280 wide, default admin theme (the Technique admin page is a long full-page capture)
- Approved design: demo https://claude.ai/artifact/H8QEAKXt9ZdTLt5f5NABCb (revision 5), read from the saved text-and-structure copy `/tmp/claude-1000/-workspaces-arxii/fc44b5ef-7a3b-4009-b7da-06a109d94293/scratchpad/demo-5026.html` (styles omitted; the original artifact page was not opened, so the demo's visual styling is not compared) and the spec in the #5026 issue body
- Visual review: completed for Screens 1 and 2, the dagger, armor, technique and thrown-share admin pages, and the telnet transcript (a text file, not an image)
- Visual verdict: PASS
- Screenshots: ![Strike picker with the target line, With and Enchant with rows](.github/issue-evidence/5026/s01-strike-picker.png) ![Strike picker on the game page](.github/issue-evidence/5026/s02-game-page.png) ![Soulfray accept box](.github/issue-evidence/5026/s03-soulfray-accept.png) ![Last Outcome card, three rows](.github/issue-evidence/5026/s04-round-rolls.png) ![Admin, two-handed throw refused](.github/issue-evidence/5026/thrown-strike-admin-two-handed-refused.png) ![Admin, coat protects against fire](.github/issue-evidence/5026/thrown-strike-admin-coat-protects-fire.png) ![Admin, Technique with Strike to-hit size](.github/issue-evidence/5026/thrown-strike-admin-technique.png) ![Admin, Strike thrown damage catalog row with its help](.github/issue-evidence/5026/thrown-strike-admin-thrown-share.png)
- Comparison notes: Compared with the prior pass at 7b257af0c, the diff to this revision touches only the Strike target line (`StrikeControl.tsx`, `YourTurn.tsx`) and the thrown-share help (`src/world/mechanics/admin.py`, `constants.py`). The target line now reads "Target: Bandit archer · 2 positions away" above the With row (s01, s02), the demo's Screen 1 line. The thrown-share row now carries the demo's help text verbatim in substance (admin screenshot). s04, s03, the telnet transcript and the dagger and armor admin pages are unchanged and were re-read. The remaining wording difference, "enchanted with Wreathe the blade" against the demo's "wreathed in flame", is judged an example-flavor difference and not a defect: the flavor belongs to the example technique, no authored field carries per-technique enchantment wording and the spec does not add one, and the build keeps the approved shape (names the enchantment, lists the parts, ends "back in your hand"). This is a reviewer judgment, not a human ruling; the implementer reports the demo's own header calls its content placeholders for shape, which my text-only copy of the demo does not contain (it carries "Example numbers only." under Screen 2), so that header is not verified by me.
- Tested interactions: Strike picker with the thrown chip and the Wreathe the blade chip selected and a target chosen (s01, s02); an overspending cast showing the soulfray accept box with the Strike button disabled until the box is ticked (s03); the Last Outcome card of an enchanted throw from a live server run (s04); admin save of a Greatsword with "Can also be thrown" refused; admin Salamander-hide coat with Fire ticked; admin Technique "Wreathe the blade" with "Strike to-hit size" Moderate and a Fire damage profile with "Uses equipped weapon" ticked; admin maneuver effect "Strike: thrown damage" base value 75; telnet line `strike Bandit archer with parrying dagger thrown using wreathe the blade` typed through the command handler
- Fixture/live boundary: s01, s02 and s03 are the built bundle against a MOCKED encounter payload (Playwright). s04 is the built Last Outcome card rendered from rows COPIED from a live server run, not a live render of the page. The admin screenshots are LIVE (own server, throwaway database). The telnet transcript `.github/issue-evidence/5026/telnet-transcript.txt` comes from the journey `ThrowingTheDagger.test_telnet_throws_and_enchants_with_words` (a real command handler on a test database). Live-run figures (anima 20 to 16, archer 200 to 188, dagger still equipped) are the implementer's; I did not re-run the server or the journeys.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| S1 Target line | "Target: Bandit archer · two positions away" above the With row | MATCH | s01-strike-picker.png and s02-game-page.png: "Target: Bandit archer · 2 positions away" above WITH (numeral instead of "two"; wraps in the narrow panel) |
| S1 With row: melee dagger chip | "Parrying dagger" with "one-handed melee · Melee Combat" | MATCH | s01-strike-picker.png, first chip |
| S1 With row: thrown dagger chip | "Parrying dagger, thrown" with "Thrown Combat · 75% damage", selected | MATCH | s01-strike-picker.png, second chip, selected (grey) |
| S1 With row: bare hands | "Bare hands" chip, "unarmed" | MATCH | s01: "bare hands unarmed · Unarmed Combat" (existing lowercase label, adds the skill name) |
| S1 Enchant with row | "Enchant with" heading under With, "No enchantment, a plain Strike", technique chip "Wreathe the blade, fire · 4 anima" selected (the demo's third chip "Shadow edge" is not in the fixture; chip format is proven by Wreathe the blade) | MATCH | s01-strike-picker.png, s02-game-page.png |
| S1 Strike button | Full-width "Strike" button below the rows | MATCH | s01, s02 |
| S1 soulfray accept box | Existing accept box on an overspending cast, nothing refused | MATCH | s03-soulfray-accept.png: "Soulfray Warning: Fraying ... Casting Wreathe the blade will cost 4 anima ... Accept the risk"; the Strike button is greyed until ticked, the existing gate's behavior and not a refusal |
| S2 narration | "...strikes Bandit archer. The dagger is back in your hand." | MATCH | telnet-transcript.txt last line: "You throw your Parrying dagger, enchanted with Wreathe the blade, at Bandit archer. A fair hit: 12 damage (5 physical, 7 fire). The Parrying dagger is back in your hand." Names the technique where the demo's example says "wreathed in flame" (judged example flavor, see notes) |
| S2 heading 1 | "Technique roll: Wreathe the blade" | MATCH | s04-round-rolls.png |
| S2 technique rows | "Fire Magic 3 (technique skill)" and "Anima 4 (paid for this attack, hit or miss)" | MATCH | s04: "Fire Magic 30 technique skill", "Anima 4 paid for this attack, hit or miss" |
| S2 technique result | "Good: +2 to hit, 4 fire", then the hit roll | MATCH | s04: "Success: +2 to hit, 4 fire", "then the hit roll" (outcome name is example data) |
| S2 heading 2 and rows | "Hit roll against Bandit archer's defense"; Thrown Combat (strike skill for thrown); Strength (stat for thrown); "Wreathe the blade +2 (from the technique roll)" | MATCH | s04: all four rows present |
| S2 hit result | "Hit, good", then the damage | MATCH | s04: "Hit, fair, then the damage roll" (example data) |
| S2 damage weapon row | "Parrying dagger, thrown" weapon part at the thrown share | MATCH | s04: "Parrying dagger, thrown, weapon damage and quality, at the thrown share" |
| S2 damage technique row | "Wreathe the blade, fire (technique part)" as its own row | MATCH | s04: "Wreathe the blade, fire, technique part" |
| S2 damage result | "10 damage: 3 physical, 7 fire" | MATCH | s04: "12 damage: 5 physical, 7 fire", fully in frame |
| S2 no armor or resistance values | The card never shows the archer's armor or resistance | MATCH | s04 shows none |
| S3 telnet command and reply | `strike archer with dagger thrown using wreathe the blade` replies "You ready a throw at Bandit archer with your parrying dagger, ..." | MATCH | telnet-transcript.txt: "You ready a throw at Bandit archer with your Parrying dagger, enchanted with Wreathe the blade." Command words and structure match; the closing phrase is example flavor |
| S4 what the round writes | Strike_thrown and the focused technique stored; anima, health and equipped dagger as stated | MATCH | Not a screen. Read in source, not rendered: the telnet journey asserts `strike_thrown` and `focused_action` (test file lines 268-270) and the enchanting journey asserts anima and health loss (lines 280-285); the live run reports the dagger still equipped |
| Admin dagger: "Can also be thrown" | Checkbox with staff help text; a two-handed save refused with "Only one-handed melee weapons can also be thrown." | MATCH | thrown-strike-admin-two-handed-refused.png: Greatsword, Two-Handed Melee, error banner and field error with that exact sentence |
| Admin armor: "Also protects against" | Damage-type checkboxes with "Armor always stops physical blows. Tick any other damage type its soak also stands against. Most armor ticks none." | MATCH | thrown-strike-admin-coat-protects-fire.png: Salamander-hide coat, Light Armor, Fire ticked, Fall unticked, help text present |
| Admin Technique: "Strike to-hit size" | Row after anima cost, with help text; damage profile inline with Uses equipped weapon | MATCH | thrown-strike-admin-technique.png: Anima cost 4, then "Strike to hit size: Moderate" with help text, damage profile Fire with "Uses equipped weapon" ticked (its help is the model field's help text, shown on the inline's column header as every inline field's help is) |
| Admin thrown share: row | Maneuver effects, "Strike: thrown damage", base value 75 | MATCH | thrown-strike-admin-thrown-share.png: Key "Strike: thrown damage", Kind "Damage share (percent)", Base value 75 |
| Admin thrown share: help text | "percent of the weapon's own damage a thrown attack deals. One number for every throwable weapon; 75 is a placeholder. A flat damage bonus never adds to this share." | MATCH | thrown-strike-admin-thrown-share.png: under Base value, "Percent of the weapon's own damage a thrown attack deals. One number for every throwable weapon; 75 is a placeholder. A flat damage bonus never adds to this share." |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| C1-two-chips | PASS | s01, s02: melee and thrown chips for one dagger, thrown shows "75% damage" | |
| C2-enchant-row | PASS | s01, s02: "Enchant with" row, "No enchantment", technique chip with anima cost | |
| C3-soulfray-box | PASS | s03: accept box on an overspending cast; the Strike button waits for the tick as the existing gate does | |
| C4-three-roll-rows | PASS | s04: technique, hit and damage cards in order, each with the demo's rows including the technique-skill row and the typed damage row | |
| C5-result-lines | PASS | s04: "Success: +2 to hit, 4 fire" and "12 damage: 5 physical, 7 fire", unclipped | |
| C6-telnet | PASS | telnet-transcript.txt shows the declare echo and the resolved line with "back in hand" | |
| C7-admin-dagger-armor-technique | PASS | the four admin screenshots; refusal text matches | |
| C8-target-line | PASS | s01, s02: "Target: Bandit archer · 2 positions away" above the With row | |
| C9-thrown-share-help-copy | PASS | thrown-strike-admin-thrown-share.png carries the approved help text under Base value | |
| C10-live-resolution | PASS | live run: anima 20 to 16, archer 200 to 188, dagger still equipped (figures reported by the implementer; not re-run in this review) | |

## Unresolved findings

None
