# Game - Real-Time MUD Interface

Core game interface for real-time MUD interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Main game interface with character tab management
- **`GameWindow.tsx`**: Central game display container

### Game Windows (`components/`)

- **`ChatWindow.tsx`**: Chat and communication display
- **`LocationWindow.tsx`**: Current location and exits
- **`SceneWindow.tsx`**: Active scene information
- **`CharacterPanel.tsx`**: Character status and info

### Command System (`components/`)

- **`CommandForm.tsx`**: Dynamic command form generation
- **`CommandInput.tsx`**: Command input with auto-completion
- **`CommandDrawer.tsx`**: Command selection interface
- **`CommandSelectField.tsx`**: Command parameter selection
- **`CommandTextField.tsx`**: Command text input fields

### Game Components (`components/`)

- **`EvenniaMessage.tsx`**: Game message display and formatting
- **`EntityContextMenu.tsx`**: Right-click context menus for game entities
- **`QuickAction.tsx`**, **`QuickActions.tsx`**: Quick action buttons

### Helpers (`helpers/`)

- **`commandHelpers.ts`**: Command processing utilities

### Types (`types.ts`)

- TypeScript definitions for game data structures

## Key Features

- **Multi-character sessions**: Multiple character tabs open simultaneously
- **Dynamic commands**: Commands discovered from server with generated forms
- **Real-time updates**: WebSocket integration for live game state
- **Context menus**: Right-click actions on game entities
- **Message formatting**: Rich text display for game messages

## Integration Points

- **WebSocket hooks**: Real-time communication with game server
- **Redux state**: Game session and message management
- **Command discovery**: Dynamic form generation from server metadata
