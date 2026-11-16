# Character Creation Frontend

This module provides the staged character creation UI flow.

## Structure

```
character-creation/
├── index.ts                 # Public exports
├── types.ts                 # TypeScript type definitions
├── constants.ts             # MAGIC_SKILL_CATEGORY: Magic skills are spent from the Gift
│                              #   stage's magical training (read-only group in SkillsSection,
│                              #   #4457, #4659), never bought with skill points
├── api.ts                   # API fetch functions using apiFetch
├── queries.ts               # React Query hooks
├── cg.css                   # Scoped under `.interview`; realm is an ink, paper
│                              #   pinned to Arx (#3540)
├── CharacterCreationPage.tsx # Main page component
├── folio/                   # Folio chassis primitives (#3540), realm-agnostic
│   ├── index.ts             # Barrel re-export
│   ├── ContentsRail.tsx     # Chapter table of contents; replaces StageStepper
│   ├── PageTurn.tsx         # Back/next doors between chapters
│   ├── NightPlate.tsx       # Full-bleed night moment (arrival, submission)
│   ├── ChapterLeaf.tsx      # Wraps a stage's old internals in the leaf frame; `railSlot`
│   │                        #   keeps the right-hand rail for a panel the stage sends there
│   ├── chapterRail.ts       # `useChapterRail()`: the rail element a panel portals into (#5144)
│   ├── RecordRail.tsx       # Marginalia: the "CG selections" rows + a Note aside
│   ├── Entry.tsx            # EntryList/Entry/EntryDoors: choosable record entries (an
│   │                        #   optional `tags` list prints extra `.tag`s beside `tag`). Since
│   │                        #   #4022 the name row carries a square Select mark (Selected
│   │                        #   once chosen, a second press clears; never toggles the
│   │                        #   disclosure) and a chosen row is tinted in the realm accent;
│   │                        #   the foot keeps one door, Select before and Clear after
│   ├── InstrumentFrame.tsx  # InstrumentGroup/StatRow: labeled stat instruments
│   ├── ChoiceRow.tsx        # Segmented choice: a few named options, one pressed (#3630)
│   ├── Field.tsx            # Inscription label over a serif control on a hairline (#3630)
│   ├── Paragraphs.tsx       # Blank-line-separated prose split into <p> tags (#3630)
│   ├── CodexWord.tsx        # In-world term linked via CodexTerm when a codex entry exists
│   ├── CodexLine.tsx        # "Codex: {name}" ledger line in an entry body (solid link; an
│   │                        #   optional `note` such as a cost reads after it); nothing without either
│   └── ConfirmDialog.tsx    # Native <dialog> confirm for record-clearing choices
└── components/
    ├── index.ts             # Component exports
    ├── OriginStage.tsx      # Stage 1: Area selection; since #4874 the first name is asked
    │                        #   here too (a Field above the realms, boxed while empty, saved
    │                        #   on blur by itself, listed first in the rail), so the life
    │                        #   reads the name; the letters-only rule shows only under a
    │                        #   refused name, and a refused name is not saved
    ├── HeritageStage.tsx    # Stage 2: beginnings (station on the closed row, cost on the
    │                        #   codex line), species, gender
    ├── LineageStage.tsx     # Stage 3: the beginning's route (#3617; the Upbringing pick
    │                        #   retired in #4395, the route comes with the beginning),
    │                        #   family selection, the life grids (no spouse, child or
    │                        #   twin: those come after creation, ADR-5102-A); keeps
    │                        #   InventedParentsCard, FamilyNamePreview, KinSlotPicker,
    │                        #   TarotNamingRitual, TarotCardItem, FamilyCard (exported
    │                        #   for lineage/). KinSlotPicker (#5130) is the open seats
    │                        #   of the claimed family and the only way into it: no free
    │                        #   card; a seat reads its relation to the head of the house
    │                        #   (`head_relation` + the response's `head_name`), then its
    │                        #   description; a changeable name carries an asterisk, a
    │                        #   fixed one nothing; a second press clears the pick.
    │                        #   HouseFoundingPanel retired (#3983 Plan B
    │                        #   Task 6) — claim-path house founding is
    │                        #   `almanach/founder/FounderAlmanach.tsx`, mounted from
    │                        #   `FamilyPathSection.tsx`.
    ├── PathStage.tsx        # Stage 5: Path selection
    ├── SkillsSection.tsx    # Skill point allocation, mounted inside AttributesStage
    ├── AttributesStage.tsx  # Stage 7: Attributes & Skills (mounts SkillsSection)
    ├── GiftStage.tsx        # Stage 6 (Gift): vertical funnel — Tradition → Gift →
    │                        #   [magical training, #4659] → Techniques → Gift Resonance
    │                        #   (several resonances weighted by points, #5123: opens with
    │                        #   text on what resonance is, point steppers against the
    │                        #   server's `resonance_creation_points`, a live halo in words;
    │                        #   saves `draft_data.gift_resonance_weights`, a partial spread
    │                        #   may be saved but the step stays open until every point is
    │                        #   placed; `resonanceWeights.ts` holds the pure helpers)
    │                        #   → Anima Check, plus an
    │                        #   always-visible Motif textarea and the guided Glimpse
    │                        #   flow (#2426 Task 10; Glimpse redesign #2427)
    ├── AppearanceStage.tsx  # Stage 8: Appearance. After the height block, mounts this
    │                        #   chapter's own offered distinctions (ChapterOffers
    │                        #   chapter="appearance", #3675 Task 15), the physical/social
    │                        #   ones that show, in place of the retired Distinctions stage.
    │                        #   A height band's title reads its own authored `cg_hint`
    │                        #   column (forms.HeightBand, #3675 fix round 1) when staff
    │                        #   wrote one - e.g. what opens a band players cannot normally
    │                        #   take - never a name match against a literal band name.
    ├── IdentityStage.tsx    # Stage 9: Identity (concept, quote, background, worship); the
    │                        #   name is a read-only line since #4874, asked on Origin
    ├── FinalTouchesStage.tsx # Stage 10: the Actor's Sheet (#3621): three questions,
    │                        #   numbered goals by horizon, the priced enemy, The Introductions.
    │                        #   Directly under the three questions mounts this chapter's own
    │                        #   offered distinctions (ChapterOffers chapter="actors_sheet",
    │                        #   #3675 Task 15), the personality-flavored ones each prompt
    │                        #   answers. Between the questions and the goals, the
    │                        #   card-unlocked chapter (#4846, slice 5 of #4813): the lines
    │                        #   a held card unlocks (ChapterOffers chapter="final_touches")
    │                        #   and the prompt a held card asks (draft.final_touches_prompts;
    │                        #   `crime` is Jailbird's: a select over draft.crime_kinds and a
    │                        #   500-character line, saved as draft_data.crime in the stage's
    │                        #   one PATCH, null when no kind is picked). The asks the grant
    │                        #   sidecars raise (#4852, slice 6 of #4813: draft.final_touches_cards)
    │                        #   each get a block under the card's name: a prestige card's story
    │                        #   (500 characters, draft_data.prestige_stories keyed by card id,
    │                        #   a blank one dropped), the organization a card seats you in (a
    │                        #   select over draft.organization_choices with "None" first,
    │                        #   draft_data.organizations, null for None), Capable Mentor's line
    │                        #   naming the Path's stronger Aspect from the ask's detail (nothing
    │                        #   to answer), and a card's organization tie (#4856: a select over
    │                        #   the ask's choices with "None" first, then the kind as a
    │                        #   ChoiceRow, membership or renown; draft_data.ties keyed by card
    │                        #   id, null for None). The section is absent when no held card
    │                        #   unlocks or asks anything. The Officially dead door (#4396)
    │                        #   renders only when the prompts include officially_dead (#4856:
    │                        #   Presumed Dead's card), and a second door of the same shape,
    │                        #   "A second face", when they include alter_ego (saved as
    │                        #   draft_data.alter_ego, null when skipped); both share FaceForm.
    ├── ReviewStage.tsx      # Stage 11: Review and submit
    ├── FinalizeForTableDialog.tsx # Player-GM direct-to-roster flow from ReviewStage (#3268)
    ├── TraditionPicker.tsx  # Traditions as entries — mounted inside gift/TraditionStep
    ├── PerspectivesPanel.tsx # "On {subject}" shop-window opinions; renders as margin
    │                        #   notes in HeritageStage and inside the chosen tradition's
    │                        #   entry in TraditionPicker (#3281, #3630)
    ├── gift/                # GiftStage funnel steps (#2426 Task 10)
    │   ├── TraditionStep.tsx    # Wraps TraditionPicker
    │   ├── ResonanceWeights.tsx # The Resonance step body (#5123): a stepper per resonance,
    │   │                        #   the points left, and the `AuraHalo` (`@/magic/components`)
    │   │                        #   of the spread in words
    │   ├── GiftSelector.tsx     # Gifts as entries (GET .../gifts/?draft_id=); a Gift the
    │   │                        #   Tradition favors is tagged "Teaches well" (#4659)
    │   ├── MagicTrainingBlock.tsx # Body of GiftStage's own "What <Tradition> taught you"
    │   │                        #   funnel step (#4659), after the Resonance step, gated on
    │   │                        #   a Gift and a resonance (its bonuses read both), open
    │   │                        #   until the pool is spent exactly: the breakdown
    │   │                        #   ("<distinction>, rank N" sources, the rank only when
    │   │                        #   `show_rank`; "Fits:" bonuses,
    │   │                        #   total), a "Spend all of it" ledger flagged when under or
    │   │                        #   over, and a StatRow per Magic skill writing
    │   │                        #   draft_data.magic_skills. The step is absent with no
    │   │                        #   training and nothing allocated (`magicTraining.ts`)
    │   ├── StyleStep.tsx        # The fighting style step (#4921), after the Resonance and
    │   │                        #   only for a Tradition that teaches a style (GET
    │   │                        #   .../combat-styles/?draft_id=): each style's defense style,
    │   │                        #   description and an Attacks/Defends profile read in the
    │   │                        #   closed entry (Entry's `profile` slot; the lines in
    │   │                        #   `styleLines.ts`), never its vows; saves
    │   │                        #   selected_combat_style_id. The training step waits on it
    │   ├── TechniqueSelector.tsx # Technique catalog, grouped by category, budget-capped
    │   ├── AnimaCheckStep.tsx   # Anima Check stat/skill pick + ritual name
    │   ├── GlimpseSection.tsx   # CG state binder for the Glimpse (#2427): draft reads,
    │   │                        #   updateDraft writes (draft_data.glimpse_tag_ids), the
    │   │                        #   isCollapsed deferral affordance, the copy query. Prose
    │   │                        #   stays on GiftStage's register('glimpse_story'). Renders
    │   │                        #   `GlimpseAxes`, not the shared
    │   │                        #   `@/magic/components/glimpse/GlimpseFlow` (#3675 fix
    │   │                        #   round 1: that shared component's shadcn accordion hid
    │   │                        #   two axes at a time; the sheet's live editor still uses
    │   │                        #   it, unchanged)
    │   └── GlimpseAxes.tsx      # CG-only folio-grammar layout for the Glimpse (#3675 fix
    │                            #   round 1): one `.field` per axis, all visible at once,
    │                            #   `.picks` pill buttons per tag, and one `ChapterOffers`
    │                            #   `.conditional` sub-block PER SELECTED TAG (not per
    │                            #   axis: two tags chosen on one multi-select axis each
    │                            #   get their own heading, matching the demo). No heading
    │                            #   of its own; GiftStage's `section-h` above the mount
    │                            #   carries it. Each sub-block passes ChapterOffers a
    │                            #   headingTag ("optional"); a route-closed distinction is
    │                            #   absent and named nowhere (#4979).
    └── lineage/             # LineageStage subsections (#3617, #3648, #4395)
        ├── (KinRows.tsx retired, #5102) The named parents' fates (#4870) are a select
        │                         #   under each parent's gender in LineageStage
        │                         #   (ParentFateRow; draft_data.line_parent_fate /
        │                         #   other_parent_fate)
        ├── LifeGrids.tsx         # The life as an accordion (#4874, slice 9 of #4813, built
        │                         #   against the demo): one fold per stage (heading + "N of
        │                         #   M" or Unknown, one open at a time, a click on the open one
        │                         #   folds it), one section per beat inside (a closed one reads
        │                         #   its answers with signed points or the prompt with the
        │                         #   first name; Next walks down and into the next stage);
        │                         #   every grid ends on an Amnesiac card (#5102: no cost, not a
        │                         #   distinction, copy life_amnesiac_name/_text) that marks
        │                         #   its own beat unknown; the secret marks under a grid, the Cover story box
        │                         #   on a one-of row (the no-cost card is saved as the cover when
        │                         #   the secret is marked, until a click on another card;
        │                         #   clicking the real pick drops both)
        │                         #   and a cover select on an any row; a figure's name input
        │                         #   on a picked person card; Description (Optional) per stage
        │                         #   (draft_data.stage_descriptions); the ledger, sent to
        │                         #   the chapter's rail (#5144); the testament paragraph.
        │                         #   Earlier shape, still true underneath: grids by stage
        │                         #   (#4395, the #4124 beats):
        │                         #   one block per stage the beginning offers (a struck
        │                         #   stage is absent), each beat a `ChapterOffers`
        │                         #   `layout="grid"` of its `backgrounds` offers picked
        │                         #   straight from the cards, the pick line from the
        │                         #   entry's `allowance` (one, N career points on a beat
        │                         #   whose `allowance_is_points` is on (#4829: a ranked
        │                         #   card shows pips, `ChapterOffers` `pointsPicks`), any),
        │                         #   a line of the player's own once a card
        │                         #   is picked; the footer counts the
        │                         #   taken beats and the purse. Every life ends on the
        │                         #   Recent History box (#4831), a textarea saved on blur
        │                         #   to draft_data.recent_history; a beginning that
        │                         #   strikes every stage shows its struck_stages_text
        │                         #   where the stages would be, over the box, with no
        │                         #   footer. Replaces BeatsBlock. The suggested life
        │                         #   (#4867, slice 7 of #4813): once the beats load, an
        │                         #   effect calls useLoadDefaultLife when the draft has a
        │                         #   beginning its draft_data.life_loaded_for stamp does
        │                         #   not name (a ref stops a second call per mount; the
        │                         #   server's stamp is the durable guard); a "Start blank"
        │                         #   button in the footer calls useClearLife. Both hooks
        │                         #   replace the draft cache and refetch the distinctions,
        │                         #   beats, Backgrounds offers and CG points.
        ├── UpbringingPrompts.tsx # Route prompts; `scope: 'any'` renders the pick-lists
        │                         #   asked on every path (a general write-in never
        │                         #   renders, #4395), `scope: 'path'` renders below the
        │                         #   family block, scoped to the resolved family path;
        │                         #   write-in ->
        │                         #   draft_data.origin_slots, pick-list ->
        │                         #   draft_data.origin_choices, priced off influence.
        │                         #   Each priced answer prints an `offers X` / `bundles Y`
        │                         #   line off its own `AnswerOffer[]` (#3675 Task 14); the
        │                         #   CHOSEN answer alone, when it carries a CHOICE offer,
        │                         #   mounts a `ChapterOffers` block right after the answers
        │                         #   list (`chapter="lineage"`, filtered to its own choice's
        │                         #   `offer_id`s - never by name/label, #3676 - `className=
        │                         #   "conditional"` merged onto ChapterOffers's own `.field`,
        │                         #   its bundled offers passed through as locked stances). A card
        │                         #   the route closes is absent and named nowhere (#4979).
        ├── FamilyPathSection.tsx # Path picker (when the Upbringing allows more than
        │                         #   one) plus the claim/name/none path UI; renders
        │                         #   FamilyTemplateForm (name path), VacancyPicker
        │                         #   (claim path's kin Vacancies), ServicePanel (any
        │                         #   path's retainer Vacancies), InheritedFactsPanel
        │                         #   (claim path). Reads the Upbringing's `parentage`
        │                         #   (#4024): `unknown` renders only the tarot ritual
        │                         #   (under copy `tarot_no_parents_intro`) and Service,
        │                         #   no family heading or parents card; `adoptive`
        │                         #   heads the section `adoptive_family_heading` and
        │                         #   titles the parents card "Your adoptive parents".
        │                         #   Path labels are "An established family" / "Your
        │                         #   own family" / "No family"; with the first two
        │                         #   offered and none chosen, your own is open by default.
        │                         #   Since #5130 the claim path lists only families with
        │                         #   `has_open_seat` (plus the one the draft holds), shows
        │                         #   the seat picker under the Vacancy heading, and never
        │                         #   the parents card (a seat's parents are staff's)
        ├── FamilyTemplateForm.tsx # Aspect-pick + features form for a Family Template,
        │                         #   used by the name path (#3648); the claim path's
        │                         #   own charter form is
        │                         #   `almanach/founder/FounderHouseChapter.tsx` (#3983
        │                         #   Plan B)
        ├── VacancyPicker.tsx     # Renders reachable Vacancies (description, importance,
        │                         #   presumed importance, price, remaining) for pick
        ├── ServicePanel.tsx      # Retainer Vacancies reachable from this Upbringing,
        │                         #   grouped by house, shown on any resolved path
        └── InheritedFactsPanel.tsx # Read-only aspects/features/liege facet panel for a
                                  #   claimed staff family (#3648)
```

## ChapterOffers, the life page's props (#4874)

`ChapterOffers` (`components/offers/`) grew five props for the life page and keeps every
default for the other chapters. A `layout="grid"` card (the life page's only layout) reads
the distinction's description under its name, not the offer's `player_line` (#5099).
`groupBy` splits a grid under `.group-h` headings
("Group (count)", the ungrouped cards last); `pricing="signed"` prints a grid card's price
as a bare `−N`/`+N` in its bottom-left corner and nothing on a free card; `terms` builds the
mechanics line from `offer.effects` with each term a `.term` role-button (the card is a
button, so no nested button) whose click opens one `.popover` through a portal to `body`
with the definition from the response's `terms`; `interceptPick` runs before a click
changes a pick and `coverOfferId` draws that card dashed (the cover flow);
`secretOfferIds`/`wordSecret`/`wordCover` label the secret pick and the cover on the cards.

## A card click shows at once (#5134)

`useSyncDistinctions` (`@/hooks/useDistinctions`) saves the draft's whole pick list and
returns the mutation plus `pendingEntries`: the picks a save in flight is writing for that
draft, from this grid or any other on the page (every instance shares one mutation key;
`usePendingSync` reads it), null when none is. While it is set, `ChapterOffers` reads a
card's rank from it, so the clicked card is picked and an exclusive sibling let go before
the server answers; a card held some other way than by choice (bundled, carried) is in no
save and keeps its rank. Every grid's cards and the schooling stances are disabled until
the save answers: a second save would be built from the list the first is replacing. The
save's answer is put in the draft-distinctions cache as it stands, with no second request;
the draft, the purse and the offers are still refetched.

## The points move with the click (#5141)

On a page that has distinction cards, anything that prints the draft's CG points or lists
its picks reads `useShownPicks(draft)` (`useShownPicks.ts`), never `draft.cg_points_spent`
or the saved list directly: the life page's ledger and foot line, the Lineage record's "CG
points" line, the Gift summary. It
returns `picks`, `spent` and `remaining`. With no save in flight those are the saved list
and the server's own totals. With one, `shownPicks` (`offers/syncHelpers.ts`) lays the
save's rows over the saved list (a pick left out is let go, a changed rank is re-priced
from the price the server charged per rank, a new pick is priced from its cached offer) and
the totals are re-priced: the draft's total, less the prices in `draft_data.distinctions`
(the list the server added its total up from, in the same response), plus the prices in
the list shown. When the save answers, `useSyncDistinctions` writes its list and the
re-priced totals into the cached draft at once; the draft fetch that follows replaces
them with the server's figures. A failed save shows the old totals again. A test that
mocks `@/hooks/useDistinctions` and renders one of these must give the mock a
`usePendingSync`.

The ledger prints two totals, Starting and Remaining (owner ruling 2026-11-15); the Spent
and Gained lines are gone.

## The spread follows the window (#5144)

`.interview-grid` runs the width of the window up to 150rem. The contents rail is its left
column on every stage, and the chapter's own rail is the last column of `.chapter`, so the
two rails stand at the same two edges whatever the stage holds.

- A stage's rail is its `aside` (the "CG selections" record), or, when `ChapterLeaf` is
  given `railSlot`, an empty `.chapter-rail` that the stage fills from deep inside itself:
  a component reads `useChapterRail()` and portals its panel into the element it returns
  (null outside such a leaf, where the panel renders where it is written). The life page's
  CG points ledger does this, so it is beside the whole stage and not a column of the life.
- A railed leaf (`.chapter-railed`) takes all the room between the rails; its grids widen
  by container query and its prose keeps 68ch. Every other leaf keeps a 38rem reading
  column midway between the rails. To let a stage use the width, give it a layout that
  does (columns of entries, statistics side by side) and lift its cap; do not stretch a
  single column, which puts a row's name a screen-width from its controls.
- Below 74rem a reading stage's rail drops under the leaf; a railed stage keeps its rail
  beside it down to 52rem (the points stay in view while cards are picked).

## Key Features

- **Free navigation**: All stages clickable, incomplete stages show warning badge
- **Real-time validation**: Stage completion tracked, submit blocked until all required stages complete
- **Folio primitives** (entries, instrument frames, fields, choice rows) now back Origin,
  Heritage, Path, Gift, Attributes & Skills, Appearance, Identity, Final Touches, and Review;
  Lineage alone still carries the pre-Folio card/badge markup, pending Plan C (#3630).
  `SkillsSection`, mounted inside AttributesStage's frame, still uses the shadcn Accordion for
  its per-skill specialization panels. The Distinctions stage is retired (#3675): every
  chapter now offers its own distinctions through `ChapterOffers` instead.
- Interface chrome is OOC and plain (stages, Next/Back, Select/Selected); in-character text is confined to
  realm/codex prose and the player's own words; the game never speaks for the player (#3540)
- **Staff-only features**: "Add to Roster" button visible only to staff
- **Player-GM direct-to-roster (#3268)**: a non-staff account that owns at least one active
  GM-role table sees a "Finalize for My Table" button beside Submit, gated by the same
  completeness condition. Opens `FinalizeForTableDialog` — picks the target table, names a
  story, and finalizes onto that table's Available roster (`POST .../finalize-gm/`) without
  going through staff review.

## API Endpoints Used

- `GET /api/character-creation/starting-areas/` - List accessible areas
- `GET /api/character-creation/species/` - List species (filtered)
- `GET /api/character-creation/families/?area_id=&kind=` - List families, optionally
  filtered by area and one or more `FamilyKind` ids (the claimed-path Upbringing's
  `claimable_kind_ids`, #3617)
- `GET /api/roster/families/{id}/slots/` - The claimed family's open seats and counted
  openings, each seat with its `head_relation`, plus the house head's `head_name` (#5130)
- `GET /api/character-creation/can-create/` - Check eligibility
- `GET /api/character-creation/drafts/` - List user's drafts (returns array with 0-1 items)
- `POST /api/character-creation/drafts/` - Create new draft
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Draft detail operations
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- `GET /api/character-creation/combat-styles/?draft_id=X` - The combat styles the draft's Tradition teaches, with how each attacks and defends (#4921)
- `GET /api/magic/resonances/` - Every Resonance with its `affinity_name`, unpaginated (the Gift
  stage's Resonance step; `GET /api/magic/affinities/` lists the Affinities, #4665)
- `GET /api/character-creation/glimpse-tags/` - List the active glimpse tag catalog (guided Glimpse flow, #2427)
- `GET /api/character-creation/form-options/{species_id}/?draft=X` - Trait palettes (`{traits, inherited}`; traits carry `is_required`, `?draft=` appends cross-line option groups from the draft's parents, #2815)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff direct add
- `POST /api/character-creation/drafts/{id}/finalize-gm/` - Player-GM direct-to-roster for a
  table they own (`target_table`, `story_title`, optional `story_description`) (#3268)
- `GET /api/character-creation/drafts/{id}/beats/` - The life's beats as this draft meets
  them (#4124, #4395: each with its `allowance`); the `backgrounds` offers come through
  `GET /api/character-creation/drafts/{id}/offers/?chapter=backgrounds` (#4872: each offer
  carries its `group`, `asks_figure_name` and `effects` with magnitudes; the response's
  `terms` give each lever's definition for the term popovers)
- `GET /api/character-creation/beginnings/{id}/perspectives/` - A beginning's shop-window
  perspective entries, ungated by codex knowledge (ADR-0224, #3281)
- `GET /api/character-creation/traditions/{id}/perspectives/` - Same, for a tradition
  (ADR-0224, #3281)

## Route

`/characters/create` - Main character creation page
