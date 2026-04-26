# Narrative - IC Message Delivery UI

Frontend for the `world.narrative` backend app. Inline message rendering
in the main game text feed (light red), browseable messages section on
the character sheet, and the unread counter in top-level navigation.

## Key Directories

### `components/`

Components are added during Phase 4 Wave 1.

### `pages/`

The narrative app does not own a top-level page. Its UI surfaces
through:

- Inline rendering in the main game text feed (lives under `frontend/src/game/`)
- A messages section embedded in the character-sheet page (lives under `frontend/src/roster/pages/CharacterSheetPage.tsx`)
- An unread-counter badge in the top-level nav

## Key Files

### API Integration

- **`api.ts`**: REST API functions for narrative operations
- **`queries.ts`**: React Query hooks for narrative data
- **`types.ts`**: TypeScript definitions, re-exported from generated API types

## Data Flow

- **REST API**: `/api/narrative/my-messages/` (GET) and `/api/narrative/deliveries/{id}/acknowledge/` (POST)
- **Real-time**: WebSocket session channel delivers narrative messages tagged with `|R[NARRATIVE]|n` color code, picked up by the main text feed component

## Integration Points

- **Backend Models**: `world.narrative.NarrativeMessage` and `NarrativeMessageDelivery`
- **Game text feed**: Real-time inline rendering
- **Character sheet**: Messages section
