# Scenes - Scene Management Interface

Scene management interface for RP (roleplay) scenes with filtering, viewing, and participation tracking.

## Key Directories

### `components/`

- **`SceneHeader.tsx`**: Scene title and metadata display. Renders the scene room's art
  (`scene.art_url`, #3556) as a scrimmed banner behind the title when present; nothing when
  the room has no art (render-or-vanish, never a card). See `docs/systems/scenes.md`'s
  "Room art backdrop" section.
- **`SceneTacticalMap.tsx`**: wraps `frontend/src/areas/components/TacticalMap.tsx`, passing
  `scene.art_url` as its `artUrl` prop for the same room-art backdrop behind the node graph
  (#3556). `CombatTacticalMap.tsx` shares the same `TacticalMap` but never passes `artUrl`.
- **`SceneMessages.tsx`**: Scene interaction/dialogue display using the Interaction system
- **`ActorLine.tsx`** (#3858, ADR-0299): the body of a pose or say, the server's `line` (the
  actor in the sentence) through `FormattedContent`, with the leading name set semibold
  when the line opens with the card's own name (the companion's for a companion pose); a row
  without a line renders its `content`. Used by `PoseUnit` and the game's `ExplorationReader`.
  Presentation only: the name is the one the server sent, never a second formatter.
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
