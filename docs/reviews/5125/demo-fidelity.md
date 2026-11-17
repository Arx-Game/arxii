# Demo fidelity review: #5125 Substances and Primum

## Header

| Item | Value |
|---|---|
| Reviewed commit | `854d11fafea01ad078ed4798de071ce722f1099d` (branch `feature-5125-substances-and-primum-what-a-gift-works`) |
| Approved design | https://claude.ai/artifact/3AVFkN2kC9i1qJVAhtYrhq (issue #5125 body, "Demo (approved reference once this spec is approved)"), five screens |
| How the design was read | The `Artifact` tool was not available to this reviewer. The demo was read from the HTML file that the coordinator's own `Artifact read` saved earlier in the session (`tool-results/artifact-11856231-1794882759-ae91.html`, saved 2026-11-17 06:39). That file matches the coordinator's working copy of the demo (`scratchpad/5125/substances-primum-demo.html`) apart from the page wrapper lines. If staff edited the artifact after that read, this review does not cover the edit. |
| Reference screenshots | `demo-screen1.png` to `demo-screen5.png` (the demo HTML rendered at 1280x900) |
| Environment | Local devcontainer, SQLite test tier, Django test client for admin, Vite 6.4.5 dev server on port 3457 (stopped afterwards) plus headless Chromium 1208 for the React surfaces. No production or dev database was touched. |
| Viewport and theme | 1280x900. Admin: light theme (Django admin default). React surfaces: both light and dark (`-light.png` and `-dark.png`). |
| Owner rulings applied as non-defects | (a) removed fields and relabels, (b) telnet verb `extract`, (c) "Costs N AP", (d) a living creature's Primum does not feed a cast, (e) "Something here strengthens your <own>" |

## Fixture versus live boundary

- **Live, real code:** admin pages are the real `ModelAdmin` pages rendered through the Django test client against test data built with the branch's factories. Their HTML was saved with its linked admin stylesheets and scripts resolved from disk (`base.css`, `forms.css` and its `@import widgets.css`, `autocomplete.css`, `arx_admin.css`, `SelectFilter2.js` and the others), then screenshotted. The page content is cropped to `#content` (the admin sidebar is hidden to keep the image readable).
- **Payloads are real server output.** Every JSON shape the React screens consume (room-frame `primum` block, `cast_preview.surroundings`, combat opponent `harvest_offers`, `harvest_primum` dispatch result, crafting quote, item detail with `carries`) was produced by the branch's own serializers and services in throwaway journey-style tests, then deleted. The journeys' `JourneyCase` base is tagged postgres, so they were run once each on the SQLite tier (`arx test --sqlite`, one class at a time); they passed.
- **React components are the real ones** (`PrimumPanel`, `HarvestPanel` through `PrimumPanel`, `HarvestRow`, `SurroundingsLines`, `CraftingQuotePanel`, `ItemDetailPanel`) mounted in a throwaway Vite page (deleted afterwards) inside the real Redux store and a react-query client.
- **Fixture boundary:** `window.fetch` in the harness answered the dispatch POST with the recorded real `harvest_primum` result (a mock for the network hop only) and returned empty lists for unrelated item-panel queries. The cast cards show only the surroundings lines (`SurroundingsLines`), not the surrounding cast card shell, so the demo's Cancel and Cast buttons were not rendered. The slain foe row is a minimal wrapper (name and status) around the real `HarvestRow`; the real `CombatantsList` row was not mounted. `AttachFacetDialog` was not mounted; the facet quote shares `CraftingQuotePanel`, which was.
- **Not rendered:** the Primum step, power curve and harvest outcome inlines on the config admin, the Place Primum and Creature Primum inlines, telnet output other than the `look` line (the journeys' own assertions cover `extract`; see Findings for what they show).

## Screenshots

Admin (light, 1280 wide): `admin-substance.png`, `admin-gift.png`, `admin-itemtemplate-harvesting.png`, `admin-itemtemplate.png`.
React, each in `-light` and `-dark`: `fe-s2-room-pyromancer`, `fe-s2-room-no-perception`, `fe-s2-room-magesight`, `fe-s3-cast-cards` (four cards on one page), `fe-s4-harvest-panel`, `fe-s4-harvest-panel-result`, `fe-s4-foe-before`, `fe-s4-foe-after`, `fe-s5-crafting-quote`, `fe-s5-crafting-quote-ticked`, `fe-s5-item-carries`.

## Interactions exercised

- Opened the Substance change page for fire with three relationships stored, and the Gift change page for Pyromancy with a substance picked.
- Opened the Item template page for the Fire Primum template and expanded its Harvesting fieldset.
- Room panel as a pyromancer (own-gift sense), as a character with no perception, and as a harvester after a sighting of fire and earth.
- Clicked Harvest Primum on the room panel, saw the pick, check line, AP line, Cancel and Harvest, pressed Harvest and read the answer.
- On a slain elemental: saw the sense line, check line, AP line and Harvest button, pressed Harvest and read the answer.
- Cast cards for a fire mage at a forge and at a caldera with a worn coat, an ice mage at a caldera not perceiving fire, an ice mage at a cistern after a sighting.
- Crafting quote for a recipe with optional Fire Primum, ticked the box; item detail of the crafted coat as seen by another character.

## Visual checklist

Legend: MATCH (compared on screen against the demo image at the same viewport), MATCH-NOTE (same element, wording or style differs trivially), GAP (element absent or different, a finding below), N/R (not rendered, see boundary).

### Screen 1 - Admin: one substance, its relationships, the Gift that works it (`demo-screen1.png` vs `admin-substance.png`, `admin-gift.png`, `admin-itemtemplate-harvesting.png`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 1.1 | Breadcrumb "Home > Magic > Substances > Fire", title "Change substance" | Django admin title "Change substance" and object name "fire" shown; breadcrumb is in the cropped-out header and is the stock admin one | MATCH-NOTE |
| 1.2 | Name field with help "What the cast card and the roll breakdown call it." | Present, same help | MATCH |
| 1.3 | "Which room condition feeds it" pick, value "Heat", help "Picked from the room conditions the game already tracks." | Present, same label and help; the option reads "Heat exposure" (existing room-condition label) | MATCH-NOTE |
| 1.4 | "Stronger when it is" pick, value "Higher" | Present; the option reads "Higher (wetter, windier or hotter, e.g. water, wind or fire)" and the help paragraph is longer than the demo shows | MATCH-NOTE |
| 1.5 | "Property added to every technique of this gift" with the long help line | Present with the same label and help, as an autocomplete with add/change links | MATCH |
| 1.6 | "Item created by harvesting" pick (value "Fire Primum") with help "The item template a harvest of this substance makes." on the substance page | Absent from the substance page. The field exists only on the Item template page, inside a collapsed "Harvesting" fieldset, with different help text | GAP (finding F1) |
| 1.7 | "Relationships" table: rows of Other substance pick, Kind pick (Opposed/Related), Delete box, "add another" | Two dual-list pickers, "Related to" and "Opposed to" (filter box, Choose and Remove arrows). No Kind column, no row table, no "add another" | GAP (finding F2) |
| 1.8 | Relationship help "Each relationship is authored once and shows on both substances. Relationships never chain: light being related to fire says nothing about what light is to ice." | Help is split over the two lists: "A caster of one of these gets a share of this substance's benefit, and the other way round. Relationships never chain: ..." and "Each of these works against a caster of this substance, and the other way round." The "authored once and shows on both" sentence is gone | GAP (part of F2) |
| 1.9 | Save button | Admin submit row: Save, Save as new, Save and continue editing, Delete | MATCH-NOTE |
| 1.10 | Gift form shows Name, Kind (Major), Substance (fire) | All present with the rest of the existing Gift form around them; Substance is an autocomplete with "fire" picked | MATCH |
| 1.11 | Gift Substance help "The one substance this Gift perceives and controls. Child Gifts inherit it unless they name their own. Minor Gifts usually leave this blank." | Help reads "The one substance this gift works through, such as fire or shadow. Every major gift has one and a minor gift has none." The child-inherits sentence is dropped, and "usually leave blank" became "has none" | GAP (finding F3) |
| 1.12 | Old per-Gift inline with seven fields gone | No substance inline on the Gift page | MATCH |
| 1.13 | Credit fields (Written by, Written on, Reviewed by, Reviewed on) not drawn in the demo | Drawn on the substance page (the standard credit block every authored model carries) | MATCH-NOTE |

CSS reach (finding class 1): the substance page links `base.css`, `forms.css` (which `@import`s `widgets.css`), `autocomplete.css`, `arx_admin.css`, `nav_sidebar.css` and `responsive.css`, and it renders as a styled admin page in the screenshots, so no unstyled-rule defect here. The pages use the stock `ModelAdmin`/`fieldset.module.aligned` markup, no `as_div` or hand-written labels.

### Screen 2 - A place: who perceives the Primum it holds (`demo-screen2.png` vs `fe-s2-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 2.1 | Pyromancer: card titled "You sense" with row "Fire Primum: Massive", no check needed | `fe-s2-room-pyromancer`: "YOU SENSE" heading (small caps) with "Fire Primum: Massive". A "Harvest Primum" button sits under it (allowed: a mage perceives her own substance, rule 26) | MATCH-NOTE |
| 2.2 | Character with no perception sees only the room description | `fe-s2-room-no-perception`: nothing rendered under the description | MATCH |
| 2.3 | After Magesight: "Magesight / Good success" header row | Not in the room panel. The technique's own result is a separate message, not part of the sense block | GAP (finding F4) |
| 2.4 | After Magesight: rows "Fire Primum: Massive" then "Earth Primum: Trace" (strongest first) | `fe-s2-room-magesight`: both rows, in the order Earth Trace then Fire Massive | GAP (finding F5) |
| 2.5 | "You see this until you leave the place." | Absent from the room panel and from the server payload | GAP (finding F4) |
| 2.6 | Telnet `look` shows the same "You sense" line | Real `look` output ends "You sense earth Primum: Trace. You sense fire Primum: Rich." (one sentence per substance) | MATCH |

### Screen 3 - Casting: one bonus from everything around them (`demo-screen3.png` vs `fe-s3-cast-cards-*.png`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 3.1 | Forge card: heading "Fire around you", source "The forge . Trace 1", source "Ember-lined coat, worn . carries fire 2", total "Fire adds +3 power" | Heading "FIRE AROUND YOU", "The Long Hall . Trace 2", "Ember-lined coat, worn . carries fire 2", "Fire adds +4 power". Same structure and wording; numbers differ because the demo's numbers are examples | MATCH |
| 3.2 | Caldera card: "The Ashmouth Caldera . Massive 8", coat 2, "Fire adds +7 power" | "The Long Hall . Massive 10", coat 2, "Fire adds +8 power". Same structure | MATCH |
| 3.3 | Caldera card hint "The more fire around you, the less each extra source adds." | Absent. No such string exists in the frontend or the server | GAP (finding F6) |
| 3.4 | Unperceived card: heading "Around you", one line "Something here works against your ice -6 power" | Heading "ICE AROUND YOU" with "Calls up ice, free, your control covers it", "The Long Hall . Trace 2", "Something here works against your ice -10", total "Around you adds -6 power". The foreign substance is not named, as designed. The extra lines come from the spec's recorded technical call that a cast with none of her substance calls it up to Trace | MATCH-NOTE (finding F7, scope note) |
| 3.5 | Cistern card: "Around you", "The flooded cistern . Rich water, related to ice 3", "Related substances add +3 power" | "ICE AROUND YOU" heading, Trace 2, "The Long Hall . Rich water, related to ice 3", total "Around you adds +4 power". Source wording matches; total label differs because the ice Trace source is also present | MATCH-NOTE (F7) |
| 3.6 | Cistern hint "You can draw strength for your ice from the water here. You cannot move the water." | Absent from the frontend and the server | GAP (finding F6) |
| 3.7 | Heading drawn in small caps, power lines coloured, amounts right-aligned | Same: caps heading, right-aligned monospace amounts, green positive power, amber negative | MATCH |
| 3.8 | Cancel and Cast buttons | Not rendered (cast card shell is untouched by this diff) | N/R |

### Screen 4 - Harvesting: from a place, and from a slain creature (`demo-screen4.png` vs `fe-s4-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 4.1 | Title "Harvest Primum", label "Draw out" | Both present (`fe-s4-harvest-panel`) | MATCH |
| 4.2 | Pick of "Fire Primum . Massive" and "Earth Primum . Trace" as chips | Same labels as radio buttons with the first selected, not chips | MATCH-NOTE |
| 4.3 | Check line "Check: Wits + Harvesting" | "Check: Harvest Primum" (the authored check type's name) | MATCH-NOTE |
| 4.4 | (ruling c) AP cost line | "Costs 2 AP" | MATCH |
| 4.5 | Cancel and Harvest buttons | Both present, Harvest primary | MATCH |
| 4.6 | Result "Good success. You draw out 2 Fire Primum (Fine)." | "Success. You draw out 2 Fire Primum (Fine)." (real server text, tier name differs with the forced outcome) | MATCH |
| 4.7 | Result second line "The caldera now holds a Rich amount of fire Primum. It refills over many weeks." | "Fire Primum here is now Rich." The refill sentence and the place name are gone | GAP (finding F8) |
| 4.8 | Slain foe: "The fire elemental is destroyed." heading and "Slain" tag | Not rendered (wrapper only); the real combat row was not mounted | N/R |
| 4.9 | "You sense fire Primum in its remains." | Present, exact text (`fe-s4-foe-before`) | MATCH |
| 4.10 | Check line "Check: Wits + Harvesting . +2 from your thread on Pyromancy (example)" | "Check: Harvest Primum". The thread-bonus half is not shown; the payload carries no bonus figure | GAP (finding F9) |
| 4.11 | Harvest button, then "Success. You draw out 1 Fire Primum (Common)." and "Nothing more can be drawn from the elemental." | Harvest button present, answer "Success. You draw out 2 Fire Primum (Fine)." and "Nothing more can be drawn from elemental." (the article is missing) | MATCH-NOTE |
| 4.12 | Telnet `extract fire` and `extract fire from elemental` | Verified only through the branch's own journeys (`test_primum_harvest_journeys`) which assert those two lines, not re-run here | N/R |

### Screen 5 - Crafting: Primum as a material, for an item and for a facet (`demo-screen5.png` vs `fe-s5-*`)

| # | Demo element | Built | Status |
|---|---|---|---|
| 5.1 | Coat recipe lists required materials ("Wool cloth . 2 have 4") and "Fire Primum . 1, Common or better have 3" | Quote panel shows an optional checkbox row "Fire Primum . 1 (optional)" with "have 1". There is no minimum-quality wording and the recipe is not drawn as a required-with-floor | GAP (finding F10) |
| 5.2 | Facet recipe "Fire Primum . 1 (optional) have 2" | Same wording and layout for the optional row (shared `CraftingQuotePanel`); the facet dialog itself was not mounted | MATCH-NOTE |
| 5.3 | "Check: Dexterity + Tailoring" line | Not shown; the panel shows "Skill cap: Common" and "On failure: ..." instead. The panel is existing code, not changed by this diff | GAP (finding F11) |
| 5.4 | Craft and Attach buttons | Not part of the quote panel; N/R | N/R |
| 5.5 | Result card "Ember-lined coat . Fine / Carries fire" | `fe-s5-item-carries`: item detail panel with "Carries fire" under the stats, shown from `carries: ["fire"]` that another character reads | MATCH |
| 5.6 | Silver ring "Facet: Flame / Carries fire" | The same `carries` line renders on any item; a facet-attached item was not captured | N/R |

## Criterion verdicts

| Criterion | Verdict | Evidence |
|---|---|---|
| Report names the exact commit, environment, viewport and theme | PASS | Header |
| Screenshots are committed files under `docs/reviews/5125/` | PASS | Screenshots section |
| Approved design reached | PASS with caveat | Read from the coordinator's saved Artifact file; the live artifact was not reachable by this reviewer |
| Finding class 1 (rule reaches the page) on the admin pages | PASS | Rendered with the stylesheets resolved from disk; `forms.css` and `widgets.css` reach the page |
| Finding class 2 (host CSS contract) | PASS | Stock admin markup; React uses the shared Tailwind tokens |
| Screen 1 | FAIL | F1, F2, F3 |
| Screen 2 | FAIL | F4, F5 |
| Screen 3 | FAIL (copy) | F6; structure matches |
| Screen 4 | FAIL (copy) | F8, F9 |
| Screen 5 | FAIL (gaps) | F10, F11 |
| Divergences covered by owner rulings | PASS | Removed fields, labels, `extract`, AP cost, unperceived wording all as ruled |
| Overall | **FAIL** | Eleven findings; none block play, five change approved copy or layout |

## Unresolved findings

Each is a defect against the approved demo unless the note says it is a scope question for the human.

- **F1 (defect or scope question):** The "Item created by harvesting" field is not on the Substance page. The demo draws it there (`demo-screen1.png`, annotation "the Harvested as field"). The build put `ItemTemplate.primum_substance` on the Item template page (`src/world/items/admin.py` line 317, label set in `src/world/items/template_admin_parts.py` line 117), as the technical design in the issue says ("`primum_substance` on `ItemTemplate`"). The demo and the technical design disagree, so the human decides which wins. If the demo wins, the substance form needs a field that reads the template the other way round.
- **F2 (defect):** Relationships are two dual-list pickers (`SubstanceAdminForm.related_to` and `.opposed_to`, `src/world/magic/admin.py` lines 1188 to 1265), not the demo's table of rows with a Kind pick and "add another". The issue's technical design also says "SubstanceAdmin with relation inline". The two-list form is a reasonable answer to the pair-stored-once rule, but it is not the approved layout and drops the "authored once and shows on both substances" help line. Needs a human call.
- **F3 (defect):** The Gift form's Substance help text dropped the approved wording: "Child Gifts inherit it unless they name their own. Minor Gifts usually leave this blank." (`GiftAdminForm.Meta.help_texts`, `src/world/magic/admin.py` line 1120).
- **F4 (defect or scope question):** After Magesight the demo shows a "Magesight / Good success" header on the sense block and the line "You see this until you leave the place." Neither is built in `PrimumPanel` (`frontend/src/game/components/room-panel/PrimumPanel.tsx`) or in the room payload. The spec's scope does not say they are out.
- **F5 (defect):** The sense rows are not strongest first. The demo lists Fire Massive above Earth Trace after a good-success Magesight; the real payload and panel list Earth Trace first (alphabetical). The spec says a plain success names the strongest, which implies strongest first.
- **F6 (defect or scope question):** Two approved hint lines are not built: "The more fire around you, the less each extra source adds." on the caldera card, and "You can draw strength for your ice from the water here. You cannot move the water." on the cistern card. No such string exists in `frontend/src` or `src/world`. Not recorded in the spec as out of scope.
- **F7 (scope note, not a defect):** An ice mage at the caldera who has not perceived the fire gets a card with "Calls up ice", an ice Trace source, the unnamed fire line and a total, not the demo's single unnamed line. This follows the spec's "Calls made in the technical design" (a cast calls her own substance up to Trace). It is listed so the human can confirm that call overrides the demo's single-line card.
- **F8 (defect):** The place harvest answer's second line reads "Fire Primum here is now Rich." The demo's approved copy names the place and says how it refills: "The caldera now holds a Rich amount of fire Primum. It refills over many weeks." (`remaining_line` from the harvest service, `src/world/magic/services/harvest.py`).
- **F9 (defect):** The slain-foe check line does not mention the thread bonus ("+2 from your thread on Pyromancy"). `HarvestOffer` carries only `check_name` and `ap_cost` (`frontend/src/hooks/types.ts`), so the bonus is not on screen even though the spec gives a matching thread a bonus on the check.
- **F10 (scope question):** The demo's coat recipe draws Primum as a required material with a quality floor ("Common or better"). The build has only an optional flag (`CraftingMaterialRequirement.is_optional`) and no minimum-quality field, so a required Primum with a floor cannot be authored. The spec text says a recipe can require or optionally take Primum, but does not mention a floor.
- **F11 (scope question):** The demo's crafting card shows "Check: Dexterity + Tailoring". The quote panel has never shown the check (it shows skill cap and failure risk) and this diff does not change that. Whether the approved design expected it to be added is the human's call.

Minor wording differences that are not findings: "Heat exposure" and the longer "Higher (...)" option labels come from existing room-condition choice labels; "Nothing more can be drawn from elemental." drops the article.

## Proposed mechanical companion

A `SubstanceAdminTests` assertion that the rendered substance change page contains a `<label>` for the harvest-item field and one row per stored relationship, so F1 and F2 cannot drift again, and a frontend test that `PrimumPanel` orders `sensed` rows by step rank descending (F5).
