# Character Creation Frontend

This module provides the staged character creation UI flow.

## Structure

```
character-creation/
├── index.ts                 # Public exports
├── types.ts                 # TypeScript type definitions
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
│   ├── Entry.tsx            # EntryList/Entry/EntryDoors: choosable record entries
│   ├── InstrumentFrame.tsx  # InstrumentGroup/StatRow: labeled stat instruments
│   ├── ChoiceRow.tsx        # Segmented choice: a few named options, one pressed (#3630)
│   ├── Field.tsx            # Inscription label over a serif control on a hairline (#3630)
│   ├── Paragraphs.tsx       # Blank-line-separated prose split into <p> tags (#3630)
│   ├── CodexWord.tsx        # In-world term linked via CodexTerm when a codex entry exists
│   ├── CodexLine.tsx        # "Codex: {name}" ledger line in an entry body; nothing without an id
│   └── ConfirmDialog.tsx    # Native <dialog> confirm for record-clearing choices
└── components/
    ├── index.ts             # Component exports
    ├── OriginStage.tsx      # Stage 1: Area selection
    ├── HeritageStage.tsx    # Stage 2: Heritage, species, gender, pronouns, age
    ├── LineageStage.tsx     # Stage 3: Upbringing + family selection (#3617); keeps
    │                        #   InventedParentsCard, HouseFoundingPanel,
    │                        #   FamilyNamePreview, KinSlotPicker, TarotNamingRitual,
    │                        #   TarotCardItem, FamilyCard (exported for lineage/)
    ├── DistinctionsStage.tsx # Stage 4: Distinctions
    ├── PathStage.tsx        # Stage 5: Path selection
    ├── SkillsSection.tsx    # Skill point allocation, mounted inside AttributesStage
    ├── AttributesStage.tsx  # Stage 7: Attributes & Skills (mounts SkillsSection)
    ├── GiftStage.tsx        # Stage 6 (Gift): vertical funnel — Tradition → Gift →
    │                        #   Techniques → Gift Resonance → Anima Check, plus an
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
    ├── IdentityStage.tsx    # Stage 9: Identity
    ├── FinalTouchesStage.tsx # Stage 10: the Actor's Sheet (#3621): three questions,
    │                        #   numbered goals by horizon, the priced enemy, The Introductions.
    │                        #   Directly under the three questions mounts this chapter's own
    │                        #   offered distinctions (ChapterOffers chapter="actors_sheet",
    │                        #   #3675 Task 15), the personality-flavored ones each prompt
    │                        #   answers.
    ├── ReviewStage.tsx      # Stage 11: Review and submit
    ├── FinalizeForTableDialog.tsx # Player-GM direct-to-roster flow from ReviewStage (#3268)
    ├── TraditionPicker.tsx  # Traditions as entries — mounted inside gift/TraditionStep
    ├── PerspectivesPanel.tsx # "On {subject}" shop-window opinions; renders as margin
    │                        #   notes in HeritageStage and inside the chosen tradition's
    │                        #   entry in TraditionPicker (#3281, #3630)
    ├── gift/                # GiftStage funnel steps (#2426 Task 10)
    │   ├── TraditionStep.tsx    # Wraps TraditionPicker
    │   ├── GiftSelector.tsx     # Gifts as entries (GET .../gifts/?draft_id=)
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
    └── lineage/             # LineageStage subsections (#3617, #3648)
        ├── UpbringingPicker.tsx  # One card per OriginTemplate for the chosen Beginning
        ├── UpbringingPrompts.tsx # Slot prompts; `scope: 'any'` renders above the family
        │                         #   block, `scope: 'path'` renders below it, scoped to
        │                         #   the resolved family path; write-in ->
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
        │                         #   (claim path)
        ├── FamilyTemplateForm.tsx # Shared aspect-pick + features form for a Family
        │                         #   Template, used by both HouseFoundingPanel (noble
        │                         #   title claim) and the name path (#3648)
        ├── VacancyPicker.tsx     # Renders reachable Vacancies (description, importance,
        │                         #   presumed importance, price, remaining) for pick
        ├── ServicePanel.tsx      # Retainer Vacancies reachable from this Upbringing,
        │                         #   grouped by house, shown on any resolved path
        └── InheritedFactsPanel.tsx # Read-only aspects/features/liege facet panel for a
                                  #   claimed staff family (#3648)
```

## Key Features

- **Free navigation**: All stages clickable, incomplete stages show warning badge
- **Real-time validation**: Stage completion tracked, submit blocked until all required stages complete
- **Folio primitives** (entries, instrument frames, fields, choice rows) now back Origin,
  Heritage, Distinctions, Path, Gift, Attributes & Skills, Appearance, Identity, Final
  Touches, and Review; Lineage alone still carries the pre-Folio card/badge markup, pending
  Plan C (#3630). `SkillsSection`, mounted inside AttributesStage's frame, still uses the
  shadcn Accordion for its per-skill specialization panels.
- Interface chrome is OOC and plain (stages, Next/Back, Selected); in-character text is confined to
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
- `GET /api/character-creation/origin-templates/?beginning=X` - Upbringings for the
  chosen Beginning (the Lineage step's picker, #3617)
- `GET /api/character-creation/can-create/` - Check eligibility
- `GET /api/character-creation/drafts/` - List user's drafts (returns array with 0-1 items)
- `POST /api/character-creation/drafts/` - Create new draft
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Draft detail operations
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- `GET /api/character-creation/glimpse-tags/` - List the active glimpse tag catalog (guided Glimpse flow, #2427)
- `GET /api/character-creation/form-options/{species_id}/?draft=X` - Trait palettes (`{traits, inherited}`; traits carry `is_required`, `?draft=` appends cross-line option groups from the draft's parents, #2815)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff direct add
- `POST /api/character-creation/drafts/{id}/finalize-gm/` - Player-GM direct-to-roster for a
  table they own (`target_table`, `story_title`, optional `story_description`) (#3268)
- `GET /api/character-creation/beginnings/{id}/perspectives/` - A beginning's shop-window
  perspective entries, ungated by codex knowledge (ADR-0224, #3281)
- `GET /api/character-creation/traditions/{id}/perspectives/` - Same, for a tradition
  (ADR-0224, #3281)

## Route

`/characters/create` - Main character creation page
