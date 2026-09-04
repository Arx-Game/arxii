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
    ├── AppearanceStage.tsx  # Stage 8: Appearance
    ├── IdentityStage.tsx    # Stage 9: Identity
    ├── FinalTouchesStage.tsx # Stage 10: Goals
    ├── ReviewStage.tsx      # Stage 11: Review and submit
    ├── FinalizeForTableDialog.tsx # Player-GM direct-to-roster flow from ReviewStage (#3268)
    ├── TraditionPicker.tsx  # Tradition card grid — mounted inside gift/TraditionStep
    ├── PerspectivesPanel.tsx # "On {subject}" shop-window opinions, mounted in
    │                        #   HeritageStage's beginning detail panel and
    │                        #   TraditionPicker's tradition detail panel (#3281)
    ├── gift/                # GiftStage funnel steps (#2426 Task 10)
    │   ├── TraditionStep.tsx    # Wraps TraditionPicker
    │   ├── GiftSelector.tsx     # Gift catalog cards (GET .../gifts/?draft_id=)
    │   ├── TechniqueSelector.tsx # Technique catalog, grouped by category, budget-capped
    │   ├── AnimaCheckStep.tsx   # Anima Check stat/skill pick + ritual name
    │   └── GlimpseSection.tsx   # CG mount of the shared guided Glimpse flow (#2427);
    │                            #   binds `@/magic/components/glimpse/GlimpseFlow` to
    │                            #   draft_data glimpse_tag_ids/glimpse_linked_distinction_ids,
    │                            #   prose stays on GiftStage's register('glimpse_story')
    └── lineage/             # LineageStage subsections (#3617)
        ├── UpbringingPicker.tsx  # One card per OriginTemplate for the chosen Beginning
        ├── UpbringingPrompts.tsx # Slot prompts scoped to the resolved family path;
        │                         #   write-in -> draft_data.origin_slots, pick-list ->
        │                         #   draft_data.origin_choices, priced off influence
        └── FamilyPathSection.tsx # Path picker (when the Upbringing allows more than
                                  #   one) plus the claim/name/none path UI
```

## Key Features

- **Free navigation**: All stages clickable, incomplete stages show warning badge
- **Real-time validation**: Stage completion tracked, submit blocked until all required stages complete
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
