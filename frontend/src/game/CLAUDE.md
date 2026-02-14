# Game - Real-Time RPG Interface

Core game interface for real-time RPG interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Main game interface, composes the three-column layout
- **`GameWindow.tsx`**: Central communication hub with session tabs, chat, and command input

### Layout (`components/`)

- **`GameLayout.tsx`**: Three-column responsive grid (left sidebar, center, right sidebar)
- **`GameTopBar.tsx`**: Character avatars, connection status, character switching
- **`ConversationSidebar.tsx`**: Left sidebar for conversation channels (placeholder)

### Communication (`components/`)

- **`ChatWindow.tsx`**: Message display with auto-scroll and message type coloring
- **`CommandInput.tsx`**: Textarea input with Enter to submit, Shift+Enter for newline, command history
- **`EvenniaMessage.tsx`**: Game message display and formatting

### Room Panel (`components/room-panel/`)

- **`RoomPanel.tsx`**: Right sidebar container with room info, scene controls, navigation
- **`RoomHeader.tsx`**: Room name and scene start/end controls
- **`RoomDescription.tsx`**: Collapsible room description
- **`CharactersList.tsx`**: Characters present in the room with avatars
- **`ExitsList.tsx`**: Clickable exit buttons for navigation
- **`ObjectsList.tsx`**: Objects visible in the room

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
