# Review evidence: demo fidelity for #5125 Substances and Primum

- Reviewed revision: a5f03779acaddaefdbbcc5aeb220ebde3abb8517
- Reviewer: demo-fidelity-reviewer agent, final confirmation round after the F12 to F14 fixes (earlier rounds at 854d11faf and f42e9d68f)
- Reviewer verdict: PASS
- Application/build identity: branch feature-5125-substances-and-primum-what-a-gift-works at commit a5f03779a; the admin pages are the real ModelAdmin pages and the React surfaces are the real components (PrimumPanel, HarvestPanel, HarvestRow, SurroundingsLines, CraftingQuotePanel, ItemDetailPanel) at that commit
- Environment: local devcontainer, SQLite test tier; admin pages through the Django test client, React surfaces through a throwaway Vite 6.4.5 page on port 3461 (stopped by pid afterwards) and headless Chromium 1208; no production or dev database was touched
- Viewports/themes: 1280x900; admin in the light theme; React surfaces in both light and dark
- Approved design: https://claude.ai/artifact/3AVFkN2kC9i1qJVAhtYrhq (issue #5125 body, section Demo, five screens), read from the saved round-one copy and the reference renders demo-screen1.png to demo-screen5.png because the Artifact tool was not available to the reviewer
- Visual review: completed; every built screenshot was compared side by side with the matching demo render at the same viewport, across all five demo screens
- Visual verdict: PASS
- Screenshots: ![Substance admin page](docs/reviews/5125/admin-substance.png) ![Substance page after Add another relationship](docs/reviews/5125/admin-substance-add-another-clicked.png) ![Gift admin page](docs/reviews/5125/admin-gift.png) ![Item template harvesting](docs/reviews/5125/admin-itemtemplate-harvesting.png) ![Room panel pyromancer](docs/reviews/5125/fe-s2-room-pyromancer-light.png) ![Room panel after Magesight](docs/reviews/5125/fe-s2-room-magesight-light.png) ![Cast cards](docs/reviews/5125/fe-s3-cast-cards-light.png) ![Harvest panel](docs/reviews/5125/fe-s4-harvest-panel-light.png) ![Slain foe after harvest](docs/reviews/5125/fe-s4-foe-after-light.png) ![Crafting quote](docs/reviews/5125/fe-s5-crafting-quote-light.png) ![Item carries](docs/reviews/5125/fe-s5-item-carries-light.png) ![Demo screen 1](docs/reviews/5125/demo-screen1.png); the dark-theme captures and the remaining demo renders sit in the same folder
- Comparison notes: every round-one finding F1 to F11 is fixed or ruled, and F12 (script order on the Substance page), F13 (taper hint on the forge card) and F14 (article in the foe harvest sentence) are fixed and confirmed on the rendered pages; the per-element tables are under Detailed comparison
- Tested interactions: opened the Substance, Gift and Item template admin pages and pressed Add another relationship (4 rows became 5, no console error); room panel as a pyromancer, with no perception and after sightings; Harvest Primum from a place and from a slain elemental, pressing Harvest and reading the answer; four cast cards; the crafting quote for a required and an optional Primum with the box ticked; the crafted coat's item detail
- Fixture/live boundary: admin pages and all payloads are real server output from the branch's own factories and journeys; the React components are the real ones in a real store; the network hop for the dispatch POST was answered with the real captured harvest result, and the cast card shell, the combat list row and the facet dialog were not mounted (see the ledger rows marked OUT_OF_SCOPE)
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R1-report-identity | PASS | Report names the exact commit, environment, viewport and theme | n/a |
| R2-screenshots-committed | PASS | Screenshots are committed files under docs/reviews/5125 | n/a |
| R3-approved-design-reached | PASS | Read from the saved Artifact copy and the five demo renders; caveat: the live artifact was not reachable by this reviewer, so a later staff edit is not covered | n/a |
| R4-admin-css-reach | PASS | forms.css and widgets.css reach all three admin pages; the relationship table is styled | n/a |
| R5-admin-script-reach | PASS | F12 fixed: the served script list runs jquery.min.js, jquery.init.js, then inlines.js; the Add another relationship link renders and adds a row when pressed | n/a |
| R6-host-css-contract | PASS | Stock admin markup on the admin pages; the React surfaces use the shared Tailwind tokens | n/a |
| R7-rulings-applied | PASS | Divergences covered by rulings are listed under Detailed comparison, Rulings applied as non-defects | n/a |
| S1-substance-form | PASS | Screen 1 matches: substance page, relationship rows, Add another relationship, Gift Substance pick; F1, F2, F3 and F12 fixed | n/a |
| S2-place-panel | PASS | Screen 2 matches: pyromancer card, no-perception view, Magesight rows strongest first, leave-the-place line, telnet look; F4 and F5 fixed | n/a |
| S3-cast-cards | PASS | Screen 3 matches with one noted extra line from the approved call-up-to-Trace rule; F6, F7 and F13 resolved | n/a |
| S4-harvest | PASS | Screen 4 matches: place harvest and slain-foe harvest with check, AP and result lines; F8, F9 and F14 fixed | n/a |
| S5-crafting | PASS | Screen 5 matches: Primum material rows, check line and Carries fire line; F10 and F11 fixed | n/a |
| S3-cast-cancel-button | OUT_OF_SCOPE | Cancel and Cast buttons of the cast card were not rendered; the cast card shell is untouched by this diff | Out-of-scope boundary set by the controller for this round: elements that were not rendered are recorded here instead of in the visual checklist |
| S4-slain-foe-row | OUT_OF_SCOPE | The destroyed-elemental heading and Slain tag of the real combat list row were not mounted; the wrapper showed the name and Slain around the real HarvestRow | Out-of-scope boundary set by the controller for this round: elements that were not rendered are recorded here instead of in the visual checklist |
| S5-second-material-row | OUT_OF_SCOPE | The Wool cloth row was not drawn because the test recipe has no other material; the row layout is the same one | Out-of-scope boundary set by the controller for this round: elements that were not rendered are recorded here instead of in the visual checklist |
| S5-craft-attach-buttons | OUT_OF_SCOPE | Craft and Attach buttons are not part of the quote panel and were not rendered | Out-of-scope boundary set by the controller for this round: elements that were not rendered are recorded here instead of in the visual checklist |
| S5-facet-item-card | OUT_OF_SCOPE | A facet-attached silver ring was not captured; the same carries line renders on any item and was shown on the crafted coat | Out-of-scope boundary set by the controller for this round: elements that were not rendered are recorded here instead of in the visual checklist |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| 1.1 | Breadcrumb "Home > Magic > Substances > Fire", title "Change substance" | MATCH | Same element, trivial difference in wording or style. Title "Change substance" and object name "fire"; the breadcrumb is in the cropped-out header and is the stock admin one |
| 1.2 | Name field with help "What the cast card and the roll breakdown call it." | MATCH | Present, same help |
| 1.3 | "Which room condition feeds it" pick, "Heat", help "Picked from the room conditions the game already tracks." | MATCH | Same element, trivial difference in wording or style. Present, same label and help; the option reads "Heat exposure" (the existing room-condition label) |
| 1.4 | "Stronger when it is" pick, "Higher" | MATCH | Same element, trivial difference in wording or style. Present; the option reads "Higher (wetter, windier or hotter, e.g. water, wind or fire)" with a longer help paragraph |
| 1.5 | "Property added to every technique of this gift" with the long help line | MATCH | Present with the same label and help, as an autocomplete with add/change links |
| 1.6 | "Item created by harvesting" pick (value "Fire Primum") with help "The item template a harvest of this substance makes." on the substance page | MATCH | Now present on the substance page, same label and same help, with "Fire Primum" picked (`admin-substance.png`). Was F1 |
| 1.7 | "Relationships" table of rows: Other substance pick, Kind pick (Opposed/Related), Delete box | MATCH | Now a "RELATIONSHIPS" table with OTHER SUBSTANCE, KIND and DELETE? columns, one row per stored relationship (earth Related, ice Opposed, light Related) and a blank row. Was F2 |
| 1.8 | "add another" link under the table | MATCH | Present: "+ Add another relationship" under the table, and the blank row carries a remove icon. The served script list now runs `jquery.min.js`, then `jquery.init.js`, then `inlines.js`; the page throws nothing in the console, and pressing the link adds a fifth row (`admin-substance.png`, `admin-substance-add-another-clicked.png`). Was F12 |
| 1.9 | Help "Each relationship is authored once and shows on both substances. Relationships never chain: ..." | MATCH | Present under the table, word for word |
| 1.10 | Save button | MATCH | Same element, trivial difference in wording or style. Admin submit row: Save, Save as new, Save and continue editing, Delete |
| 1.11 | Gift form shows Name, Kind (Major), Substance (fire) | MATCH | All present within the existing Gift form; Substance is an autocomplete with "fire" picked |
| 1.12 | Gift Substance help "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts usually leave this blank." | MATCH | Matches through a controller ruling (see Rulings applied). Reads "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts have no substance." The last sentence differs by controller ruling (the form refuses a substance on a Minor Gift). Was F3 |
| 1.13 | Old per-Gift inline with seven fields gone | MATCH | No substance inline on the Gift page |
| 1.14 | Credit fields (Written by, Written on, Reviewed by, Reviewed on) not drawn in the demo | MATCH | Same element, trivial difference in wording or style. Drawn on the substance page (the standard credit block every authored model carries) |
| 2.1 | Pyromancer: card titled "You sense" with row "Fire Primum: Massive", no check needed | MATCH | Same element, trivial difference in wording or style. `fe-s2-room-pyromancer`: "YOU SENSE" heading with "Fire Primum: Massive" and a Harvest Primum button (allowed: a mage perceives her own substance) |
| 2.2 | Character with no perception sees only the room description | MATCH | `fe-s2-room-no-perception`: nothing rendered under the description |
| 2.3 | After Magesight: "Magesight / Good success" header row | MATCH | Matches through a controller ruling (see Rulings applied). Not in the room panel. By controller ruling this header is the cast result's own display |
| 2.4 | After Magesight: rows "Fire Primum: Massive" then "Earth Primum: Trace" (strongest first) | MATCH | `fe-s2-room-magesight`: Fire Massive then Earth Trace. Was F5 |
| 2.5 | "You see this until you leave the place." | MATCH | Present under the rows when any row came from a sighting, and absent for the pyromancer's own substance. Was F4 part 2 |
| 2.6 | Telnet `look` shows the same "You sense" line | MATCH | Real `look` after the sightings ends "You sense fire Primum: Massive. You sense earth Primum: Trace." (strongest first, one sentence per substance); the pyromancer's `look` ends "You sense fire Primum: Massive." |
| 3.1 | Forge card: heading "Fire around you", "The forge . Trace 1", "Ember-lined coat, worn . carries fire 2", "Fire adds +3 power" | MATCH | "FIRE AROUND YOU", "The Long Hall . Trace 2", "Ember-lined coat, worn . carries fire 2", "Fire adds +4 power". Same structure and wording; the numbers differ because the demo's are examples |
| 3.2 | Caldera card: "The Ashmouth Caldera . Massive 8", coat 2, "Fire adds +7 power" | MATCH | "The Long Hall . Massive 10", coat 2, "Fire adds +8 power" |
| 3.3 | Caldera hint "The more fire around you, the less each extra source adds." | MATCH | Present on the caldera card, same words, muted style (10 and 2 points, 12 become +8, so the curve tapers). Was F6 part 1 |
| 3.4 | Forge card has no hint | MATCH | No hint on the forge card: the place (2 points) and the coat (2 points) total 4 points, which the curve turns into +4 power, so nothing tapers (`fe-s3-cast-cards-light.png`, "Forge"). Was F13 |
| 3.5 | Unperceived card: heading "Around you", one line "Something here works against your ice -6 power" | MATCH | Same element, trivial difference in wording or style. "ICE AROUND YOU" with "Calls up ice, free, your control covers it", Trace 2, "Something here works against your ice -10", total "Around you adds -6 power". The foreign substance is not named. The extra lines come from the spec's recorded call that a cast calls her own substance up to Trace; the card has no hint |
| 3.6 | Cistern card: "The flooded cistern . Rich water, related to ice 3", "Related substances add +3 power" | MATCH | Same element, trivial difference in wording or style. Trace 2, "The Long Hall . Rich water, related to ice 3", total "Around you adds +4 power". Source wording matches; the total label differs because her own Trace source is also present |
| 3.7 | Cistern hint "You can draw strength for your ice from the water here. You cannot move the water." | MATCH | Same element, trivial difference in wording or style. Present, same words. The taper hint also shows above it, because the cistern card here has two sources (her own substance called up to Trace, 2, and the water, 3; 5 points become +4), so the curve really does reduce the total. The demo's cistern card has the water as its only source (no taper, no hint), so the difference follows from the ruled call-up-to-Trace line (row 3.5), not from the hint rule. Was F6 part 2 |
| 3.8 | Heading in small caps, power lines coloured, amounts right-aligned | MATCH | Same: caps heading, right-aligned monospace amounts, green positive power, amber negative |
| 4.1 | Title "Harvest Primum", label "Draw out" | MATCH | Both present (`fe-s4-harvest-panel`) |
| 4.2 | Pick of "Fire Primum . Massive" and "Earth Primum . Trace" as chips | MATCH | Same element, trivial difference in wording or style. Same labels as radio buttons with the first selected, not chips |
| 4.3 | Check line "Check: Wits + Harvesting" | MATCH | Same element, trivial difference in wording or style. "Check: Harvest Primum" (the authored check type's name) |
| 4.4 | AP cost line (ruling) | MATCH | "Costs 2 AP" |
| 4.5 | Cancel and Harvest buttons | MATCH | Both present, Harvest primary |
| 4.6 | Result "Good success. You draw out 2 Fire Primum (Fine)." | MATCH | "Success. You draw out 2 Fire Primum (Fine)." (the tier name follows the forced outcome) |
| 4.7 | Result second line "The caldera now holds a Rich amount of fire Primum. It refills over many weeks." | MATCH | Same element, trivial difference in wording or style. "The Ashmouth Caldera now holds a Rich amount of fire Primum. It refills slowly." (`fe-s4-harvest-panel-result`). Names the place and says whether and how it refills; "slowly" for "over many weeks" is a wording difference. Was F8 |
| 4.9 | "You sense fire Primum in its remains." | MATCH | Present, exact text (`fe-s4-foe-before`) |
| 4.10 | Check line "Check: Wits + Harvesting . +2 from your thread on Pyromancy" | MATCH | Same element, trivial difference in wording or style. "Check: Harvest Primum . +10 from your thread on Pyromancy" for the pyromancer with a level-200 thread; the figure is the real bonus. Was F9 |
| 4.11 | Harvest button, then "Success. You draw out 1 Fire Primum (Common)." and "Nothing more can be drawn from the elemental." | MATCH | Harvest button, "Success. You draw out 2 Fire Primum (Fine)." and "Nothing more can be drawn from the elemental." (`fe-s4-foe-after-light.png`, `-dark.png`); the article is there and the sentence is word for word the demo's. The quantity and quality follow this round's authored outcome row. Was F14 |
| 4.12 | Telnet `extract fire` and `extract fire from elemental` | MATCH | Same element, trivial difference in wording or style. Bare `extract` now prints "You can extract fire Primum (Rich) here." then "Check: Harvest Primum . +10 from your thread on Pyromancy" then "Each attempt costs 2 AP, whatever you roll."; the place answer over telnet ends with the same place line as the web. The foe line over telnet was not re-captured |
| 5.1 | Coat recipe lists "Fire Primum . 1, Common or better have 3" | MATCH | `fe-s5-crafting-quote`: "Fire Primum . 1, Common or better" with "have 3" at the right (red when short). Was F10 |
| 5.2 | Facet recipe "Fire Primum . 1 (optional) have 2" | MATCH | Same element, trivial difference in wording or style. `fe-s5-crafting-quote-optional` and `-ticked`: a tick box, "Fire Primum . 1 (optional)", "have 3" at the right; the facet dialog itself was not mounted |
| 5.3 | "Check: Dexterity + Tailoring" line | MATCH | Same element, trivial difference in wording or style. "Check: Enchanting" (the recipe's check type name). The panel keeps its existing "Skill cap" and "On failure" lines. Was F11 |
| 5.6 | Result card "Ember-lined coat . Fine / Carries fire" | MATCH | `fe-s5-item-carries`: item detail panel with "Carries fire" under the stats, shown to another character from `carries: ["fire"]` (quality reads Common in this data) |

## Unresolved findings

## Detailed comparison

The sections below keep the earlier per-screen detail, round history and notes. Their wording was left as written; the status words there (MATCH-NOTE, N/R) are folded into the Visual checklist above as MATCH with the note in the Evidence column, and the N/R rows are the OUT_OF_SCOPE ledger rows.

### Header

| Item | Value |
|---|---|
| Reviewed commit | `a5f03779acaddaefdbbcc5aeb220ebde3abb8517` (`a5f03779a`, branch `feature-5125-substances-and-primum-what-a-gift-works`). Earlier rounds: `854d11faf` (round one), `f42e9d68f` (re-review, which left F12, F13 and F14). Commit `a5f03779a` changes only `SubstanceAdmin.Media`, the taper-hint rule, the harvest `remaining_line` and tests/doc. |
| Approved design | https://claude.ai/artifact/3AVFkN2kC9i1qJVAhtYrhq (issue #5125 body, "Demo (approved reference once this spec is approved)"), five screens |
| How the design was read | The `Artifact` tool is not available to this reviewer, so the demo was read again from the saved copy used in round one (`scratchpad/rv/demo.html`, the coordinator's `Artifact read` output) and the five reference renders `demo-screen1.png` to `demo-screen5.png`, which were re-opened side by side with every new screenshot. If staff edited the artifact after that read, this review does not cover the edit. |
| Reference screenshots | `demo-screen1.png` to `demo-screen5.png` (the demo HTML rendered at 1280x900) |
| Environment | Local devcontainer, SQLite test tier. Admin pages through the Django test client; React surfaces through a throwaway Vite 6.4.5 page on port 3461 (stopped by pid afterwards, no `just stop`) and headless Chromium 1208. No production or dev database was touched. All throwaway files (one test module, the Vite page and its copied payloads) were deleted before the commit; this round re-rendered only the three affected screens, and the room-panel, harvest-panel, crafting, Gift and Item template screenshots are unchanged from the `f42e9d68f` round because `a5f03779a` does not touch what they render. |
| Viewport and theme | 1280x900. Admin: light theme. React surfaces: both light and dark (`-light.png` and `-dark.png`). |
| Rulings applied as non-defects | Owner rulings from round one: removed fields and relabels, telnet verb `extract`, "Costs N AP", a living creature's Primum does not feed a cast, "Something here strengthens your <own>". Controller rulings for this round: the Gift form's last help sentence reads "Minor Gifts have no substance." because the form refuses a substance on a Minor Gift; the "Magesight / Good success" header is the cast result's own display, not the room panel; the unperceived-card extra lines are the spec's approved call-up-to-Trace. |

### Fixture versus live boundary

- **Live, real code:** admin pages are the real `ModelAdmin` pages rendered through the Django test client against rows built with the branch's factories (fire with three stored relationships and a harvest item, a Pyromancy Gift with fire picked). The HTML was saved with every linked admin stylesheet and script resolved from disk, including `forms.css` and the `widgets.css` it imports, then screenshotted with the sidebar hidden. The page is the exact server output, so the script order it contains is the order a browser would run.
- **Payloads are real server output.** The JSON the three re-rendered screens consume was produced again this round by a throwaway test module whose classes subclass the branch's own `_FireField`, `_IceField` and `AfterAHarvest` journeys (run on the SQLite tier with `arx test --sqlite`): the four `cast_preview.surroundings` cards (forge and caldera with a worn Ember-lined coat built from item-substance rows and equipped, ice at the caldera not perceiving fire, ice at a cistern after a sighting of water), the combat opponent `harvest_offers` for a slain elemental (with the +10 thread bonus), and the `harvest_primum` dispatch result for that slain foe, serialised with the real `DispatchResultSerializer`. The Substance change page was fetched through the Django test client as a superuser. Payloads for the unchanged screens are the round-two captures.
- **React components are the real ones** (`PrimumPanel`, `HarvestPanel` through it, `HarvestRow`, `SurroundingsLines`, `CraftingQuotePanel`, `ItemDetailPanel`) mounted in the real Redux store and a react-query client.
- **Fixture boundary:** `window.fetch` in the harness answered the dispatch POST with the real `harvest_primum` result captured above (a mock for the network hop) and returned empty lists for unrelated item-panel queries. The cast cards show only the surroundings lines (`SurroundingsLines`) inside a plain bordered box, not the cast card shell, so the demo's Cancel and Cast buttons were not rendered. The slain-foe row is a minimal wrapper (name and "Slain") around the real `HarvestRow`; the real combat list row was not mounted. The four cards sit in a two-by-two grid with a muted caption (Forge, Caldera, Unperceived, Cistern) added by the harness. The substance page in this round's data has no Property picked, which is a data choice of the harness, not a build change. `AttachFacetDialog` was not mounted; the facet quote shares `CraftingQuotePanel`, which was. The harvest check line shows "Check: Harvest Primum" because that is the authored check type's name in the test data.
- **Not rendered:** the Primum step, power curve and harvest outcome inlines on the config admin, the Place Primum and Creature Primum inlines, and telnet output other than what the payload dumps captured (see Findings).

### Screenshots

Admin (light, 1280 wide): `admin-substance.png` (re-rendered at `a5f03779a`, shows "Add another relationship"), `admin-substance-add-another-clicked.png` (the same page after pressing the link, a fifth row has appeared), `admin-gift.png`, `admin-itemtemplate-harvesting.png`, `admin-itemtemplate.png` (both item template shots unchanged since round one, byte identical, so the page did not change).
React, each in `-light` and `-dark` (re-rendered at `a5f03779a`: `fe-s3-cast-cards`, `fe-s4-foe-before`, `fe-s4-foe-after`; the rest unchanged since `f42e9d68f`): `fe-s2-room-pyromancer`, `fe-s2-room-no-perception`, `fe-s2-room-magesight`, `fe-s3-cast-cards` (four cards on one page), `fe-s4-harvest-panel`, `fe-s4-harvest-panel-result`, `fe-s4-foe-before`, `fe-s4-foe-after`, `fe-s5-crafting-quote` (the required Common-or-better row), `fe-s5-crafting-quote-optional` (the optional row), `fe-s5-crafting-quote-ticked`, `fe-s5-item-carries`.

### Interactions exercised

- Opened the Substance change page for fire with three stored relationships and a harvest item set, and the Gift change page for Pyromancy with fire picked; loaded the substance page in headless Chromium with the console open (no errors), counted the "Add another relationship" link (one), pressed it and counted the relationship rows (4 before, 5 after).
- Opened the Item template page for Fire Primum and expanded its Harvesting fieldset.
- Room panel as a pyromancer with a thread on her Gift, as a character with no perception, and as a harvester after sightings of fire and earth.
- Clicked Harvest Primum on the room panel, saw the pick, check line, AP line, Cancel and Harvest, pressed Harvest and read the answer.
- On a slain elemental viewed by the pyromancer: saw the sense line, check line with the thread bonus, AP line and Harvest button, pressed Harvest and read the answer (now "the elemental").
- Cast cards for a fire mage at a forge with a worn coat, at a caldera with the coat, an ice mage at the caldera not perceiving fire, and an ice mage at a cistern after a sighting.
- Crafting quote for a recipe requiring Fire Primum, Common or better, and for one taking it optionally (ticked the box); item detail of the crafted coat as another character sees it.

### Screen-by-screen tables

Built column is at `a5f03779a`. Legend: MATCH (compared on screen against the demo image at the same viewport), MATCH-NOTE (same element, wording or style differs trivially), GAP (element absent or different, a finding below), N/R (not rendered, see boundary).

#### Screen 1 - Admin: one substance, its relationships, the Gift that works it (`demo-screen1.png` vs `admin-substance.png`, `admin-gift.png`, `admin-itemtemplate-harvesting.png`)

| # | Demo element | Built (at `a5f03779a`) | Status |
|---|---|---|---|
| 1.1 | Breadcrumb "Home > Magic > Substances > Fire", title "Change substance" | Title "Change substance" and object name "fire"; the breadcrumb is in the cropped-out header and is the stock admin one | MATCH-NOTE |
| 1.2 | Name field with help "What the cast card and the roll breakdown call it." | Present, same help | MATCH |
| 1.3 | "Which room condition feeds it" pick, "Heat", help "Picked from the room conditions the game already tracks." | Present, same label and help; the option reads "Heat exposure" (the existing room-condition label) | MATCH-NOTE |
| 1.4 | "Stronger when it is" pick, "Higher" | Present; the option reads "Higher (wetter, windier or hotter, e.g. water, wind or fire)" with a longer help paragraph | MATCH-NOTE |
| 1.5 | "Property added to every technique of this gift" with the long help line | Present with the same label and help, as an autocomplete with add/change links | MATCH |
| 1.6 | "Item created by harvesting" pick (value "Fire Primum") with help "The item template a harvest of this substance makes." on the substance page | Now present on the substance page, same label and same help, with "Fire Primum" picked (`admin-substance.png`). Was F1 | MATCH |
| 1.7 | "Relationships" table of rows: Other substance pick, Kind pick (Opposed/Related), Delete box | Now a "RELATIONSHIPS" table with OTHER SUBSTANCE, KIND and DELETE? columns, one row per stored relationship (earth Related, ice Opposed, light Related) and a blank row. Was F2 | MATCH |
| 1.8 | "add another" link under the table | Present: "+ Add another relationship" under the table, and the blank row carries a remove icon. The served script list now runs `jquery.min.js`, then `jquery.init.js`, then `inlines.js`; the page throws nothing in the console, and pressing the link adds a fifth row (`admin-substance.png`, `admin-substance-add-another-clicked.png`). Was F12 | MATCH |
| 1.9 | Help "Each relationship is authored once and shows on both substances. Relationships never chain: ..." | Present under the table, word for word | MATCH |
| 1.10 | Save button | Admin submit row: Save, Save as new, Save and continue editing, Delete | MATCH-NOTE |
| 1.11 | Gift form shows Name, Kind (Major), Substance (fire) | All present within the existing Gift form; Substance is an autocomplete with "fire" picked | MATCH |
| 1.12 | Gift Substance help "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts usually leave this blank." | Reads "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts have no substance." The last sentence differs by controller ruling (the form refuses a substance on a Minor Gift). Was F3 | MATCH (ruling) |
| 1.13 | Old per-Gift inline with seven fields gone | No substance inline on the Gift page | MATCH |
| 1.14 | Credit fields (Written by, Written on, Reviewed by, Reviewed on) not drawn in the demo | Drawn on the substance page (the standard credit block every authored model carries) | MATCH-NOTE |

CSS reach (finding class 1): the substance, Gift and Item template pages link `base.css`, `forms.css` (which imports `widgets.css`), `autocomplete.css`, `arx_admin.css`, `nav_sidebar.css` and `responsive.css` and render as styled admin pages. The new relationship table uses the stock tabular inline markup (`.tabular.inline-related`, `.inline-heading`) that `forms.css` and `base.css` style, and it is drawn correctly. The script reach is now correct too: `SubstanceAdmin.Media` (`src/world/magic/admin.py`) lists the jQuery file, `jquery.init.js` and `inlines.js` in Django's own order, and the rendered page's script list has them in that order. The existing test still asserts only that `admin/js/inlines.js` is on the page, not its position; see the proposed companion below.

#### Screen 2 - A place: who perceives the Primum it holds (`demo-screen2.png` vs `fe-s2-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 2.1 | Pyromancer: card titled "You sense" with row "Fire Primum: Massive", no check needed | `fe-s2-room-pyromancer`: "YOU SENSE" heading with "Fire Primum: Massive" and a Harvest Primum button (allowed: a mage perceives her own substance) | MATCH-NOTE |
| 2.2 | Character with no perception sees only the room description | `fe-s2-room-no-perception`: nothing rendered under the description | MATCH |
| 2.3 | After Magesight: "Magesight / Good success" header row | Not in the room panel. By controller ruling this header is the cast result's own display | MATCH (ruling). Was F4 part 1 |
| 2.4 | After Magesight: rows "Fire Primum: Massive" then "Earth Primum: Trace" (strongest first) | `fe-s2-room-magesight`: Fire Massive then Earth Trace. Was F5 | MATCH |
| 2.5 | "You see this until you leave the place." | Present under the rows when any row came from a sighting, and absent for the pyromancer's own substance. Was F4 part 2 | MATCH |
| 2.6 | Telnet `look` shows the same "You sense" line | Real `look` after the sightings ends "You sense fire Primum: Massive. You sense earth Primum: Trace." (strongest first, one sentence per substance); the pyromancer's `look` ends "You sense fire Primum: Massive." | MATCH |

#### Screen 3 - Casting: one bonus from everything around them (`demo-screen3.png` vs `fe-s3-cast-cards-*.png`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 3.1 | Forge card: heading "Fire around you", "The forge . Trace 1", "Ember-lined coat, worn . carries fire 2", "Fire adds +3 power" | "FIRE AROUND YOU", "The Long Hall . Trace 2", "Ember-lined coat, worn . carries fire 2", "Fire adds +4 power". Same structure and wording; the numbers differ because the demo's are examples | MATCH |
| 3.2 | Caldera card: "The Ashmouth Caldera . Massive 8", coat 2, "Fire adds +7 power" | "The Long Hall . Massive 10", coat 2, "Fire adds +8 power" | MATCH |
| 3.3 | Caldera hint "The more fire around you, the less each extra source adds." | Present on the caldera card, same words, muted style (10 and 2 points, 12 become +8, so the curve tapers). Was F6 part 1 | MATCH |
| 3.4 | Forge card has no hint | No hint on the forge card: the place (2 points) and the coat (2 points) total 4 points, which the curve turns into +4 power, so nothing tapers (`fe-s3-cast-cards-light.png`, "Forge"). Was F13 | MATCH |
| 3.5 | Unperceived card: heading "Around you", one line "Something here works against your ice -6 power" | "ICE AROUND YOU" with "Calls up ice, free, your control covers it", Trace 2, "Something here works against your ice -10", total "Around you adds -6 power". The foreign substance is not named. The extra lines come from the spec's recorded call that a cast calls her own substance up to Trace; the card has no hint | MATCH-NOTE (F7 scope note) |
| 3.6 | Cistern card: "The flooded cistern . Rich water, related to ice 3", "Related substances add +3 power" | Trace 2, "The Long Hall . Rich water, related to ice 3", total "Around you adds +4 power". Source wording matches; the total label differs because her own Trace source is also present | MATCH-NOTE (F7) |
| 3.7 | Cistern hint "You can draw strength for your ice from the water here. You cannot move the water." | Present, same words. The taper hint also shows above it, because the cistern card here has two sources (her own substance called up to Trace, 2, and the water, 3; 5 points become +4), so the curve really does reduce the total. The demo's cistern card has the water as its only source (no taper, no hint), so the difference follows from the ruled call-up-to-Trace line (row 3.5), not from the hint rule. Was F6 part 2 | MATCH-NOTE |
| 3.8 | Heading in small caps, power lines coloured, amounts right-aligned | Same: caps heading, right-aligned monospace amounts, green positive power, amber negative | MATCH |
| 3.9 | Cancel and Cast buttons | Not rendered (the cast card shell is untouched by this diff) | N/R |

#### Screen 4 - Harvesting: from a place, and from a slain creature (`demo-screen4.png` vs `fe-s4-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 4.1 | Title "Harvest Primum", label "Draw out" | Both present (`fe-s4-harvest-panel`) | MATCH |
| 4.2 | Pick of "Fire Primum . Massive" and "Earth Primum . Trace" as chips | Same labels as radio buttons with the first selected, not chips | MATCH-NOTE |
| 4.3 | Check line "Check: Wits + Harvesting" | "Check: Harvest Primum" (the authored check type's name) | MATCH-NOTE |
| 4.4 | AP cost line (ruling) | "Costs 2 AP" | MATCH |
| 4.5 | Cancel and Harvest buttons | Both present, Harvest primary | MATCH |
| 4.6 | Result "Good success. You draw out 2 Fire Primum (Fine)." | "Success. You draw out 2 Fire Primum (Fine)." (the tier name follows the forced outcome) | MATCH |
| 4.7 | Result second line "The caldera now holds a Rich amount of fire Primum. It refills over many weeks." | "The Ashmouth Caldera now holds a Rich amount of fire Primum. It refills slowly." (`fe-s4-harvest-panel-result`). Names the place and says whether and how it refills; "slowly" for "over many weeks" is a wording difference. Was F8 | MATCH-NOTE |
| 4.8 | Slain foe: "The fire elemental is destroyed." heading and "Slain" tag | Wrapper shows the name and "(Slain)"; the real combat row was not mounted | N/R |
| 4.9 | "You sense fire Primum in its remains." | Present, exact text (`fe-s4-foe-before`) | MATCH |
| 4.10 | Check line "Check: Wits + Harvesting . +2 from your thread on Pyromancy" | "Check: Harvest Primum . +10 from your thread on Pyromancy" for the pyromancer with a level-200 thread; the figure is the real bonus. Was F9 | MATCH-NOTE |
| 4.11 | Harvest button, then "Success. You draw out 1 Fire Primum (Common)." and "Nothing more can be drawn from the elemental." | Harvest button, "Success. You draw out 2 Fire Primum (Fine)." and "Nothing more can be drawn from the elemental." (`fe-s4-foe-after-light.png`, `-dark.png`); the article is there and the sentence is word for word the demo's. The quantity and quality follow this round's authored outcome row. Was F14 | MATCH |
| 4.12 | Telnet `extract fire` and `extract fire from elemental` | Bare `extract` now prints "You can extract fire Primum (Rich) here." then "Check: Harvest Primum . +10 from your thread on Pyromancy" then "Each attempt costs 2 AP, whatever you roll."; the place answer over telnet ends with the same place line as the web. The foe line over telnet was not re-captured | MATCH-NOTE |

#### Screen 5 - Crafting: Primum as a material, for an item and for a facet (`demo-screen5.png` vs `fe-s5-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 5.1 | Coat recipe lists "Fire Primum . 1, Common or better have 3" | `fe-s5-crafting-quote`: "Fire Primum . 1, Common or better" with "have 3" at the right (red when short). Was F10 | MATCH |
| 5.2 | Facet recipe "Fire Primum . 1 (optional) have 2" | `fe-s5-crafting-quote-optional` and `-ticked`: a tick box, "Fire Primum . 1 (optional)", "have 3" at the right; the facet dialog itself was not mounted | MATCH-NOTE |
| 5.3 | "Check: Dexterity + Tailoring" line | "Check: Enchanting" (the recipe's check type name). The panel keeps its existing "Skill cap" and "On failure" lines. Was F11 | MATCH-NOTE |
| 5.4 | Wool cloth row ("Wool cloth . 2 have 4") | The test recipe has no other material, so no second row was drawn; the row layout is the same one | N/R |
| 5.5 | Craft and Attach buttons | Not part of the quote panel | N/R |
| 5.6 | Result card "Ember-lined coat . Fine / Carries fire" | `fe-s5-item-carries`: item detail panel with "Carries fire" under the stats, shown to another character from `carries: ["fire"]` (quality reads Common in this data) | MATCH |
| 5.7 | Silver ring "Facet: Flame / Carries fire" | The same `carries` line renders on any item; a facet-attached item was not captured | N/R |

### Criterion verdicts

| Criterion | Verdict | Evidence |
|---|---|---|
| Report names the exact commit, environment, viewport and theme | PASS | Header |
| Screenshots are committed files under `docs/reviews/5125/` | PASS | Screenshots section |
| Approved design reached | PASS with caveat | Read from the saved Artifact copy; the live artifact was not reachable by this reviewer |
| Finding class 1 (rule reaches the page) on the admin pages | PASS | `forms.css` and `widgets.css` reach all three pages; the relationship table is styled |
| Finding class 1 for behaviour (script reaches the page in a runnable order) | PASS | F12 fixed: the script list runs jQuery, `jquery.init.js`, then `inlines.js`; the link renders and adds a row when pressed |
| Finding class 2 (host CSS contract) | PASS | Stock admin markup; React uses the shared Tailwind tokens |
| Screen 1 | Matches | F12 fixed |
| Screen 2 | Matches | F4 and F5 fixed |
| Screen 3 | Matches (one noted extra line) | F13 fixed (no hint on the forge card); the cistern card's taper hint is truthful and follows the ruled call-up line; F6 fixed |
| Screen 4 | Matches | F14, F8 and F9 fixed |
| Screen 5 | Matches | F10 and F11 fixed |
| Divergences covered by rulings | PASS | Gift help last sentence, Magesight header, call-up-to-Trace card lines, round-one rulings |
| Overall | **PASS** | F12, F13 and F14 are fixed and confirmed on the rendered pages; every round-one finding is resolved or ruled. No criterion is FAIL or BLOCKED. Caveats unchanged: the live artifact was read from the saved copy, and the cast-card shell, combat list row and facet dialog were not mounted |

### Round-one findings and their status

- **F1 (harvest item on the substance page):** fixed. Row 1.6.
- **F2 (relationship rows):** fixed. Rows 1.7, 1.8 and 1.9.
- **F3 (Gift help):** fixed with the controller's ruling on the last sentence. Row 1.12.
- **F4 (Magesight header and "You see this until you leave the place."):** the header is ruled the cast result's own display; the line is built. Rows 2.3 and 2.5.
- **F5 (strongest first):** fixed in the panel, the payload and `look`. Rows 2.4 and 2.6.
- **F6 (hint lines):** built. Rows 3.3 and 3.7. The rule now fires only where the curve reduces the total (F13).
- **F7 (call-up-to-Trace lines on the unperceived card):** ruled, the spec's approved call. Rows 3.5 and 3.6.
- **F8 (place name and refill line):** fixed. Row 4.7.
- **F9 (thread bonus on the check line):** fixed. Row 4.10.
- **F10 (required Primum with a quality floor):** fixed. Row 5.1.
- **F11 (check on the crafting card):** fixed. Row 5.3.

### Findings closed in this round

- **F12 (was a defect): fixed.** `SubstanceAdmin.Media` now lists the jQuery file, `jquery.init.js` and `inlines.js` in Django's own order. Row 1.8; `admin-substance.png` shows the link and `admin-substance-add-another-clicked.png` shows a fifth row after pressing it, with no console error.
- **F13 (was a minor defect): fixed.** `_hint_texts` in `src/world/magic/services/substance.py` shows the taper hint only when two or more sources add and the curve turns their sum into less power. The forge card (4 points, +4) has none; the caldera card (12 points, +8) has it. Rows 3.3, 3.4 and 3.7.
- **F14 (was a nit): fixed.** `harvest` in `src/world/magic/services/harvest.py` now writes "Nothing more can be drawn from the elemental." Row 4.11.

### Closing note

No findings are unresolved. One scope note for the human, not a defect: the cistern card in this build shows the taper hint, which the demo's single-source cistern card does not, because the approved call-up-to-Trace line gives the card a second source and the curve then really does reduce the total (5 points give +4).

### Proposed mechanical companion

A `SubstanceAdminTests` assertion on the rendered change page that `admin/js/jquery.init.js` appears before `admin/js/inlines.js` in the page's script list, and a check that every `<script src>` on the page resolves from disk. The branch's own tests already cover the hint rule (the two-source taper journey asserts the hint where 8 points give 6, and the ice journeys no longer expect it where the total does not taper) and the harvest sentence; those were not re-run here, only observed on the rendered output.
