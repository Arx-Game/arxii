# Store - Redux State Management

Redux Toolkit store for global client state management. Minimal use of Redux - only for truly global state.

## Key Files

### Store Configuration

- **`store.ts`**: Redux store configuration with middleware
- **`hooks.ts`**: Typed Redux hooks for components

### State Slices

- **`authSlice.ts`**: User authentication state management
- **`gameSlice.ts`**: Game session management (messages, connections, character sessions).
  Each per-character `Session` also carries the **conversation-tab state** (#2165):
  `openThreadTabs` (ordered thread keys with an open tab; never contains `'room'`,
  which is always the anchor) and `activeThreadTab` (the focused tab's key, or
  `null` for the room anchor). Reducers: `openThreadTab` (opens or focuses a tab),
  `closeThreadTab` (drops a tab, falling back to the room anchor if it was
  active), `setActiveThreadTab` (guards against activating a key that isn't in
  `openThreadTabs`), and `hydrateThreadTabs` (seeds tab state from
  `frontend/src/game/threadTabsStorage.ts`'s `localStorage` snapshot — only when
  the session hasn't already opened tabs, so a live session always wins over a
  stale snapshot). `setSessionScene` resets both fields to empty/`null` whenever
  the session's scene id actually changes — a tab pointing at a previous scene's
  thread set is a mis-send vector, not just stale UI.

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
