# Roster - Character Management Interface

Character roster management system with character sheets and applications. A
character's pictures live in its sheet's Gallery tab (#4151); the data layer for it is
`gallery.ts` here, the components are `character_sheets/components/sheet/gallery/`.

## Key Directories

### `pages/`

- **`RosterListPage.tsx`**: Browsable character roster with filtering
- **`CharacterSheetPage.tsx`**: Detailed character information display. Its plate lines
  come from `character_sheets/components/sheet/glanceLines.ts`, shared with the waiting
  sheet (`character-creation/WaitingSheetPage.tsx`, #5206), which composes the same plate,
  section row and panels from a draft

## The sheet's pieces take data as well as an id (#5206)

The waiting sheet has no character to fetch by, so these take what they draw as an optional
prop and make no query when it is given (absent, each behaves as before): `Plate` `mark` (a
node above the name), `SectionRow` `sections` (the sections offered), `DistinctionsTab` /
`DistinctionsPanel` `payload`, `SpellbookTab` / `MagicPanel` `payload`, `SecretsTab`
`secrets`, `XpLedgerCard` `ledger`, `LanguagesSection` `languages`. The Estate's pieces are
exported from `panels.tsx` and draw from data: `PurseBlock` (`balance`), `CarriedBlock`
(`items`, `outfits`, `wardrobe` for the links), `DomainsBlock`, `KeyringBlock`;
`EstatePanel` fetches and passes them in. `OriginStoryAnswers` is the origin story
read-only, and `ReputationTab` exports `OrganizationStandingBlock`

## Key Files

### API Integration

- **`api.ts`**: REST API functions for roster operations
- **`queries.ts`**: React Query hooks for roster data
- **`types.ts`**: TypeScript definitions for roster data structures
- **`gallery.ts`**: The Gallery's calls and hooks (#4151): list, upload, change, delete,
  reorder, hide/show, wear, storage, moods. Every change refreshes the gallery, the
  sheet, the roster entry and the portrait chips

## Key Features

- **Character Applications**: Apply for available roster characters
- **Character Sheets**: Detailed character information and demographics
- **Gallery**: a character's pictures and looks, on the sheet (#4151)
- **Natural weapons**: Physical's block for claws or a bite a gift gave the character
  (#4898, `character_sheets/components/sheet/NaturalWeapons.tsx`), drawn from the sheet
  payload's `natural_weapons`, which only the owner and staff receive
- **Tenure System**: Character ownership history tracking
- **Search and Filtering**: Advanced roster browsing capabilities

## Data Flow

- **REST API**: Full CRUD operations via `/api/roster/` endpoints
- **Pagination**: Large roster sets with efficient pagination
- **File Upload**: Direct integration with Cloudinary for media storage
- **NSFW veil**: flagged pictures are blurred for non-friends; no per-picture privacy

## Integration Points

- **Backend Models**: Direct integration with world.roster Django models
- **Authentication**: Tenure-based permissions for character access
- **Media Storage**: Cloudinary integration for file uploads
