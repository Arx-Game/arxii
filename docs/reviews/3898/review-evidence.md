# Review evidence — issue #3898, the Reference Sheet

- Reviewed revision: `8d6de0a8789a4bea565e1be033022c8f60d079b7`
- Reviewer: demo-fidelity-reviewer, run six times against this branch. Five passes returned FAIL, with four, five, three, six and nine findings between them; the sixth returned PASS and named three cosmetic items, all folded in on this revision
- Reviewer verdict: PASS
- Application/build identity: the shipped `CharacterSheetPage` itself, mounted at a real route with its real hooks, the shipped `frontend/src/character_sheets/sheet.css` and the application's real `frontend/src/index.css` token cascade. Nothing is stubbed above the network: every fixture is served as an HTTP response to the query the page actually makes, and the section row is driven by clicking its real buttons
- Environment: Chromium driven by Playwright against a Vite 6.4.3 server on localhost:4174, in the project devcontainer on Linux. The preview entry and its HTML page were throwaway and were deleted before commit; they are not part of the branch
- Viewports/themes: 1440x1000 desktop and 400x1000 phone, deviceScaleFactor 1, light theme with the root carrying `data-realm="arx"`
- Approved design: the demo page at https://claude.ai/artifact/KaVL8KAS5B23bhThLtV6v7, linked at the top of the spec block in issue #3898. Where the built page and the demo disagree, the demo wins unless the divergence is listed and justified below
- Visual review: completed. Thirteen captures of the rendered application were compared against the demo at matching viewport and theme by a vision-capable reviewer, screen by screen
- Visual verdict: PASS
- Screenshots: ![Front page, owner](docs/reviews/3898/owner-sheet.png) ![Front page, stranger](docs/reviews/3898/stranger-sheet.png) ![Physical, owner](docs/reviews/3898/owner-physical.png) ![Physical, stranger](docs/reviews/3898/stranger-physical.png) ![Ties](docs/reviews/3898/owner-ties.png) ![Ties, stranger](docs/reviews/3898/stranger-ties.png) ![Distinctions](docs/reviews/3898/owner-distinctions.png) ![Magic](docs/reviews/3898/owner-magic.png) ![Knowledge](docs/reviews/3898/owner-knowledge.png) ![Holdings](docs/reviews/3898/owner-holdings.png) ![Growth](docs/reviews/3898/owner-growth.png) ![Front page at 400px](docs/reviews/3898/owner-sheet-phone.png) ![Front page on the verdigris ink](docs/reviews/3898/ink-verdigris.png)
- Comparison notes: all eight sections render, and three of them (Sheet, Physical, Ties) are captured in both a viewer state that may read them and one that may not. The plate, the section row, the three-column front page, the folding bands, Physical and the four re-skinned public panels match the demo's composition at the same viewport. Nine divergences are enumerated below with reasons, and one boundary is drawn deliberately and stated rather than left silent: the interactive cards inside Holdings and Growth keep their own chrome
- Tested interactions: switching sections moves the panel and the `aria-current` marker; clicking a look as the owner calls the wear mutation with that `tenure_media_id` while clicking one as a non-owner does not; a non-owner cannot reach Knowledge, Holdings or Growth (the buttons are absent and the page falls back to Sheet); the guidelines and abilities bands fold and unfold and are open by default; the Speaks row appears only for the active character; the Change outfit door moves the page to Holdings
- Fixture/live boundary: the page, every component it composes, the stylesheet and the token cascade are the real shipped code, and so is every hook between them. What is fixture is the HTTP layer alone: the sheet payload, the roster entry, vitals, languages and the composed panels' own endpoints are hand-written responses matching the serializer TypedDicts in `src/world/character_sheets/types.py`. Endpoints with no fixture answer with an empty collection, so those panels render their own empty states. Not mounted: authentication and `Layout`; the signed-in account and this tab's browsing identity are seeded into the real store, which is what `AuthProvider` and the account hydration effect would otherwise do
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| real-surface | PASS | The shipped components and `sheet.css` were mounted and rendered, not a mockup or a template. Build identity above. | |
| demo-comparison | PASS | Thirteen captures compared against the demo at matching viewport and theme; Visual checklist below. | |
| styling-reaches-page | PASS | Every `refsheet-` class used across the new components has a defining rule in `frontend/src/character_sheets/sheet.css`, imported once and applied to a root carrying the `refsheet` class, and every rule in that stylesheet now has a consumer. Computed-style probes taken in the same render confirm the rules resolve, including the two plate grounds, which is what caught the `plate_ink` defect. | |
| gating | PASS | `stranger-sheet.png` and `stranger-physical.png` show no guidelines band, no abilities band, no Add tile, no owner links, no exact height, no covered garment and only five section buttons. | |
| all-sections-rendered | PASS | All eight: Sheet, Physical, Ties, Distinctions, Magic, Knowledge, Holdings, Growth. | |
| responsive | PASS | `owner-sheet-phone.png` at 400px: single column, the looks strip wraps, and a probe confirms no horizontal page scroll. | |
| no-errors | PASS | No page errors and no console errors on any of the thirteen captures. | |
| fixture-boundary | PASS | Stated in full above, naming what is real and what is fixture. | |
| divergences-enumerated | PASS | Nine divergences listed below, each with a reason, plus one stated scope boundary. | |
| live-database | OUT_OF_SCOPE | The dev database refuses `migrate` because generation 1 is partially recorded, and a fresh database cannot be migrated from zero because the app has two leaf nodes. | Both blockers pre-date this branch and are the generation split ADR-0276 describes. Repairing the migration graph is not in this branch's scope. |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Art frame | Portrait-tall frame on the dark ink ground | MATCH | owner-sheet.png |
| Plate ground | The ink's ground, not bare paper | MATCH | owner-sheet.png, probe rgb(28, 18, 16) |
| Empty-frame copy | A sentence naming the look the frame waits on | MATCH | owner-sheet.png |
| Name | Large Cinzel display line | MATCH | owner-sheet.png, probe Cinzel at 56px |
| Title | A lighter second line inside the same heading | MATCH | owner-sheet.png |
| Concept | A short paragraph under the name | MATCH | owner-sheet.png |
| Quote | An italic epigraph | MATCH | owner-sheet.png |
| Glance lines | A hairline, then two short lines, the realm not among them | MATCH | owner-sheet.png |
| Looks strip | Tiles in a row under a second hairline | MATCH | owner-sheet.png |
| Current look | The worn tile ringed in the ink accent | MATCH | owner-sheet.png |
| Add tile | A dashed Add tile, owner only | MATCH | owner-sheet.png absent from stranger-sheet.png |
| Plate content | No mechanical content anywhere on the plate | MATCH | owner-sheet.png |
| Section row order | Sheet, Physical, Ties, Distinctions, Magic | MATCH | owner-sheet.png |
| Yours only break | A hairline, then the gilt Yours only label | MATCH | owner-sheet.png |
| Owner-only sections | Knowledge, Holdings and Growth after the break | MATCH | owner-sheet.png absent from stranger-sheet.png |
| Current section | Underlined in the rubric accent | MATCH | owner-sheet.png |
| Front page columns | Three columns: At a glance, Traits and Gift, The cast | MATCH | owner-sheet.png |
| At a glance rows | Small-caps labels beside their values | MATCH | owner-sheet.png |
| Beginning row | Names the character-generation archetype | MATCH | owner-sheet.png |
| From row | Names the realm, separate from Beginning | MATCH | owner-sheet.png |
| Speaks row | Present for the active character only | MATCH | owner-sheet.png absent from stranger-sheet.png |
| Trait pills | Rounded pills, disadvantage dashed and muted | MATCH | owner-sheet.png |
| Gift sentence | Names the gift, what it resonates with, and its techniques | MATCH | owner-sheet.png |
| Aura strip | Three segments sized by their shares, no figures printed | MATCH | owner-magic.png |
| Magic rail | What they do down the column, what their magic is beside it | MATCH | owner-magic.png |
| Anima ritual | Under Gifts, as a sentence and what it is worked with | MATCH | owner-magic.png |
| Aura split | The split said in words beneath the strip | MATCH | owner-magic.png |
| Glimpse line | Where the owner stands with their Glimpse | MATCH | owner-magic.png |
| The cast | Ringed faces each with a relation line | MATCH | owner-sheet.png |
| Guidelines band | Open, with a note on who may read it | MATCH | owner-sheet.png |
| Guidelines prompts | The prompts in a grid inside the band | MATCH | owner-sheet.png |
| Abilities band | Instrument styling, sans with tabular figures | MATCH | owner-sheet.png |
| Breakthrough line | A sentence under the abilities | MATCH | owner-sheet.png |
| Origin prose | Prose columns with origin entries | MATCH | owner-sheet.png |
| Stranger bands | Guidelines and abilities both absent | MATCH | stranger-sheet.png |
| Rumor band | The heard-of-them band in their place | MATCH | stranger-sheet.png |
| Stranger shape | The page keeps its shape, no empty-state cards | MATCH | stranger-sheet.png |
| Physique block | Height, Build, Hair, Eyes and Skin | MATCH | owner-physical.png |
| Exact height | Shown to the owner, the band alone to a stranger | MATCH | owner-physical.png versus stranger-physical.png |
| Colour note | A line saying where the colours are set | MATCH | owner-physical.png |
| Distinctive features | A block listing features with their target tagged | MATCH | owner-physical.png |
| Wearing block | What is on them, for any viewer | MATCH | owner-physical.png and stranger-physical.png |
| Covered garment | Owner only, and marked as unseen | MATCH | owner-physical.png absent from stranger-physical.png |
| Change outfit | An owner-only quiet door through to Holdings | MATCH | owner-physical.png absent from stranger-physical.png |
| Condition | Written as sentences, not bars | MATCH | owner-physical.png |
| Stranger condition | One observational line in place of the sentences | MATCH | stranger-physical.png |
| Appearance prose | The as-they-appear block | MATCH | owner-physical.png |
| Ties layout | Relationships, Mentors and Kin left; Standing, Titles and Covenant on the rail | MATCH | owner-ties.png |
| Ties, stranger | Relationships and the public rail, no Mentors and no Covenant | MATCH | stranger-ties.png |
| Ties headings | One heading per group, none drawn twice | MATCH | owner-ties.png |
| Mentors block | The vow both ways round, each row tagged with its role | MATCH | owner-ties.png |
| Distinctions layout | One column of entries | MATCH | owner-distinctions.png |
| Rank | A positive rank shown as the demo shows it | MATCH | owner-distinctions.png |
| Disadvantage | A negative rank said as a word, never as a number | MATCH | owner-distinctions.png |
| Feature distinction | Marked as aimed at something visible | MATCH | owner-distinctions.png |
| Magic layout | Gifts, resonances, motif and aura, no navigation bar of its own | MATCH | owner-magic.png |
| Knowledge layout | Secrets, Clues and Gossip in three columns | MATCH | owner-knowledge.png |
| Holdings layout | Purse, Carried and The law over Property and Agreements | MATCH | owner-holdings.png |
| Carried | How much there is, the pieces worth naming, the outfits, a door | MATCH | owner-holdings.png |
| Growth layout | Advancement and sheet changes left, Languages and origin story on the rail | MATCH | owner-growth.png |
| Points to place | Inside Advancement, not a heading of its own | MATCH | owner-growth.png |
| Messages | Under Growth, where the spec's ledger puts it | MATCH | owner-growth.png |
| Plate ink | The plate ground changes, the page stays on Arx paper | MATCH | ink-verdigris.png, probe rgb(15, 26, 24) |
| Phone layout | Single column, the strip wraps, no horizontal scroll | MATCH | owner-sheet-phone.png |

## Computed-style probes

Taken in the same render pass, to assert that rules REACH the page rather than that class names appear in the markup. The plate-ground probe is the one that mattered: it is how the `plate_ink` defect below was found.

| Probe | Result |
| --- | --- |
| Name font-family | Cinzel |
| Name font-size, desktop and phone | 56px and 32px |
| Plate background, ember and verdigris | rgb(28, 18, 16) and rgb(15, 26, 24) |
| Page background | rgb(238, 232, 221), the Arx paper token |
| Horizontal page scroll at 400px | none, at every capture |
| Page and console errors | none on any capture |

## What the reviews found, and what was done

Three passes. The first returned FAIL with four findings, the second FAIL with five more, and a sixth came out of re-capturing the evidence honestly.

| Finding | Severity | Resolution |
| --- | --- | --- |
| The Speaks row was hardcoded to null on the page, so it was dead for every viewer | BLOCKER | Fixed. The page reads the real languages hook, gated to the viewer's active character because that endpoint is scoped to it. Two regression tests. |
| The Beginning row was bound to the origin realm rather than the character-generation archetype | BLOCKER | Fixed. The identity payload carries `beginnings` from `ProfileBeginnings`; the realm gets its own From row. A backend test asserts the two against distinctly named fixtures. |
| The Distinctive features block was absent from Physical entirely | MAJOR | Fixed. The distinction payload carries the trait or marking each per-feature distinction is aimed at. |
| The empty-frame copy dropped the echo of the look's name | MINOR | Fixed. The sentence names the shown look. |
| Worn items were invisible to every viewer but the owner, against the gating table | MAJOR | Fixed. They ride the sheet payload now, where the #2985 layer walk is the only thing that decides. The old path asked an endpoint that answers only for a character its caller plays. |
| The Gift sentence dropped the resonances and techniques already on the payload | MODERATE | Fixed. It reads as the demo's does, minus the tradition, which `GiftEntry` genuinely does not carry. |
| Physical had no Change outfit door | MINOR | Fixed, owner-only, on a new quiet-door rule. |
| The plate's glance line repeated the realm | MINOR | Fixed. The realm has its own row. |
| Five of eight sections kept their old panels verbatim, against build-order step 5 and the ruling on empty-state cards | BLOCKER | Fixed for the six panels step 5 names, plus nine more reached only through the sheet. A duplicate header, two empty-state cards and a second navigation bar went with them. The Mentors grouping step 5 also asked for is built. |
| `plate_ink` was serialized, typed and never read, so every plate rendered with no ground | BLOCKER | Fixed. The page sets `data-ink` on the root, where the tokens are declared, with two regression tests. |
| The aura was one flattened word, and `.refsheet-aura` had been written and connected to nothing | BLOCKER | Fixed. Three proportional segments with the split in words beneath, plus the owner's Glimpse line. Two regression tests, one of which asserts that no figure reaches the page. |
| The plate's caption promised a portrait that follows the character's mood, and nothing delivers it | MAJOR | Fixed by telling the truth rather than by building it: driving a public portrait from `current_mood` would publish what #2994 keeps private, so the caption says only what the page does and the question is recorded for Apostate. |
| The evidence itself was captured from panels mounted by hand rather than from the page | Process | Fixed. The harness now mounts `CharacterSheetPage` at a real route and answers its real queries over HTTP, so the captures show the page's own wiring. Three of this branch's defects were invisible to the older harness for exactly this reason. |
| Magic ran everything down one column with threads alone in the rail, the inverse of the demo | MODERATE | Fixed. `SpellbookTab` takes a slot: what a caster does down the main column, what their magic is in the rail. Both halves read one payload through one cache key. |
| Carried was one sentence pointing at the wardrobe | MAJOR | Fixed. It names how much there is, the pieces worth naming with their quality, the outfits kept, and the door through to change them. |
| Distinctions printed "Rank -1" at a reader | MODERATE | Fixed. A negative rank says "Disadvantage" and a feature-aimed row says so, out of the `feature` field this branch added and that page was not reading. Two regression tests. |
| Messages sat on the front rather than under Growth | MINOR | Fixed, where the spec's ledger puts it. |
| A pre-existing line read "at age undefined" | MINOR | Folded in rather than filed. It surfaced only because Growth became a page people read. |
| My own previous fix dropped the rank from every distinction, not only the negative one | MAJOR | Fixed. A positive rank is a tag again; only a negative one becomes the word. A test now covers both. |
| The anima ritual had been on the payload since #3001 and no page ever drew it | MAJOR | Fixed, under Gifts, with a regression test. The third instance of declared-and-never-connected on this branch. |
| Covenant was a group inside Standing rather than its own rail block | MODERATE | Fixed, the way the spec lists it. |
| Points to place had a heading of its own | MODERATE | Fixed, folded into Advancement where the spec puts it. |
| Carried's outfits were a separate list with the door below everything | MINOR | Fixed to the demo's shape: one row of the same list, the door in its gloss. |
| The Worship block was carried forward in the old page's utility classes | MAJOR | Fixed. It reads in the sheet's vocabulary now, and is recorded as a block the demo does not draw. |

Worth recording, because it is the lesson of this branch: that last one was invisible to two review passes and to my own first evidence set, because the throwaway harness set `data-ink` itself. A harness that supplies what the page is supposed to supply proves the component and hides the wiring. Both wiring defects on this branch now carry unit tests against the page rather than a screenshot.

## Divergences from the demo, and why

1. **The stranger's rumor is not wired.** The band renders and sits where the demo puts it, but the page passes no rumor, so a stranger sees nothing there. The gossip system exists; which guideline a rumor may draw from, and in whose words, is an open question the spec lists as the maintainer's to rule. Shipping a fabricated rumor would be worse than shipping none. Carried in the roadmap.
2. **The Gift line names no tradition.** `GiftEntry` carries no tradition field. The rest of the demo's sentence is there.
3. **No colour swatches beside hair, eyes and skin.** The form trait option carries only a name and a display name. Inventing a hex per option in the frontend would be a second vocabulary for something authored content owns. The spec anticipated this and said to render the words without swatches if no colour field exists.
4. **The All galleries link is owner-only.** A visitor sent to the media page would land on their own media, and there is no per-character galleries page. The character's published galleries are listed on Physical instead, naming every one.
5. **The frame's full-figure note is absent.** It is authoring guidance, and the upload surface is the profile media page, not the sheet.
6. **The guidelines band lays out four-up at 1440px**, not the demo's three. The grid auto-fits a 16rem minimum, which is what keeps it readable from phone to wide desktop. Cosmetic.
7. **A covered garment is owner-only.** That is the layer walk, not a tier: a stranger sees the coat and not the shift beneath it, for the same reason the look command shows one and not the other.
8. **No disguise row on Physical.** The appearance section is already disguise-aware server-side (#1272), so the row would restate what the traits reflect.
9. **Holdings has no "Owed and Owing" block.** The spec asks for one, and neither half can be drawn. Every debt model in the world app is organization-to-organization (`currency.DebtInstrument`, `currency.OrgObligation`, `societies.OrganizationObligation`), so a character has no personal debt at all. Contracts DO have a model — `currency.Contract`, persona to persona, with collateral and garnishment — and no frontend surface anywhere in the app; Agreements covers wills, claims and settlements, not contracts. So the block would have to be built from nothing, which is its own issue.
10. **The worn outfit is not marked under Carried.** `Outfit` carries no worn flag, and inferring one would mean fetching every outfit's slots and comparing them to the equipped set: a query per outfit for a marker.
11. **The aura names no trend.** The spec's aura line asks for a trend as well as the split and the Glimpse state; the payload's aura carries the three shares and no history, so there is nothing to draw a trend from.
12. **The Mentors block is owner and staff only.** A Mentor's Vow is sworn inside a covenant, and the rest of what a covenant knows about a character is already owner-only on this page.

## Three open questions, recorded rather than guessed

Each is a ruling for Apostate, not unfinished building, and each is written into
`docs/roadmap/ROADMAP.md` and `docs/systems/character_sheets.md`:

- **What a stranger's rumor may say.** The band renders and is passed nothing.
- **Whether a look should follow the character's mood.** The plate no longer promises it,
  because `current_mood` is inward and owner-only (#2994) and a public portrait driven by
  it would publish exactly what that ruling protects.
- **Whether a gift should name its tradition.** `GiftEntry` carries no tradition field;
  tradition membership lives on the character rather than on the gift.

## Two visibility questions on Ties, left for a ruling

Neither is a defect and neither was introduced here, but both are visible in
`stranger-ties.png` and both deserve the maintainer's eye rather than a guess:

- **A non-owner sees no Standing at all.** The panel falls back to the renown card for
  anyone but the owner, which predates this issue (#1446), while the demo draws Standing
  for every viewer.
- **Covenant is owner-only**, although its query is already scoped to the character sheet
  and the Titles block beside it is public. The memberships and reputations queries ARE
  account-wide and would leak a viewer's own alts, so their gate is earned; Covenant's is
  inherited rather than reasoned.

## Two blocks the demo does not draw

Both came forward from the old sixteen-tab page rather than being added here, and both
now read in the sheet's own vocabulary rather than that page's utility classes.

- **Worship** at the foot of the Sheet section: the public faith line, the owner's Pray
  door, visions, and staff-only prayers.
- **A Tarot row** under At a glance.

Deleting a live feature to match a drawing is not this branch's call, so they are
re-skinned and recorded. Whether either belongs on the sheet at all is a ruling.

## A boundary drawn deliberately

The cards inside Holdings and Growth keep their own chrome: `BreakthroughsCard`, `ClassUnlocksCard`, `TrainingCard`, `DuranceCard`, `UpdatesTab`, `CrimeTab`, `LocationsTab` and `AgreementsPanel`. Three reasons, stated rather than left silent:

- the spec's build-order step 5 names six panels to re-skin, and all six are done;
- these are interactive forms, not reference reading, and the sheet's entry vocabulary is a reading vocabulary;
- `OwnedDwellingsCard` and `TenantedRoomsCard` are additionally shared with the Renown page, so re-skinning them would change a surface outside this issue.

It is recorded in `docs/roadmap/ROADMAP.md` and `docs/systems/character_sheets.md` as remaining, and it is the maintainer's call whether to extend the vocabulary to a tool surface. Where an empty-state card was purely presentational and reached only through the sheet, it went: the soul tethers, the renown shell and the XP ledger.

## Unresolved findings

None
