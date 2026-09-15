# Hooks - Custom React Hooks

Custom React hooks for game logic, WebSocket management, and utility functions.

## Key Files

### WebSocket Management

- **`useGameSocket.ts`**: Manages WebSocket connections for real-time game communication
- Connection lifecycle, message handling, automatic reconnection

### Message Processing

- **`parseGameMessage.ts`**: Parses incoming WebSocket messages from game server
- **Text frames become feed notes** (#3856): `useGameSocket`'s `dispatchLegacyText`
  turns every `text` frame into an `addFeedNote` with the kind from `kwargs.type`
  (`game/feedKinds.ts`'s `classifyText`) and `kwargs.subject` when the server names
  one. The type rides Evennia's tuple form on the server (`msg((text, {"type":
kind}))`), whose dict becomes the frame's kwargs; a sibling keyword would leave as
  a separate frame the client cannot attach to the line.
- **The staff console's frames** (#3857): `sendConsole(character, line)` sends the
  same `text` frame with `{console: true}` in its kwargs; the server tags every
  `text` frame it sends back while that line runs with `console: true`, and
  `dispatchLegacyText` routes such a frame to `addConsoleLine`, never to a note.
- **`handleCommandPayload.ts`**: Processes command-related message payloads
- **`handleRoomStatePayload.ts`**: Updates room state from server messages
- **`handleScenePayload.ts`**: Processes scene-related updates

### Utility Hooks

- **`useDebouncedValue.ts`**: Debounced value updates for search/input fields

### Types (`types.ts`)

- TypeScript definitions for hook-related data structures

## Key Features

- **WebSocket abstraction**: Simplifies real-time communication with game server
- **Message parsing**: Structured handling of different message types
- **State synchronization**: Keeps frontend in sync with game server state
- **Connection management**: Automatic reconnection and error handling

## Usage Patterns

Hooks centralize complex WebSocket logic, allowing components to focus on rendering while maintaining real-time game state synchronization.

```typescript
// Example usage
const { socket, connected } = useGameSocket();
const roomState = useRoomState(characterId);
```
