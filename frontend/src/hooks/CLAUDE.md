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
- **The staff console's frames** (#3857): `sendConsole(character, line)` echoes the
  line into `consoleLines` (`sent: true`) and sends the same `text` frame with
  `{console: true}` in its kwargs; the server tags every
  `text` frame it sends back while that line runs with `console: true`, and
  `dispatchLegacyText` routes such a frame to `addConsoleLine`, never to a note.
- **The puppet handshake** (#3933): on every socket open `useGameSocket` sends
  `['puppet', [], { character }]`, not the `@ic <name>` text line it used to send.
  The reply is structured, never text: a `puppet_changed` naming **this** socket's
  character sets `session.puppetConfirmed`, a `puppet_changed` for another
  character (a sibling tab switching) is ignored, and a refusal arrives as
  `command_error` and is toasted. Readiness still gates on `room_state`.
- **Three tags drop a `text` frame** (#3933, ADR-0306). `dispatchLegacyText` adds no
  note when the frame's kwargs carry `interaction_echo: true` (the structured
  Interaction pushed alongside it is the render), `type: 'lifecycle'` (a puppet
  milestone, not story), or `on_entry: true` (the room panel already shows the entry
  look). `logged_in` is silent for the same reason, so it no longer lands in the
  message lane.
- **Every frame type has a case** (#3933). `handlerFor` covers ours, including
  `character_died` (toast), `estate_settlement_opened` (the REST view owns that
  surface), `oob` and `webclient_options` (no Arx meaning).
  `EVENNIA_CONTROL_TYPES` in `types.ts` lists Evennia's own protocol frames
  (channel, ping, ...), which are ignored silently. Anything left is a genuine gap
  in this client: `unknownFrames.ts` records the type name in a bounded in-memory
  list (50 entries, no payload) and `console.warn`s it. It never becomes a feed
  diagnostic, because a protocol gap is for a developer to close and a player
  cannot act on it.
  **The server side pins this:** `src/web/tests/test_message_type_parity.py` fails
  when a `WebsocketMessageType` member is not named in `types.ts`, so adding a
  server frame type forces a client case.
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
