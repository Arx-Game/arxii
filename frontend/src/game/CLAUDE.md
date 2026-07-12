# Game - Real-Time RPG Interface

Core game interface for real-time RPG interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Composition root for `/game` (#2156). Derives the active
  session's `sceneId`/`roomName`, calls `useSceneInteractions` +
  `useThreading` once, owns `composerMode` state, and feeds the result down
  as props to `ConversationSidebar` (left) and `GameWindow` (center) — no
  duplicate roster/scene-interaction queries in the children.
- **`GameWindow.tsx`**: Central communication hub with session tabs and
  command input. When the composition root passes a `sceneFeed` prop (an
  active scene), the center renders the structured chat-bubble feed
  (`SceneMessages` + `SystemLane`) instead of the legacy `ChatWindow`.

### Layout (`components/`)

- **`GameLayout.tsx`**: Three-column responsive grid (left sidebar, center, right sidebar)
- **`GameTopBar.tsx`**: Character avatars, connection status, character switching
- **`ConversationSidebar.tsx`**: Left sidebar. Renders the scene's
  `ThreadSidebar` (room/place/whisper/target threads) when `GamePage` passes
  threading state for an active scene; otherwise falls back to a static
  "Room" button. Also owns the per-thread `ThreadFilterModal` (participant
  mute list), mirroring `SceneInteractionPanel`'s composition on `/scenes/:id`.

### Communication (`components/`)

- **`ChatWindow.tsx`**: Legacy raw message log (monospace, black background) —
  the fallback center feed when there's no active scene to structure into
  chat bubbles.
- **`SystemLane.tsx`**: Muted, collapsible strip for system/channel/error
  chatter shown alongside the structured scene feed (#2156) — no
  `bg-black`/`font-mono`, just a quiet compact strip that expands on click.
- **`CommandInput.tsx`**: Textarea input with Enter to submit, Shift+Enter for newline, command history
- **`EvenniaMessage.tsx`**: Game message display and formatting

### Room Panel (`components/room-panel/`)

- **`RoomPanel.tsx`**: Right sidebar container with room info, scene controls, navigation
- **`RoomHeader.tsx`**: Room name and scene start/end controls
- **`RoomDescription.tsx`**: Collapsible room description
- **`CharactersList.tsx`**: Characters present in the room with avatars
- **`ExitsList.tsx`**: Clickable exit buttons for navigation
- **`ObjectsList.tsx`**: Objects visible in the room
- **`PortalsBlock.tsx`**: Portal-network destinations the active character could
  travel to right now (#2222); renders nothing when empty. "Travel" dispatches the
  same `travel_to` registry action the Go-there buttons use.

### Command System (`components/`)

- **`CommandForm.tsx`**: Dynamic command form generation
- **`CommandDrawer.tsx`**: Command selection interface
- **`CommandSelectField.tsx`**: Command parameter selection
- **`CommandTextField.tsx`**: Command text input fields

### Game Components (`components/`)

- **`EntityContextMenu.tsx`**: Right-click context menus for game entities
- **`QuickAction.tsx`**: Quick action button component

### Helpers (`helpers/`)

- **`commandHelpers.ts`**: Command processing utilities

## Key Features

- **Three-column layout**: Conversation sidebar, communication hub, room panel
- **Responsive**: Sidebars hidden below lg breakpoint, center content fills screen
- **Multi-character sessions**: Multiple character tabs open simultaneously
- **Dynamic commands**: Commands discovered from server with generated forms
- **Real-time updates**: WebSocket integration for live game state
- **Context menus**: Right-click actions on game entities
- **Message formatting**: Rich text display for game messages

## Integration Points

- **WebSocket hooks**: Real-time communication with game server
- **Redux state**: Game session and message management
- **Command discovery**: Dynamic form generation from server metadata
