# Character Creation Frontend

This module provides the staged character creation UI flow.

## Structure

```
character-creation/
├── index.ts                 # Public exports
├── types.ts                 # TypeScript type definitions
├── api.ts                   # API fetch functions using apiFetch
├── queries.ts               # React Query hooks
├── CharacterCreationPage.tsx # Main page component
└── components/
    ├── index.ts             # Component exports
    ├── StageStepper.tsx     # Navigation breadcrumb
    ├── StartingAreaCard.tsx  # Area selection card with gradient placeholder
    ├── OriginStage.tsx      # Stage 1: Area selection
    ├── HeritageStage.tsx    # Stage 2: Heritage, species, gender, pronouns, age
    ├── LineageStage.tsx     # Stage 3: Family selection
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
    ├── TraditionPicker.tsx  # Tradition card grid — mounted inside gift/TraditionStep
    └── gift/                # GiftStage funnel steps (#2426 Task 10)
        ├── TraditionStep.tsx    # Wraps TraditionPicker
        ├── GiftSelector.tsx     # Gift catalog cards (GET .../gifts/?draft_id=)
        ├── TechniqueSelector.tsx # Technique catalog, grouped by category, budget-capped
        ├── AnimaCheckStep.tsx   # Anima Check stat/skill pick + ritual name
        └── GlimpseSection.tsx   # CG mount of the shared guided Glimpse flow (#2427);
                                 #   binds `@/magic/components/glimpse/GlimpseFlow` to
                                 #   draft_data glimpse_tag_ids/glimpse_linked_distinction_ids,
                                 #   prose stays on GiftStage's register('glimpse_story')
```

## Key Features

- **Free navigation**: All stages clickable, incomplete stages show warning badge
- **Framer Motion**: Smooth transitions between stages
- **Visual cards**: Starting areas displayed as cards with crest images or gradient placeholders
- **Real-time validation**: Stage completion tracked, submit blocked until all required stages complete
- **Staff-only features**: "Add to Roster" button visible only to staff

## API Endpoints Used

- `GET /api/character-creation/starting-areas/` - List accessible areas
- `GET /api/character-creation/species/` - List species (filtered)
- `GET /api/character-creation/families/` - List families (filtered)
- `GET /api/character-creation/can-create/` - Check eligibility
- `GET /api/character-creation/drafts/` - List user's drafts (returns array with 0-1 items)
- `POST /api/character-creation/drafts/` - Create new draft
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Draft detail operations
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- `GET /api/character-creation/glimpse-tags/` - List the active glimpse tag catalog (guided Glimpse flow, #2427)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff direct add

## Route

`/characters/create` - Main character creation page
