# Store - Redux State Management

Redux Toolkit store for global client state management. Minimal use of Redux - only for truly global state.

## Key Files

### Store Configuration

- **`store.ts`**: Redux store configuration with middleware
- **`hooks.ts`**: Typed Redux hooks for components

### State Slices

- **`authSlice.ts`**: User authentication state management
- **`gameSlice.ts`**: Game session management (messages, connections, character sessions).
  Each `Session` carries `notes: FeedNote[]` (#3856): every `text` frame the socket
  receives becomes one, kind from its `kwargs.type` (`addFeedNote`, id assigned in the
  reducer, bounded at 200, counts `unread` like a message; `clearFeedNotes`). Notes
  survive a room change on purpose: the feed is the character's own history. The
  older `messages` array is still written by the three non-text legacy frames
  (login, VN, reaction) but has had no reader since `SystemLane` went.
  `consoleLines` (#3857) holds the staff console's lines (`addConsoleLine`, bounded
  at 500, never counted as unread; `clearConsoleLines`).
  `minimizedFeed` / `dismissedFeed` (#3856 PR 2) hold the `feedItemKey`s of blocks
  this viewer folded or removed from their own view (`minimizeFeedItem`,
  `restoreFeedItem`, `dismissFeedItem`, and the batch forms `minimizeFeedItems`,
  `dismissFeedItems`, `restoreAllFeed` for the sorting menu's per-character and
  all-lines actions, #4128); in memory only, nothing is deleted for anyone else,
  and a dismissed block never badges.
  Each per-character `Session` also carries the **rail selection** (#4129, which
  replaced #2165's open-tab list): `activeThreadTab` is the conversation rail's one
  selected row — a thread key, `'room'`, a page row's `page:<persona id>`, or `null`
  for All. `setActiveThreadTab` writes any key; nothing is persisted, so
  everything not tied to a scene starts fresh at login. `setSessionScene` (and the
  room-state path) reset it to `null` whenever the session's scene id actually
  changes, the room row excepted — a selection pointing at a previous scene's
  whisper set is a mis-send vector, not just stale UI. A page row's
  `threadLastSeen` mark is a time in ms, since a page is a note with no id.
  `browsingEntryId` (#3479, ADR-0302) is THIS tab's browsing identity, a `RosterEntry`
  id mirrored from `browsingIdentity.ts`; `setBrowsingIdentity`/`clearBrowsingIdentity`
  write it, and `useAccountQuery`'s hydration effect (`evennia_replacements/queries.tsx`)
  seeds it from the account default only when the tab has none, keyed on the account
  payload alone so a Redux-only change (a clear) never re-seeds. Ambient pages read it through `useBrowsingIdentity()`
  (`frontend/src/roster/`); `active`/`sessions` stay the live-session fields.
- **`browsingIdentity.ts`**: the per-tab `sessionStorage` store behind
  `browsingEntryId` (`{ entryId, tabId }`; reads and writes in try/catch, so a page
  renders correctly with no stored value). Per tab by the browser's own contract:
  a reload keeps it, a new tab starts without one. Never keyed by name.

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
