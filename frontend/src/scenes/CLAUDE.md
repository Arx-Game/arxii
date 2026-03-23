# Scenes - Scene Management Interface

Scene management interface for RP (roleplay) scenes with filtering, viewing, and participation tracking.

## Key Directories

### `components/`

- **`SceneHeader.tsx`**: Scene title and metadata display
- **`SceneMessages.tsx`**: Scene interaction/dialogue display using the Interaction system
- **`ActionPanel.tsx`**: Scene action request panel
- **`ActionResult.tsx`**: Action result display
- **`ConsentPrompt.tsx`**: Consent prompt for scene actions
- **`PersonaContextMenu.tsx`**: Context menu for persona interactions
- **`PlaceBar.tsx`**: Place bar for sub-location display

### `pages/`

- **`ScenesListPage.tsx`**: Browsable scenes list with status filtering
- **`SceneDetailPage.tsx`**: Detailed scene view with interactions and participants

## Key Files

### API Integration

- **`queries.ts`**: React Query hooks for scene and interaction data
- **`types.ts`**: TypeScript definitions for scene and interaction data structures

## Key Features

- **Scene Browsing**: Filter scenes by status (Active/Paused/Finished)
- **Scene Details**: View scene interactions and participant list
- **Real-time Updates**: Active scenes update via WebSocket
- **Participation Tracking**: Character involvement with persona support
- **Interactions**: All RP content recorded via the Interaction system

## Integration Points

- **Backend Models**: Direct integration with world.scenes Django models
- **WebSocket**: Real-time updates for active scenes
- **Stories System**: Scenes linked to story episodes
- **Character System**: Persona integration for disguised participation
