# Game - Real-Time RPG Interface

Core game interface for real-time RPG interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Composition root for `/game` (#2156). Derives the active
  session's `sceneId`/`roomName`, calls `useSceneInteractions` +
  `useThreading` once, owns `composerMode` state, and feeds the result down
  as props to `ConversationSidebar` (left) and `GameWindow` (center) — no
  duplicate roster/scene-interaction queries in the children. Also owns the
  **conversation-tab session state** (#2165): `openThreadTabs`/`activeThreadTab`
  live in `gameSlice` per session, and `GamePage` derives the tab strip's props,
  the tab-narrowed feed (`tabInteractions`), and the tab-locked composer mode
  (`effectiveComposerMode`, via `tabKeyToComposerMode`) from that state every
  render — the composer's audience is never stored, only derived, which is the
  mis-send guard. It also hydrates/persists the open-tab layout from
  `threadTabsStorage.ts` and resets tabs on scene change (see `gameSlice.ts`'s
  `setSessionScene`).
- **`GameWindow.tsx`**: Central communication hub with session tabs and
  command input. When the composition root passes a `sceneFeed` prop (an
  active scene), the center renders the structured chat-bubble feed
  (`SceneMessages` + `SystemLane`) instead of the legacy `ChatWindow`. Renders
  `ConversationTabStrip` above the feed when `conversationTabs` is passed
  (#2165), and remembers each conversation tab's scroll offset (`Map<threadKey,
scrollTop>`), restoring it on tab switch and re-pinning to the bottom only
  when the reader was already at the bottom for that tab. The multi-puppet
  session tab bar carries the same direct/ambient `AttentionBadge` as
  `GameTopBar` (#2166), keyed per session name via each character's
  `primary_persona_id` — with one guard `GameTopBar` doesn't need: the
  **active** puppet's own tab never badges (`name !== active`), since its
  attention already surfaces via `ConversationTabStrip`; badging it too would
  double-count the active character's own unseen activity on its own
  already-highlighted tab.
- **`threadTabsStorage.ts`**: `loadThreadTabs`/`saveThreadTabs` (#2165) —
  client-local persistence of the open-tab layout (thread **keys** only, never
  message content) in `localStorage`, keyed per character+scene
  (`arx:threadTabs:<character>:<sceneId>`); a character keeps at most one
  scene's entry, older entries for the same character are pruned on save.
  Best-effort: any storage error (unavailable, unparsable) is swallowed and
  treated as "nothing stored."
- **`attention.ts`**: `sessionAttention(session, personaId)` (#2166) — pure,
  selector-side two-tier attention derivation for one character's session, no
  new Redux write path. Reuses `getThreadKey`/`countUnread` (exported from
  `useThreading.ts`) against `threadLastSeen`/`sceneBaselineId`, the same
  grouping #2165's tab strip badges use. `direct` = unread on `whisper:*`
  threads plus `target:*` threads that include `personaId` (an @-target,
  duel challenge, or consent request aimed at that persona specifically);
  `ambient` = any other thread unread, or the legacy `session.unread` scalar.
  Requires a resolved `personaId` to route to `direct` at all — before the
  roster loads, whisper/target unread routes to `ambient` instead, so a
  session's own echoed whisper never misreads as direct pre-roster-load.

### Layout (`components/`)

- **`GameLayout.tsx`**: Three-column responsive grid (left sidebar, center, right sidebar)
- **`GameTopBar.tsx`**: Character avatars, connection status, character
  switching. Each alt character's avatar carries a two-tier attention
  indicator (#2166, `sessionAttention` from `attention.ts`): a red numeric
  badge for _direct_ attention (an unseen whisper or @-target aimed at that
  character), else a muted dot for _ambient_ (any other unseen activity in
  that session), else nothing. The active character is structurally excluded
  (this bar only ever renders alts) — its own attention lives in
  `ConversationTabStrip`'s per-tab badges, not here.
- **`ConversationSidebar.tsx`**: Left sidebar. Renders the scene's
  `ThreadSidebar` (room/place/whisper/target threads) when `GamePage` passes
  threading state for an active scene; otherwise falls back to a static
  "Room" button. Also owns the per-thread `ThreadFilterModal` (participant
  mute list), mirroring `SceneInteractionPanel`'s composition on `/scenes/:id`.
  **Open-a-tab surface (#2165):** clicking a non-room thread row calls
  `onThreadClick`, which `GamePage` wires to open (or focus, if already open) a
  conversation tab — the sidebar itself never narrows the feed. Clicking the
  room row, or the "All" button, re-anchors the tab strip back to the room and
  resets the composer; `onShowAll` is `GamePage`'s override of
  `threading.showAll` for exactly that reason (the bare `showAll` only resets
  the filter/mute state, not the active tab).
- **`ConversationTabStrip.tsx`**: The open-conversations tab strip rendered
  above the feed in `GameWindow` (#2165) — the room feed as a permanent,
  unclosable anchor tab plus one closable tab per broken-out thread
  (place/whisper/target), each with an unread badge. Selecting a tab dispatches
  `setActiveThreadTab`; closing one dispatches `closeThreadTab`. Renders
  nothing when no conversation tab is open (room-only sessions see no strip).

### Communication (`components/`)

- **`ChatWindow.tsx`**: Legacy raw message log (monospace, black background) —
  the fallback center feed when there's no active scene to structure into
  chat bubbles.
- **`SystemLane.tsx`**: Muted, collapsible strip for system/channel/error
  chatter shown alongside the structured scene feed (#2156) — no
  `bg-black`/`font-mono`, just a quiet compact strip that expands on click.
- **`CommandInput.tsx`**: Textarea input with Enter to submit, Shift+Enter for
  newline, command history. Optional `speakingAs?: { name, thumbnailUrl }`
  prop (#2166) renders a compact `PersonaAvatar` + name chip at the start of
  `leftSlot`, before `ModeSelector` — a standing "who am I talking as right
  now" identity marker on the composer, shown even for single-character
  players. Always renders when supplied; renders nothing when omitted
  (legacy callers unaffected). `GamePage` supplies it from `activeEntry`;
  `SceneDetailPage`'s record-page composer supplies the same shape from its
  own roster lookup. `CombatScenePage`'s composer does not yet thread this
  prop (out of scope for #2166).
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
- **Conversation tabs (#2165)**: Keep several threads (room + place/whisper/target)
  open at once per session; the composer's audience locks to whichever tab is
  active
- **Cross-character attention (#2166)**: Background characters badge
  distinctly by tier (`attention.ts`) — direct (whisper/@-target/prompt, red
  numeric) vs ambient (any other activity, muted dot) — on `GameTopBar` and
  `GameWindow`'s puppet tabs. A background whisper also fires a switch-through
  toast (`handleInteractionPayload.ts`, in `frontend/src/hooks/`) that jumps
  to the right character and thread on click. Duel challenges and consent
  requests addressed to ANY played character surface account-wide
  (`DuelChallengeNotifier`, `ConsentAttentionNotifier`) and act/respond **as**
  the addressed character, not the currently-active one. Every composer
  carries a "speaking as" identity chip (see `CommandInput.tsx` below). All
  routing is derived client-side from data already scoped to the account's own
  personas — no new account-wide payload is rendered to other players ("Never
  out alts").
- **Dynamic commands**: Commands discovered from server with generated forms
- **Real-time updates**: WebSocket integration for live game state
- **Context menus**: Right-click actions on game entities
- **Message formatting**: Rich text display for game messages

## Integration Points

- **WebSocket hooks**: Real-time communication with game server
- **Redux state**: Game session and message management
- **Command discovery**: Dynamic form generation from server metadata
