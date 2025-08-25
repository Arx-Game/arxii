# Store - Redux State Management

Redux Toolkit store for global client state management. Minimal use of Redux - only for truly global state.

## Key Files

### Store Configuration

- **`store.ts`**: Redux store configuration with middleware
- **`hooks.ts`**: Typed Redux hooks for components

### State Slices

- **`authSlice.ts`**: User authentication state management
- **`gameSlice.ts`**: Game session management (messages, connections, character sessions)

## Key Features

- **Authentication State**: Current user account and login status
- **Game Sessions**: Multi-character session management
- **Message History**: Game message storage and display
- **Connection State**: WebSocket connection status

## Architecture Decisions

- **Minimal Redux Usage**: Only for global state that needs sharing across components
- **React Query for Server State**: All API data managed by React Query, not Redux
- **Typed Hooks**: Fully typed Redux integration for TypeScript safety

## Integration Points

- **AuthProvider**: Authentication state synced with React Query
- **WebSocket Hooks**: Game state updates from WebSocket messages
- **Game Interface**: Multi-character session state management
