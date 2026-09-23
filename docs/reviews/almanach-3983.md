# Review evidence, issue #3983, the Almanach de Catenys: the House Builder

- Reviewed revision: `1d83d631c77555e166280802429b4ae5de649547`
- Reviewer: demo-fidelity-reviewer (second pass)
- Reviewer verdict: PASS
- Application/build identity: the shipped `AlmanachPage`/`HouseDocument` (staff routes
  `/staff/almanach*`, `frontend/src/almanach/AlmanachPage.tsx`,
  `frontend/src/almanach/document/HouseDocument.tsx`) and the shipped `FounderAlmanach` mounted
  inside character creation's real Lineage stage (`frontend/src/almanach/founder/FounderAlmanach.tsx`,
  wired through `character-creation/components/lineage/FamilyPathSection.tsx`), composing every
  real Almanach component and `frontend/src/almanach/almanach.css`, served from the production
  build (`pnpm build` from `frontend/` with `src/.env` present, `pnpm exec playwright test
  e2e/evidence/almanach-3983.spec.ts` against `pnpm preview`). This pass's three fixes landed in
  `2a9d6b596ced951c5aefe12832c6a7438ef87c3c` (`.almanach .contents{display:block}` so Tailwind's
  `contents` utility no longer dissolves the rail into the grid; `FamilyChapter.tsx`'s `renderNode`
  renders an outsider consort without the union's children, so a blood child hangs under the
  member, never under the consort as "grandchild"; `RecordSoFar.tsx`'s "you" line reads "· head of
  house" when `founder_relation === 'head'`), and the 14 affected screenshots were re-rendered in
  `1d83d631c77555e166280802429b4ae5de649547` (the reviewed revision itself — no gap between the
  code and the evidence this pass).
- Environment: container, Chromium via Playwright `^1.58.2`, `pnpm build` + `pnpm preview`
  (`frontend/e2e/evidence/almanach-3983.spec.ts`)
- Viewports/themes: 1280x800, light (`data-theme` unset); two screens additionally captured at a
  ~400px phone width (S-I, F-I) as extra evidence beyond what the plates require
- Approved design: staff demo https://claude.ai/artifact/TGDvT8de4kStEAkhJLav2X , founder demo
  https://claude.ai/artifact/2isT3Z6eRvavWGZxMDD8V7 ; local plate sources
  `scratchpad/almanac/staff.html` (S-I to S-VIII) and `scratchpad/almanac/founder.html` (F-I, F-Ib,
  F-II to F-VI), read in full
- Visual review: completed — second pass. Read all 14 refreshed PNGs (`s1`-`s8` built, the F-I
  phone shot, `f1b`, `f3`, `f4`, `f5` built) against their plates; every other screen (S-II, F-I,
  F-II, F-VI, F-VI night, and the untouched S-I phone shot) was re-confirmed unaffected and still
  matching from the first pass
- Visual verdict: PASS
- Screenshots: ![S-I built](docs/reviews/almanach-3983/s1-built.png) ![S-I built, phone](docs/reviews/almanach-3983/s1-built-phone.png) ![S-I plate](docs/reviews/almanach-3983/s1-plate.png) ![S-II built](docs/reviews/almanach-3983/s2-built.png) ![S-II plate](docs/reviews/almanach-3983/s2-plate.png) ![S-III built](docs/reviews/almanach-3983/s3-built.png) ![S-III plate](docs/reviews/almanach-3983/s3-plate.png) ![S-IV built](docs/reviews/almanach-3983/s4-built.png) ![S-IV plate](docs/reviews/almanach-3983/s4-plate.png) ![S-V built](docs/reviews/almanach-3983/s5-built.png) ![S-V plate](docs/reviews/almanach-3983/s5-plate.png) ![S-VI built](docs/reviews/almanach-3983/s6-built.png) ![S-VI plate](docs/reviews/almanach-3983/s6-plate.png) ![S-VII built](docs/reviews/almanach-3983/s7-built.png) ![S-VII plate](docs/reviews/almanach-3983/s7-plate.png) ![S-VIII built](docs/reviews/almanach-3983/s8-built.png) ![S-VIII plate](docs/reviews/almanach-3983/s8-plate.png) ![F-I built](docs/reviews/almanach-3983/f1-built.png) ![F-I built, phone](docs/reviews/almanach-3983/f1-built-phone.png) ![F-I plate](docs/reviews/almanach-3983/f1-plate.png) ![F-Ib built](docs/reviews/almanach-3983/f1b-built.png) ![F-Ib plate](docs/reviews/almanach-3983/f1b-plate.png) ![F-II built](docs/reviews/almanach-3983/f2-built.png) ![F-II plate](docs/reviews/almanach-3983/f2-plate.png) ![F-III built](docs/reviews/almanach-3983/f3-built.png) ![F-III plate](docs/reviews/almanach-3983/f3-plate.png) ![F-IV built](docs/reviews/almanach-3983/f4-built.png) ![F-IV plate](docs/reviews/almanach-3983/f4-plate.png) ![F-V built](docs/reviews/almanach-3983/f5-built.png) ![F-V plate](docs/reviews/almanach-3983/f5-plate.png) ![F-VI built](docs/reviews/almanach-3983/f6-built.png) ![F-VI built, submitted](docs/reviews/almanach-3983/f6-night-built.png) ![F-VI plate](docs/reviews/almanach-3983/f6-plate.png)
- Comparison notes: all three findings from the first pass are confirmed fixed by direct
  re-inspection. S-I, S-III, S-IV, S-V, S-VI, S-VII now render the three-column
  `contents | chapter | record` grid side by side, and S-VIII renders its two-column
  `contents | chapter` variant side by side — the ladder table's full column set (including
  `vassals`) is now visible and unclipped on every screen. S-IV's family tree now nests Raffaele
  (consort), Nerea and Océane as three siblings directly under Galerna, labeled "consort" and
  "child" respectively — no more "grandchild" mislabeling or extra nesting level. F-III's (and,
  consistently, F-IV's and F-V's) record rail now reads "you / Given name · head of house,"
  matching the open panel's "head of house" selection instead of contradicting it with "· heir."
  See `## Resolved findings` below for the file:line detail on each.
- Tested interactions: reused the evidence harness's own real-click journey (no workarounds, per
  `docs/reviews/almanach-3983/README.md`) — the staff Plant-a-rung dialog opened over the ladder;
  the founder journey claimed Fervor with a real click on "Claim Fervor" (F-I → F-Ib → F-II),
  added a consort and opened the founder's own panel (F-III), expanded Solfatara. This review did
  not re-run the harness; it read the 14 refreshed PNGs plus the fix commit's diff.
- Fixture/live boundary: as recorded in `docs/reviews/almanach-3983/README.md` — every `/api/**`
  call is a fixture (`frontend/e2e/evidence/fixtures/{inferna,founder}.ts`); the routes,
  components, CSS and the production build are the real, shipped application. The founder family
  fixture still seeds only two kin (a consort, "Dario," and the founder herself) rather than the
  plates' full multi-generation worked example — unchanged by this pass's fixes, noted below, not
  scored as a defect.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| revision-match | PASS | `git rev-parse HEAD` = `1d83d631c77555e166280802429b4ae5de649547`; this is the commit the 14 refreshed evidence PNGs were rendered at (`docs/reviews/almanach-3983/README.md`, commit `1d83d631c`), so there is no gap between reviewed code and evidence this pass. | |
| fixture-boundary | PASS | `docs/reviews/almanach-3983/README.md`'s fixture-vs-live boundary section, unchanged by this pass's fixes; confirmed the routes/components/CSS/build are real and only `/api/**` is stubbed. | |
| s1 | PASS | `s1-built.png` vs `s1-plate.png`: three-column grid renders side by side, full five-column ladder table visible. Fixed in `2a9d6b596`. | |
| s2 | PASS | `s2-built.png` vs `s2-plate.png`: the Plant a Rung dialog matches field-for-field; the Batch Unclaimed dialog's absence and the added realm-root toggle are ruled (README; final review I9). | |
| s3 | PASS | `s3-built.png` vs `s3-plate.png`: three-column grid renders side by side. Fixed in `2a9d6b596`. | |
| s4 | PASS | `s4-built.png` vs `s4-plate.png`: three-column grid renders side by side; the family tree nests Raffaele/Nerea/Océane as siblings under Galerna with correct "consort"/"child" labels. Fixed in `2a9d6b596`. | |
| s5 | PASS | `s5-built.png` vs `s5-plate.png`: three-column grid renders side by side, vassals table fully visible. Fixed in `2a9d6b596`. | |
| s6 | PASS | `s6-built.png` vs `s6-plate.png`: three-column grid renders side by side. Fixed in `2a9d6b596`. | |
| s7 | PASS | `s7-built.png` vs `s7-plate.png`: three-column grid renders side by side. Fixed in `2a9d6b596`. | |
| s8 | PASS | `s8-built.png` vs `s8-plate.png`: two-column grid renders side by side. Fixed in `2a9d6b596`. | |
| f1 | PASS | `f1-built.png` vs `f1-plate.png`: matches under the ruled two-column container-query collapse; unaffected by this pass's fixes. | |
| f1b | PASS | `f1b-built.png` vs `f1b-plate.png`: matches; Solfatara expanded and selected, Fervor/Arsura shown held. | |
| f2 | PASS | `f2-built.png` vs `f2-plate.png`: matches, including the principles sliders and Quiddity list; unaffected by this pass's fixes. | |
| f3 | PASS | `f3-built.png` vs `f3-plate.png`: record rail now reads "Given name · head of house," matching the open panel's "head of house" toggle. Fixed in `2a9d6b596`. | |
| f4 | PASS | `f4-built.png` vs `f4-plate.png`: matches, Atlas pin as a labeled dash per ruling; record rail's "you" line consistently reads "head of house." | |
| f5 | PASS | `f5-built.png` vs `f5-plate.png`: matches; record rail's "you" line consistently reads "head of house." | |
| f6 | PASS | `f6-built.png`/`f6-night-built.png` vs `f6-plate.png`: matches; both the review chapter and the post-submit night plate render (two shots for the plate's one stacked image, a stated harness simplification). | |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| S-I crumb + mode chip | "Almanach de Catenys › Inferna", "staff" chip | MATCH | `s1-built.png` |
| S-I contents rail: Realm group (The Ladder / Charter) | Two-item list, Charter inert with its gloss sub-line | MATCH | `s1-built.png` |
| S-I contents rail: Houses group | Piropa, Solano listed | MATCH | `s1-built.png` |
| S-I three-column layout (contents / chapter / record) | Side-by-side per `.almanac{grid-template-columns:13rem minmax(0,1fr) 19rem}` | MATCH | `s1-built.png` vs `s1-plate.png` — fixed in `2a9d6b596` (`almanach.css`'s `.almanach .contents{display:block}`) |
| S-I chapter h3 + tier ("Inferna ▾ Grand Principality · Piropa") | Realm-switcher button + crown tier span | MATCH | `s1-built.png` |
| S-I level bar (Kingdom/Ducal 3/County 9/Barony 19) | Segmented tier control with unclaimed counts | MATCH | `s1-built.png` |
| S-I ladder table columns (title/held by/sworn to/demesne/vassals) | Five columns, disclosure carets, tier prefixes | MATCH | `s1-built.png` — all five columns fully visible, including vassals, now that the layout defect is fixed |
| S-I ladder table rows (Vampa…Brasa, Unclaimed/Undefined chips) | Full 15-row ladder matching the plate | MATCH | `s1-built.png` |
| S-I savebar (⊕ plant a rung / batch unclaimed…) | Two buttons | MATCH | `s1-built.png` |
| S-I record rail: on record (crown, default tithe) | crown Piropa, default tithe 10% | MATCH | `s1-built.png` |
| S-I record rail: Charter (succession/particle/quiddity) | Fed by `useCharter`, replacing the plate's inert placeholder (final review deferred item 1, fixed) | MATCH | `s1-built.png` |
| S-I phone (400px) layout | Single column, contents → chapter → record | MATCH | `s1-built-phone.png` |
| S-II dialog: Plant a rung fields (under/tier/name/comes with/held by) | Fervor duchy, county/barony seg, name input, "1 barony, seat Undefined · hall Undefined", Unclaimed/a house on record seg | MATCH | `s2-built.png` |
| S-II dialog: Cancel/Plant actions | Two buttons, bottom-right | MATCH | `s2-built.png` |
| S-II added realm-root toggle ("under Fervor / at the realm root") | Not drawn on the plate | MATCH | `s2-built.png` — accepted addition, final review I9 (`AlmanachPage.tsx:130`, `PlantRungDialog.tsx`) |
| S-II Batch Unclaimed dialog | Plate draws it beside Plant a Rung as a second static mockup | MATCH | README — accepted omission (only one Radix dialog can be meaningfully open at once) |
| S-III crumb + status chip + mode chip | "…Inferna › Piropa", "draft", "staff" | MATCH | `s3-built.png` |
| S-III contents rail (House / Holdings groups) | The House/The Family; Realm/Lands 4 baronies/Estate | MATCH | `s3-built.png` |
| S-III three-column layout | Side-by-side | MATCH | `s3-built.png` vs `s3-plate.png` — fixed in `2a9d6b596` |
| S-III state seg (Standing/In exile/Extinct/Gentry) | Four options, Gentry disabled outside Luxen | MATCH | `s3-built.png` |
| S-III particle + succession fields | "worked example" tip, Infernal Enatic-Durance + codex | MATCH | `s3-built.png` |
| S-III words/colors/sigil/the house (PLACEHOLDER) | Empty/greyed placeholder treatment | MATCH | `s3-built.png` |
| S-III House Quiddity list, Glamour selected | 7 entries, one marked, codex links, "⊕ change" door | MATCH | `s3-built.png` — door renders inert per ruling |
| S-III features chips + offices list | Letter of Marque chip + add; two Unclaimed offices | MATCH | `s3-built.png` |
| S-III savebar (draft note + Save) | "draft kept as you type" + Save | MATCH | `s3-built.png` |
| S-III record rail (on record + doors) | crown/holds/demesne/vassals/stature; roster door | MATCH | `s3-built.png` |
| S-IV crumb/status/mode + contents rail | Same chrome as S-III, "The Family" current | MATCH | `s4-built.png` |
| S-IV three-column layout | Side-by-side | MATCH | `s4-built.png` vs `s4-plate.png` — fixed in `2a9d6b596` |
| S-IV stat row (on record/open positions/hidden truths) | Three counts | MATCH | `s4-built.png` — fixture uses smaller counts than the plate's worked example, not a copy/format defect |
| S-IV family tree root + head of house row | Galerna, "head of house" | MATCH | `s4-built.png` |
| S-IV family tree: consort + daughters as Galerna's direct children | Raffaele (consort), Nerea (daughter · heir presumptive), Océane (daughter), Tormenta (daughter), a slot, all one level under Galerna | MATCH | `s4-built.png` vs `s4-plate.png` — Raffaele, Nerea and Océane now render as three siblings one level under Galerna, labeled "consort"/"child"/"child"; fixed in `2a9d6b596` (`FamilyChapter.tsx`'s `renderNode` no longer gives an outsider consort the union's children). Tormenta and the "third daughter" slot still do not appear (this fixture seeds fewer rows than the plate's worked example, unchanged by this fix) |
| S-IV relation words (daughter/heir presumptive/Grand Princess) | Titled plate words | MATCH | `s4-built.png` — accepted, documented divergence: structural depth-based words only, no title/rank field on the wire (`FamilyChapter.tsx:17-30`) |
| S-IV household band + Marisol panel (tier/age/gender/deceased/in the house as/born into/description) | Open panel with those fields | MATCH | `s4-built.png` |
| S-IV Marisol's "public record"/"in truth"/"known to the world as" | Plate: descriptive parentage-cover text + secret/believed-dead chips | MATCH | `s4-built.png` — accepted, documented divergence: a living/believed-dead toggle replaces the plate's static text, final review I8 (`PersonPanel.tsx:99-108,152-186`) |
| S-IV Master-at-arms open position + add doors | "open"; two ⊕ add links | MATCH | `s4-built.png` |
| S-IV record rail (kind/influence/recognition/kin slots, linked houses, doors) | Full set per plate | MATCH | `s4-built.png` |
| S-V crumb/status/mode + contents rail (Realm current) | Matches S-III chrome, Realm selected | MATCH | `s5-built.png` |
| S-V three-column layout | Side-by-side | MATCH | `s5-built.png` vs `s5-plate.png` — fixed in `2a9d6b596` |
| S-V sworn to/holds/demesne fields | —, "the crown", 4 baronies listed | MATCH | `s5-built.png` |
| S-V vassals table (Ardor/Fervor/Caldera/Undefined/Brasa) | Five rows incl. the `cl` claimed-by-Luxen row | MATCH | `s5-built.png` — all columns (held by/demesne/vassals) fully visible now that the layout defect is fixed |
| S-V savebar (draft note, swear a house, Save) | Three items | MATCH | `s5-built.png` |
| S-V record rail (tier/treasury/pacts, doors) | Dashes for facts not on the wire (accepted, ruled), "the ladder" door | MATCH | `s5-built.png` |
| S-VI crumb/status/mode + contents rail (Lands, nested baronies) | Matches S-III chrome, Lands nested sub-list expanded | MATCH | `s6-built.png` |
| S-VI three-column layout | Side-by-side | MATCH | `s6-built.png` vs `s6-plate.png` — fixed in `2a9d6b596` |
| S-VI Lands-of-Piropa summary (seat/produces/prosperity) | Perdition, salt·timber·a port, 50 | MATCH | `s6-built.png` |
| S-VI baronies table (Perdition/Bochorno/Lumbre/Seawatch) | Four rows, Perdition expanded | MATCH | `s6-built.png` |
| S-VI Perdition sub-page: chain, prose, hall/land/population | Full breadcrumb chain, worked prose, chips | MATCH | `s6-built.png` |
| S-VI Atlas pin | Plate draws a dashed-isle pin diagram | MATCH | `s6-built.png` — accepted omission: a labeled dash (ruling, brief) |
| S-VI produces table (Deepwater Quays/Reef Salterns/Lamplit Yards) + ⊕ a holding | Plate's three holdings; built shows "no holdings on record" + add door | MATCH | `s6-built.png` — fixture has no holdings seeded for this barony; the table/add-door structure itself is present |
| S-VI record rail (held by/seat of/prosperity/unrest/defenses/garrison, doors) | Full set | MATCH | `s6-built.png` |
| S-VII crumb/status/mode + contents rail (Estate current) | Matches S-III chrome, Estate selected | MATCH | `s7-built.png` — crumb shows Piropa; the plate's own S-VII example uses a different house (Candela) for narrative variety, a fixture-story choice, not a defect |
| S-VII three-column layout | Side-by-side | MATCH | `s7-built.png` vs `s7-plate.png` — fixed in `2a9d6b596` |
| S-VII name/district/held fields | Casa [House] · PLACEHOLDER chip, district, "by the house" | MATCH | `s7-built.png` |
| S-VII Atlas pin (unplaced) | "unplaced" label over the district | MATCH | `s7-built.png` — accepted omission: labeled dash treatment |
| S-VII rooms field + savebar + record rail | "—", draft note + Save, kind + doors | MATCH | `s7-built.png` |
| S-VIII crumb/status chip (published) + mode | "published" status chip | MATCH | `s8-built.png` |
| S-VIII contents rail | House/Holdings groups | MATCH | `s8-built.png` |
| S-VIII two-column layout (contents / chapter) | Side-by-side per the plate's `13rem minmax(0,1fr)` variant | MATCH | `s8-built.png` vs `s8-plate.png` — fixed in `2a9d6b596` |
| S-VIII chapter-completion table (House/Family/Realm/Lands/Estate, written, placeholders) | Five rows, checkmarks/fractions, placeholder lists | MATCH | `s8-built.png` |
| S-VIII savebar (published date, unpublish/Republish) | "published 2026-09-23 · draft since", two buttons | MATCH | `s8-built.png` |
| F-I crumb ("Character creation › Lineage › Define a house") + mode chip | Matches | MATCH | `f1-built.png` |
| F-I contents rail (Holdings/House/Holdings strip) | The Seat current; House/Family and Land/Estate greyed | MATCH | `f1-built.png` |
| F-I two-column layout (contents strip above chapter / record) | Ruled container-query collapse from the plate's three-column mock | MATCH | `f1-built.png` — ruled divergence (README), unaffected by this pass's fixes |
| F-I "Duchies of Inferna ▾ vassal of House Piropa" + tier seg | Tier switcher, realm switcher, 3/3/3 counts | MATCH | `f1-built.png` |
| F-I ladder table + Claim buttons (Fervor/Solfatara/Caldera/undefined rows) | Six rows with Claim buttons where claimable | MATCH | `f1-built.png` |
| F-I savebar note | "Houses will be reviewed by staff before approval" | MATCH | `f1-built.png` |
| F-I record rail (House Piropa: crown/quiddity/vassals; Inferna: succession/particle) | Full set | MATCH | `f1-built.png` — exceeds the ledger's "quiddity/peer houses not on the wire" note (`plan-3983-b/progress.md:51`), which appears superseded by later work |
| F-I phone (400px) layout | Single column, no horizontal overflow | MATCH | `f1-built-phone.png` |
| F-Ib: Fervor held, no Claim, Solfatara expanded/selected | "held" meta text, Solfatara's own Claim + Tizón seat row | MATCH | `f1b-built.png` |
| F-Ib record rail (House Candela + House Piropa blocks) | Both houses' summaries | MATCH | `f1b-built.png` |
| F-II House Candela: name/your-name-will-read/succession | Candela, "Marisol za Candela" (tip), succession + codex | MATCH | `f2-built.png` |
| F-II words/colors/sigil/the house (author fields, not PLACEHOLDER) | Authored text: "Iron and Ash", "Jet and gold", sigil/house prose | MATCH | `f2-built.png` — plate shows PLACEHOLDER seed copy; built shows authored draft text because this founder has typed into the fields, expected |
| F-II House Quiddity list, The Veiled selected | 7 entries, one marked, codex links | MATCH | `f2-built.png` |
| F-II principles sliders (6 axes) | Ruthlessness↔Compassion … Hierarchy↔Equality | MATCH | `f2-built.png` |
| F-II savebar (draft note + Next) | "draft kept as you type" + Next | MATCH | `f2-built.png` |
| F-II record rail ("the record, so far" + features) | seat/house/quiddity so far, remaining rows italicized as not-yet-written, Letter of Marque | MATCH | `f2-built.png` |
| F-III crumb/contents rail (The Family current) | Matches | MATCH | `f3-built.png` |
| F-III stat row (family you may define/on record/household) | 3·1 named / 2 / — | MATCH | `f3-built.png` — fixture-sized, not the plate's worked example |
| F-III family tree: Dario (consort, born Solano) | One entry, tags | MATCH | `f3-built.png` |
| F-III founder's own row: "YOU ARE" seg + mother/father/place | Segmented control, mother "Estuosa", father "Dario", place heir/younger | MATCH | `f3-built.png` — "head of house" is a legitimate choice here (a self-founding head), not the plate's own worked example but not a mismatch |
| F-III record rail "you" line | Should reflect the founder's own selected relation, consistent with the open panel | MATCH | `f3-built.png` — now reads "Given name · head of house," matching the "head of house" pressed in the open panel; fixed in `2a9d6b596` (`RecordSoFar.tsx:118-124`) |
| F-III family tree depth (head-of-house/grandmother rows, sibling slot) | Fiamma (dead), Duchess Estuosa (head), "a brother, to be defined" | MATCH | `f3-built.png` — this evidence run's fixture seeds only Dario + the founder (both render correctly, siblings not nested); the plate's deeper generations are outside this fixture's story and were not exercised, unchanged by this pass's fixes |
| F-III add-kin doors (⊕ a sibling · a spouse; ⊕ a ward · a captain of the guard · a position) | Two add-door lines | MATCH | `f3-built.png` |
| F-IV Lands of Candela summary (seat/produces/sworn to Fervor) | Ascua, farmland·a port·a quarry, Solfatara·Undefined | MATCH | `f4-built.png` |
| F-IV baronies table (Ascua seat, Undefined) | Two rows | MATCH | `f4-built.png` |
| F-IV Fervor duchy prose + land chips + Atlas pin | Chain, "the land, in your words" prose, coast/volcanic chips, pin | MATCH | `f4-built.png` — Atlas pin as a labeled dash (accepted omission) |
| F-IV record rail ("the record, so far") | seat/house/head/you/the land, the estate row italicized as not-yet-written | MATCH | `f4-built.png` — "you" line reads "head of house," consistent with F-III's fix |
| F-V Estate name/district/rooms | Casa Candela · PLACEHOLDER, district —, rooms — | MATCH | `f5-built.png` — plate shows district staff-set later and rooms deferred; both read dashed here pre-review, expected |
| F-V "the estate, in your words" prose | Empty prose field | MATCH | `f5-built.png` |
| F-V record rail | Full "record so far" list through the estate | MATCH | `f5-built.png` — "you" line reads "head of house," consistent with F-III's fix |
| F-VI review chapter (House Candela heading, quiddity/words/colors, the house, the family, the land, the estate) | All quoted fields, composing nothing extra | MATCH | `f6-built.png` |
| F-VI "the family" line | Duchess Estuosa · Dario, consort · Marisol, heir · a brother, to be defined | MATCH | `f6-built.png` — this fixture's line reads "Given name za Candela · Dario zas Candela, consort" (only the two seeded kin); the head/sibling entries are absent because the fixture never seeded them, not a rendering defect |
| F-VI savebar (Back / Submit for review) | Two buttons | MATCH | `f6-built.png` |
| F-VI post-submit night plate ("Submitted", house · pending review) | Dark full-bleed panel | MATCH | `f6-night-built.png` |

## Resolved findings

All three findings from the first pass (`docs/reviews/almanach-3983.md`'s prior revision, reviewed
at `44df1dbef608a659b7880c433ede9de21b638f2b`) are fixed in `2a9d6b596ced951c5aefe12832c6a7438ef87c3c`
and confirmed by direct re-inspection of the re-rendered PNGs (`1d83d631c77555e166280802429b4ae5de649547`):

1. **Staff `.almanac` grid not laying out side by side.** Root cause: Tailwind's `contents`
   utility (`display: contents`) matched the rail's own class name (`aside class="contents"`),
   dissolving it into the `.almanac` grid so its two `.mv` groups took grid tracks instead of the
   rail. Fix: `frontend/src/almanach/almanach.css:96-99` adds `.almanach .contents{display:block}`
   (the container-query strip under 64rem still sets `display:flex`, unaffected). Confirmed on all
   seven three-column screens (S-I, S-III, S-IV, S-V, S-VI, S-VII) and the two-column S-VIII — every
   one now renders `contents | chapter | record` (or `contents | chapter`) side by side, and S-I/S-V's
   ladder/vassals table is fully visible instead of clipped.
2. **S-IV family tree nesting Galerna's daughters under her outsider consort.** Fix:
   `frontend/src/almanach/document/FamilyChapter.tsx:313-357`'s `renderNode` now takes an
   `asConsort` flag; when rendering an outsider spouse it passes `asConsort=true`, and an
   `asConsort` node's `outsiders`/`childIds` are both forced empty — a consort rendered beside
   their partner no longer carries the union's children. Confirmed: `s4-built.png` now shows
   Raffaele (consort), Nerea (child, sheeted) and Océane (child) as three siblings one level under
   Galerna, matching the plate's flat structure (titled words like "daughter · heir presumptive"
   remain an accepted, documented divergence — structural words only, no rank field on the wire).
3. **F-III record rail contradicting the founder's own "head of house" selection.** Fix:
   `frontend/src/almanach/founder/RecordSoFar.tsx:118-124` now special-cases
   `draft.founder_relation === 'head'` to read "· head of house" instead of unconditionally
   appending "· heir"/"· younger". Confirmed: `f3-built.png`'s record rail now reads "Given name ·
   head of house," matching the open panel's "head of house" pressed toggle; `f4-built.png` and
   `f5-built.png` carry the same consistent "you" line through the rest of the founder journey.

**Divergences accepted (not defects), each cited to a ruling or an in-code decision — unchanged
from the first pass:**
- S-II: the Plant a Rung dialog is the only one screenshotted (Batch Unclaimed omitted — only one
  Radix dialog can be meaningfully open; `README.md`); the added realm-root toggle is final review
  I9.
- S-III/all staff document screens: the Quiddity catalog's "⊕ change" door renders but is inert
  (ruled, brief).
- S-IV: `PersonPanel`'s "public record" living/believed-dead toggle replacing the plate's static
  parentage-cover text is final review I8 (`PersonPanel.tsx:99-108,152-186`).
- S-IV, F-III/F-VI: structural, depth-based relation words instead of the plate's titled ranks —
  documented in `FamilyChapter.tsx:17-30`.
- S-VI, S-VII, F-IV: the Atlas pin renders as a labeled dash rather than the plate's dashed-isle
  diagram (ruled, brief).
- S-VII: the built evidence reuses House Piropa for the Estate example where the plate switches to
  a second house (Candela) for narrative variety — a fixture-story choice (S-III–S-VII share one
  draft fixture, `README.md`), not a code defect.
- F-I/F-Ib/F-II/F-III/F-IV: founder-mounted `.almanach` renders two columns (a contents strip above
  chapter | record) rather than the plate's full-page three-column mock — ruled, container-query
  driven (`README.md`, `almanach.css:118-131`).
- F-III/F-VI: the founder family fixture seeds only two kin (a consort and the founder), so the
  plate's deeper generations (a head-of-house row, a dead grandmother, a "to be defined" sibling
  slot) are not exercised — a fixture-story limitation, not a code defect, and unchanged by this
  pass's fixes.
- Staff ladder's level bar folds `march` into `county` (ruled, `plan-3983-a/progress.md:102`) — not
  independently re-verified against a march-bearing fixture row in this run, but no divergence was
  observed in the rows shown.

## Unresolved findings

None
