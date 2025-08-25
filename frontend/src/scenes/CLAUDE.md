# Scenes - Scene Management Interface

Scene management interface for RP (roleplay) scenes with filtering, viewing, and participation tracking.

## Key Directories

### `components/`

- **`SceneHeader.tsx`**: Scene title and metadata display
- **`SceneMessages.tsx`**: Scene message/dialogue display

### `pages/`

- **`ScenesListPage.tsx`**: Browsable scenes list with status filtering
- **`SceneDetailPage.tsx`**: Detailed scene view with messages and participants

## Key Files

### API Integration

- **`queries.ts`**: React Query hooks for scene data
- **`types.ts`**: TypeScript definitions for scene data structures

## Key Features

- **Scene Browsing**: Filter scenes by status (Active/Paused/Finished)
- **Scene Details**: View scene messages and participant list
- **Real-time Updates**: Active scenes update via WebSocket
- **Participation Tracking**: Character involvement with persona support

## Integration Points

- **Backend Models**: Direct integration with world.scenes Django models
- **WebSocket**: Real-time updates for active scenes
- **Stories System**: Scenes linked to story episodes
- **Character System**: Persona integration for disguised participation
