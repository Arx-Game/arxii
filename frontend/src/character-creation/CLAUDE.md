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
│   ├── ChapterLeaf.tsx      # Wraps a stage's old internals in the leaf frame
│   ├── RecordRail.tsx       # Marginalia: record-so-far rows + a Note aside
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
│   ├── CodexLine.tsx        # "Codex: {name}" ledger line in an entry body; nothing without an id
│   └── ConfirmDialog.tsx    # Native <dialog> confirm for record-clearing choices
└── components/
    ├── index.ts             # Component exports
    ├── OriginStage.tsx      # Stage 1: Area selection; since #4874 the first name is asked
    │                        #   here too (a Field above the realms, saved on blur by itself,
    │                        #   listed first in the rail), so the life reads the name
    ├── HeritageStage.tsx    # Stage 2: Heritage, species, gender, pronouns, age
    ├── LineageStage.tsx     # Stage 3: the beginning's route (#3617; the Upbringing pick
    │                        #   retired in #4395, the route comes with the beginning),
    │                        #   family selection, kin rows, the life grids; keeps
    │                        #   InventedParentsCard, FamilyNamePreview, KinSlotPicker,
    │                        #   TarotNamingRitual, TarotCardItem, FamilyCard (exported
    │                        #   for lineage/). HouseFoundingPanel retired (#3983 Plan B
    │                        #   Task 6) — claim-path house founding is
    │                        #   `almanach/founder/FounderAlmanach.tsx`, mounted from
    │                        #   `FamilyPathSection.tsx`.
    ├── PathStage.tsx        # Stage 5: Path selection
    ├── SkillsSection.tsx    # Skill point allocation, mounted inside AttributesStage
    ├── AttributesStage.tsx  # Stage 7: Attributes & Skills (mounts SkillsSection)
    ├── GiftStage.tsx        # Stage 6 (Gift): vertical funnel — Tradition → Gift →
    │                        #   [magical training, #4659] → Techniques → Gift Resonance
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
    │                            #   headingTag ("optional") and a closedFilter scoped to
    │                            #   `opener_labels.includes(tag.name)` so a route-closed
    │                            #   distinction prints once, under its own tag (fix
    │                            #   round 2).
    └── lineage/             # LineageStage subsections (#3617, #3648, #4395)
        ├── KinRows.tsx           # The people seated beside the parents (#4395, #4870): a
        │                         #   twin (alive, dead), a spouse (alive, dead, divorced,
        │                         #   separated, missing), a betrothed (promised, dead,
        │                         #   missing, broken off), children (raised, fostered away,
        │                         #   lost), each with a fate ChoiceRow, the whole list at
        │                         #   draft_data.kin_rows; finalize seats them in the
        │                         #   kinship graph. The named parents' fates (#4870) are a
        │                         #   select under each parent's gender in LineageStage
        │                         #   (ParentFateRow; draft_data.line_parent_fate /
        │                         #   other_parent_fate)
        ├── LifeGrids.tsx         # The life as an accordion (#4874, slice 9 of #4813, built
        │                         #   against the demo): one fold per stage (heading + "N of
        │                         #   M" or Unknown, one open at a time, a click on the open one
        │                         #   folds it), one section per beat inside (a closed one reads
        │                         #   its answers with signed points or the prompt with the
        │                         #   first name; Next walks down and into the next stage);
        │                         #   Unknown is a mark on the stage (every beat unknown in one
        │                         #   PATCH); the secret marks under a grid, the Cover story box
        │                         #   on a one-of row (the no-cost card stands as cover until a
        │                         #   click on another card; clicking the real pick drops both)
        │                         #   and a cover select on an any row; a figure's name input
        │                         #   on a picked person card; Description (Optional) per stage
        │                         #   (draft_data.stage_descriptions); the `.leafwrap` layout
        │                         #   with the sticky ledger rail; the testament paragraph.
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
        │                         #   is picked, the unknown mark; the footer counts the
        │                         #   taken beats and the purse. Every life ends on the
        │                         #   Recent History box (#4831), a textarea saved on blur
        │                         #   to draft_data.recent_history; a beginning that
        │                         #   strikes every stage shows its struck_stages_text
        │                         #   where the stages would be, over the box, with no
        │                         #   footer. Replaces BeatsBlock.
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
        │                         #   `showClosed={false}`, its bundled offers passed through
        │                         #   as locked stances). The route's whole closed list prints
        │                         #   once, as a `ClosedByRoute` note after the last
        │                         #   `scope: 'path'` question, never per-answer.
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
        │                         #   offered and none chosen, your own is open by default
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
default for the other chapters: `groupBy` splits a grid under `.group-h` headings
("Group (count)", the ungrouped cards last); `pricing="signed"` prints a grid card's price
as a bare `−N`/`+N` in its bottom-left corner and nothing on a free card; `terms` builds the
mechanics line from `offer.effects` with each term a `.term` role-button (the card is a
button, so no nested button) whose click opens one `.popover` through a portal to `body`
with the definition from the response's `terms`; `interceptPick` runs before a click
changes a pick and `coverOfferId` draws that card dashed (the cover flow);
`secretOfferIds`/`wordSecret`/`wordCover` label the secret pick and the cover on the cards.

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
- `GET /api/character-creation/can-create/` - Check eligibility
- `GET /api/character-creation/drafts/` - List user's drafts (returns array with 0-1 items)
- `POST /api/character-creation/drafts/` - Create new draft
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Draft detail operations
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
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
