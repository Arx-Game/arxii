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
    ├── StartingAreaCard.tsx # Area selection card with gradient placeholder
    ├── OriginStage.tsx      # Stage 1: Area selection
    ├── HeritageStage.tsx    # Stage 2: Heritage, species, gender, pronouns, age
    ├── LineageStage.tsx     # Stage 3: Family selection
    ├── PlaceholderStages.tsx # Stages 4-6: TODO placeholders
    ├── IdentityStage.tsx    # Stage 7: Name, description, personality, background
    └── ReviewStage.tsx      # Stage 8: Review and submit
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
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff direct add

## Route

`/characters/create` - Main character creation page
