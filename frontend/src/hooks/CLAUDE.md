# Hooks - Custom React Hooks

Custom React hooks for game logic, WebSocket management, and utility functions.

## Key Files

### WebSocket Management

- **`useGameSocket.ts`**: Manages WebSocket connections for real-time game communication
- Connection lifecycle, message handling, automatic reconnection

### Message Processing

- **`parseGameMessage.ts`**: Parses incoming WebSocket messages from game server
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
