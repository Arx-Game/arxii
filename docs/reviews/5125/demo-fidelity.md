# Demo fidelity review: #5125 Substances and Primum (re-review after the pre-PR fixes)

## Header

| Item | Value |
|---|---|
| Reviewed commit | `f42e9d68f6269985cb69469e7d0c9941f2f37570` (branch `feature-5125-substances-and-primum-what-a-gift-works`). The first review was of `854d11faf`; the fixes landed in `6c9fb25a2..f42e9d68f`. |
| Approved design | https://claude.ai/artifact/3AVFkN2kC9i1qJVAhtYrhq (issue #5125 body, "Demo (approved reference once this spec is approved)"), five screens |
| How the design was read | The `Artifact` tool is not available to this reviewer, so the demo was read again from the saved copy used in round one (`scratchpad/rv/demo.html`, the coordinator's `Artifact read` output) and the five reference renders `demo-screen1.png` to `demo-screen5.png`, which were re-opened side by side with every new screenshot. If staff edited the artifact after that read, this review does not cover the edit. |
| Reference screenshots | `demo-screen1.png` to `demo-screen5.png` (the demo HTML rendered at 1280x900) |
| Environment | Local devcontainer, SQLite test tier. Admin pages through the Django test client; React surfaces through a throwaway Vite 6.4.5 page on port 3457 (stopped by pid afterwards, no `just stop`) and headless Chromium 1208. No production or dev database was touched. All throwaway files (two test modules, the Vite page) were deleted before the commit. |
| Viewport and theme | 1280x900. Admin: light theme. React surfaces: both light and dark (`-light.png` and `-dark.png`). |
| Rulings applied as non-defects | Owner rulings from round one: removed fields and relabels, telnet verb `extract`, "Costs N AP", a living creature's Primum does not feed a cast, "Something here strengthens your <own>". Controller rulings for this round: the Gift form's last help sentence reads "Minor Gifts have no substance." because the form refuses a substance on a Minor Gift; the "Magesight / Good success" header is the cast result's own display, not the room panel; the unperceived-card extra lines are the spec's approved call-up-to-Trace. |

## Fixture versus live boundary

- **Live, real code:** admin pages are the real `ModelAdmin` pages rendered through the Django test client against rows built with the branch's factories (fire with three stored relationships and a harvest item, a Pyromancy Gift with fire picked). The HTML was saved with every linked admin stylesheet and script resolved from disk, including `forms.css` and the `widgets.css` it imports, then screenshotted with the sidebar hidden. The page is the exact server output, so the script order it contains is the order a browser would run.
- **Payloads are real server output.** Every JSON shape the React screens consume was produced again by this round's throwaway journey classes (subclasses of the branch's own `_Caldera`, `_PrimumCraft` and `_IceField` journeys, run once on the SQLite tier with `arx test --sqlite`): the room frame `primum` block for three viewers, the combat opponent `harvest_offers` (with the thread bonus), the `harvest_primum` dispatch results for a place and a slain foe, the four `cast_preview.surroundings` cards (including the forge and caldera cards with a worn coat made by the real craft path), the crafting quote for a required Common-or-better Primum and for an optional one, the item detail seen by another character, and the telnet `look` and `extract` output.
- **React components are the real ones** (`PrimumPanel`, `HarvestPanel` through it, `HarvestRow`, `SurroundingsLines`, `CraftingQuotePanel`, `ItemDetailPanel`) mounted in the real Redux store and a react-query client.
- **Fixture boundary:** `window.fetch` in the harness answered only the dispatch POST with the recorded real `harvest_primum` result (a mock for the network hop) and returned empty lists for unrelated item-panel queries. The cast cards show only the surroundings lines (`SurroundingsLines`) inside a plain bordered box, not the cast card shell, so the demo's Cancel and Cast buttons were not rendered. The slain-foe row is a minimal wrapper (name and "Slain") around the real `HarvestRow`; the real combat list row was not mounted. `AttachFacetDialog` was not mounted; the facet quote shares `CraftingQuotePanel`, which was. The harvest check line shows "Check: Harvest Primum" because that is the authored check type's name in the test data.
- **Not rendered:** the Primum step, power curve and harvest outcome inlines on the config admin, the Place Primum and Creature Primum inlines, and telnet output other than what the payload dumps captured (see Findings).

## Screenshots

Admin (light, 1280 wide): `admin-substance.png`, `admin-substance-inlines-js-after-jquery-init.png` (the same page with only the script order corrected, as evidence for F12), `admin-gift.png`, `admin-itemtemplate-harvesting.png`, `admin-itemtemplate.png` (both item template shots unchanged since round one, byte identical, so the page did not change).
React, each in `-light` and `-dark`: `fe-s2-room-pyromancer`, `fe-s2-room-no-perception`, `fe-s2-room-magesight`, `fe-s3-cast-cards` (four cards on one page), `fe-s4-harvest-panel`, `fe-s4-harvest-panel-result`, `fe-s4-foe-before`, `fe-s4-foe-after`, `fe-s5-crafting-quote` (the required Common-or-better row), `fe-s5-crafting-quote-optional` (the optional row), `fe-s5-crafting-quote-ticked`, `fe-s5-item-carries`.

## Interactions exercised

- Opened the Substance change page for fire with three stored relationships and a harvest item set, and the Gift change page for Pyromancy with fire picked; loaded the substance page in headless Chromium with the console open and counted the "Add another relationship" link.
- Opened the Item template page for Fire Primum and expanded its Harvesting fieldset.
- Room panel as a pyromancer with a thread on her Gift, as a character with no perception, and as a harvester after sightings of fire and earth.
- Clicked Harvest Primum on the room panel, saw the pick, check line, AP line, Cancel and Harvest, pressed Harvest and read the answer.
- On a slain elemental viewed by the pyromancer: saw the sense line, check line with the thread bonus, AP line and Harvest button, pressed Harvest and read the answer.
- Cast cards for a fire mage at a forge with a worn coat, at a caldera with the coat, an ice mage at the caldera not perceiving fire, and an ice mage at a cistern after a sighting.
- Crafting quote for a recipe requiring Fire Primum, Common or better, and for one taking it optionally (ticked the box); item detail of the crafted coat as another character sees it.

## Visual checklist

Legend: MATCH (compared on screen against the demo image at the same viewport), MATCH-NOTE (same element, wording or style differs trivially), GAP (element absent or different, a finding below), N/R (not rendered, see boundary).

### Screen 1 - Admin: one substance, its relationships, the Gift that works it (`demo-screen1.png` vs `admin-substance.png`, `admin-gift.png`, `admin-itemtemplate-harvesting.png`)

| # | Demo element | Built (at `f42e9d68f`) | Status |
|---|---|---|---|
| 1.1 | Breadcrumb "Home > Magic > Substances > Fire", title "Change substance" | Title "Change substance" and object name "fire"; the breadcrumb is in the cropped-out header and is the stock admin one | MATCH-NOTE |
| 1.2 | Name field with help "What the cast card and the roll breakdown call it." | Present, same help | MATCH |
| 1.3 | "Which room condition feeds it" pick, "Heat", help "Picked from the room conditions the game already tracks." | Present, same label and help; the option reads "Heat exposure" (the existing room-condition label) | MATCH-NOTE |
| 1.4 | "Stronger when it is" pick, "Higher" | Present; the option reads "Higher (wetter, windier or hotter, e.g. water, wind or fire)" with a longer help paragraph | MATCH-NOTE |
| 1.5 | "Property added to every technique of this gift" with the long help line | Present with the same label and help, as an autocomplete with add/change links | MATCH |
| 1.6 | "Item created by harvesting" pick (value "Fire Primum") with help "The item template a harvest of this substance makes." on the substance page | Now present on the substance page, same label and same help, with "Fire Primum" picked (`admin-substance.png`). Was F1 | MATCH |
| 1.7 | "Relationships" table of rows: Other substance pick, Kind pick (Opposed/Related), Delete box | Now a "RELATIONSHIPS" table with OTHER SUBSTANCE, KIND and DELETE? columns, one row per stored relationship (earth Related, ice Opposed, light Related) and a blank row. Was F2 | MATCH |
| 1.8 | "add another" link under the table | Absent on the page as served. `inlines.js` is linked before `jquery.init.js`, so it throws `Cannot read properties of undefined (reading 'fn')` and never builds the link; the same page with only the script order corrected shows "+ Add another relationship" and a remove icon (`admin-substance-inlines-js-after-jquery-init.png`) | GAP (finding F12) |
| 1.9 | Help "Each relationship is authored once and shows on both substances. Relationships never chain: ..." | Present under the table, word for word | MATCH |
| 1.10 | Save button | Admin submit row: Save, Save as new, Save and continue editing, Delete | MATCH-NOTE |
| 1.11 | Gift form shows Name, Kind (Major), Substance (fire) | All present within the existing Gift form; Substance is an autocomplete with "fire" picked | MATCH |
| 1.12 | Gift Substance help "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts usually leave this blank." | Reads "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts have no substance." The last sentence differs by controller ruling (the form refuses a substance on a Minor Gift). Was F3 | MATCH (ruling) |
| 1.13 | Old per-Gift inline with seven fields gone | No substance inline on the Gift page | MATCH |
| 1.14 | Credit fields (Written by, Written on, Reviewed by, Reviewed on) not drawn in the demo | Drawn on the substance page (the standard credit block every authored model carries) | MATCH-NOTE |

CSS reach (finding class 1): the substance, Gift and Item template pages link `base.css`, `forms.css` (which imports `widgets.css`), `autocomplete.css`, `arx_admin.css`, `nav_sidebar.css` and `responsive.css` and render as styled admin pages. The new relationship table uses the stock tabular inline markup (`.tabular.inline-related`, `.inline-heading`) that `forms.css` and `base.css` style, and it is drawn correctly. The new template `src/web/templates/admin/magic/substance/change_form.html` writes the inline markup by hand around the form's own formset, which is why the script-order problem in F12 is possible; the existing test asserts that `admin/js/inlines.js` is on the page but not that it runs after `jquery.init.js`.

### Screen 2 - A place: who perceives the Primum it holds (`demo-screen2.png` vs `fe-s2-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 2.1 | Pyromancer: card titled "You sense" with row "Fire Primum: Massive", no check needed | `fe-s2-room-pyromancer`: "YOU SENSE" heading with "Fire Primum: Massive" and a Harvest Primum button (allowed: a mage perceives her own substance) | MATCH-NOTE |
| 2.2 | Character with no perception sees only the room description | `fe-s2-room-no-perception`: nothing rendered under the description | MATCH |
| 2.3 | After Magesight: "Magesight / Good success" header row | Not in the room panel. By controller ruling this header is the cast result's own display | MATCH (ruling). Was F4 part 1 |
| 2.4 | After Magesight: rows "Fire Primum: Massive" then "Earth Primum: Trace" (strongest first) | `fe-s2-room-magesight`: Fire Massive then Earth Trace. Was F5 | MATCH |
| 2.5 | "You see this until you leave the place." | Present under the rows when any row came from a sighting, and absent for the pyromancer's own substance. Was F4 part 2 | MATCH |
| 2.6 | Telnet `look` shows the same "You sense" line | Real `look` after the sightings ends "You sense fire Primum: Massive. You sense earth Primum: Trace." (strongest first, one sentence per substance); the pyromancer's `look` ends "You sense fire Primum: Massive." | MATCH |

### Screen 3 - Casting: one bonus from everything around them (`demo-screen3.png` vs `fe-s3-cast-cards-*.png`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 3.1 | Forge card: heading "Fire around you", "The forge . Trace 1", "Ember-lined coat, worn . carries fire 2", "Fire adds +3 power" | "FIRE AROUND YOU", "The Long Hall . Trace 2", "Ember-lined coat, worn . carries fire 2", "Fire adds +4 power". Same structure and wording; the numbers are the demo's examples | MATCH |
| 3.2 | Caldera card: "The Ashmouth Caldera . Massive 8", coat 2, "Fire adds +7 power" | "The Long Hall . Massive 10", coat 2, "Fire adds +8 power" | MATCH |
| 3.3 | Caldera hint "The more fire around you, the less each extra source adds." | Present on the caldera card, same words, muted style. Was F6 part 1 | MATCH |
| 3.4 | Forge card has no hint | The same hint also shows on the forge card, because the rule adds it whenever two or more sources add points and the forge card has two (the place and the coat) | GAP (finding F13, minor) |
| 3.5 | Unperceived card: heading "Around you", one line "Something here works against your ice -6 power" | "ICE AROUND YOU" with "Calls up ice, free, your control covers it", Trace 2, "Something here works against your ice -10", total "Around you adds -6 power". The foreign substance is not named. The extra lines come from the spec's recorded call that a cast calls her own substance up to Trace; the card has no hint | MATCH-NOTE (F7 scope note) |
| 3.6 | Cistern card: "The flooded cistern . Rich water, related to ice 3", "Related substances add +3 power" | Trace 2, "The Long Hall . Rich water, related to ice 3", total "Around you adds +4 power". Source wording matches; the total label differs because her own Trace source is also present | MATCH-NOTE (F7) |
| 3.7 | Cistern hint "You can draw strength for your ice from the water here. You cannot move the water." | Present, same words. The build also shows the taper hint above it (two sources add), which the demo's cistern card does not | MATCH (extra line is F13). Was F6 part 2 |
| 3.8 | Heading in small caps, power lines coloured, amounts right-aligned | Same: caps heading, right-aligned monospace amounts, green positive power, amber negative | MATCH |
| 3.9 | Cancel and Cast buttons | Not rendered (the cast card shell is untouched by this diff) | N/R |

### Screen 4 - Harvesting: from a place, and from a slain creature (`demo-screen4.png` vs `fe-s4-*`)

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
| 4.11 | Harvest button, then "Success. You draw out 1 Fire Primum (Common)." and "Nothing more can be drawn from the elemental." | Harvest button, "Success. You draw out 2 Fire Primum (Fine)." and "Nothing more can be drawn from elemental." (`fe-s4-foe-after`); the article is still missing | MATCH-NOTE (finding F14, minor) |
| 4.12 | Telnet `extract fire` and `extract fire from elemental` | Bare `extract` now prints "You can extract fire Primum (Rich) here." then "Check: Harvest Primum . +10 from your thread on Pyromancy" then "Each attempt costs 2 AP, whatever you roll."; the place answer over telnet ends with the same place line as the web. The foe line over telnet was not re-captured | MATCH-NOTE |

### Screen 5 - Crafting: Primum as a material, for an item and for a facet (`demo-screen5.png` vs `fe-s5-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 5.1 | Coat recipe lists "Fire Primum . 1, Common or better have 3" | `fe-s5-crafting-quote`: "Fire Primum . 1, Common or better" with "have 3" at the right (red when short). Was F10 | MATCH |
| 5.2 | Facet recipe "Fire Primum . 1 (optional) have 2" | `fe-s5-crafting-quote-optional` and `-ticked`: a tick box, "Fire Primum . 1 (optional)", "have 3" at the right; the facet dialog itself was not mounted | MATCH-NOTE |
| 5.3 | "Check: Dexterity + Tailoring" line | "Check: Enchanting" (the recipe's check type name). The panel keeps its existing "Skill cap" and "On failure" lines. Was F11 | MATCH-NOTE |
| 5.4 | Wool cloth row ("Wool cloth . 2 have 4") | The test recipe has no other material, so no second row was drawn; the row layout is the same one | N/R |
| 5.5 | Craft and Attach buttons | Not part of the quote panel | N/R |
| 5.6 | Result card "Ember-lined coat . Fine / Carries fire" | `fe-s5-item-carries`: item detail panel with "Carries fire" under the stats, shown to another character from `carries: ["fire"]` (quality reads Common in this data) | MATCH |
| 5.7 | Silver ring "Facet: Flame / Carries fire" | The same `carries` line renders on any item; a facet-attached item was not captured | N/R |

## Criterion verdicts

| Criterion | Verdict | Evidence |
|---|---|---|
| Report names the exact commit, environment, viewport and theme | PASS | Header |
| Screenshots are committed files under `docs/reviews/5125/` | PASS | Screenshots section |
| Approved design reached | PASS with caveat | Read from the saved Artifact copy; the live artifact was not reachable by this reviewer |
| Finding class 1 (rule reaches the page) on the admin pages | PASS | `forms.css` and `widgets.css` reach all three pages; the relationship table is styled |
| Finding class 1 for behaviour (script reaches the page in a runnable order) | FAIL | F12: `inlines.js` runs before `jquery.init.js`, so "Add another relationship" never appears |
| Finding class 2 (host CSS contract) | PASS | Stock admin markup; React uses the shared Tailwind tokens |
| Screen 1 | Matches with one gap | F12 |
| Screen 2 | Matches | F4 and F5 fixed |
| Screen 3 | Matches with one gap | F13 (taper hint also on the forge card); F6 fixed |
| Screen 4 | Matches with one nit | F14; F8 and F9 fixed |
| Screen 5 | Matches | F10 and F11 fixed |
| Divergences covered by rulings | PASS | Gift help last sentence, Magesight header, call-up-to-Trace card lines, round-one rulings |
| Overall | **FAIL (one defect)** | F12 is a real, demo-visible defect with a one-line fix; every other round-one finding is resolved or ruled |

## Round-one findings and their status

- **F1 (harvest item on the substance page):** fixed. Row 1.6.
- **F2 (relationship rows):** fixed. Rows 1.7 and 1.9. The "add another" half is the new F12.
- **F3 (Gift help):** fixed with the controller's ruling on the last sentence. Row 1.12.
- **F4 (Magesight header and "You see this until you leave the place."):** the header is ruled the cast result's own display; the line is built. Rows 2.3 and 2.5.
- **F5 (strongest first):** fixed in the panel, the payload and `look`. Rows 2.4 and 2.6.
- **F6 (hint lines):** built. Rows 3.3 and 3.7. The rule is slightly too wide, see F13.
- **F7 (call-up-to-Trace lines on the unperceived card):** ruled, the spec's approved call. Rows 3.5 and 3.6.
- **F8 (place name and refill line):** fixed. Row 4.7.
- **F9 (thread bonus on the check line):** fixed. Row 4.10.
- **F10 (required Primum with a quality floor):** fixed. Row 5.1.
- **F11 (check on the crafting card):** fixed. Row 5.3.

## Unresolved findings

- **F12 (defect, finding class 1 for scripts):** The "Add another relationship" link the demo draws under the relationships table is not on the page. `SubstanceAdminForm`'s `Media` (`src/world/magic/admin.py` line 1358, `js = ["admin/js/inlines.js"]`) merges after `jquery.min.js` but before `jquery.init.js`, so `inlines.js` line 21 reads `django.jQuery` while it is still undefined, throws, and never defines `$.fn.formset`. Django's own inline media lists `jquery.js`, `jquery.init.js` and then `inlines.js`; listing the three in that order here fixes it. Evidence: `admin-substance.png` (no link) against `admin-substance-inlines-js-after-jquery-init.png` (the same HTML with only the script order changed: "+ Add another relationship" and a remove icon appear). Staff can still add one relationship per save through the blank row.
- **F13 (defect, minor):** The taper hint "The more <name> around you, the less each extra source adds." shows on every card with two or more adding sources, including the forge card and the cistern card, where the demo shows it only on the caldera card (`fe-s3-cast-cards-light.png`). The demo's intent is that the hint appears where the curve is actually tapering the total; the build's rule fires earlier. The human may accept the wider rule; it is listed because the demo's forge card has none.
- **F14 (nit):** "Nothing more can be drawn from elemental." still lacks the article the demo shows ("the elemental"); the sentence is written in `src/world/magic/services/harvest.py` (`remaining_line`) from `opponent.name`. The fix report already notes this.

## Proposed mechanical companion

A `SubstanceAdminTests` assertion on the rendered change page that `admin/js/jquery.init.js` appears before `admin/js/inlines.js` in the page's script list (F12), and a check that every `<script src>` on the page resolves from disk. Each earlier proposal (a label for the harvest-item field and one row per stored relationship; a frontend test that `PrimumPanel` orders `sensed` rows strongest first) is, per the fix report, now covered by the branch's own tests (not re-run here).
