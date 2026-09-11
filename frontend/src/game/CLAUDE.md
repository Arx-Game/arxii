# Game - Real-Time RPG Interface

Core game interface for real-time RPG interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Composition root for `/game` (#2156). Derives the active
  session's `sceneId`/`roomName`, calls `useSceneInteractions` +
  `useThreading` once, owns `composerMode` state, and feeds the result down
  as props to `PlaySidebar` (via `GameLayout`'s `sidebar` prop) and `GameWindow`
  (center) — no duplicate roster/scene-interaction queries in the children. Also owns the
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
  (`ThreadedNarrativeReader` + `SystemLane`) instead of a terminal transcript. Renders
  `ConversationTabStrip` above the feed when `conversationTabs` is passed
  (#2165), and remembers each conversation tab's scroll offset (`Map<threadKey,
scrollTop>`), restoring it on tab switch and re-pinning to the bottom only
  when the reader was already at the bottom for that tab. **The room tab is
  the one exception** (#3759): `ThreadedNarrativeReader.tsx` owns restoring
  its own pose-identity anchor for the room view, so this Map's own restore
  only applies there once it already holds a 'room' entry (i.e. from the
  SECOND visit onward this session) — on the very first visit, if a
  persisted anchor exists for the scene, GameWindow defers to the reader's
  restore instead of racing it with a scroll-to-bottom. `handleFeedScroll`
  also never records a position while a historical reference (`reference`
  prop) is being read, since that view falls `activeConvKey` back to 'room'
  too and would otherwise corrupt the live room position under the same key.
  The multi-puppet
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

- **`GameLayout.tsx`**: App shell for play — one wide reader/composer column and
  one contextual sidebar (`PlaySidebar`), not three columns. `sidebar`/
  `leftSidebar`/`rightSidebar` props exist for caller compatibility, but only
  one sidebar ever renders; below the `lg` breakpoint (1024px) the user
  explicitly toggles between Story and Sidebar panes rather than losing either.
- **`PlaySidebar.tsx`**: The single contextual sidebar — Here / Conversations /
  History mode tabs sharing one scroll container. All three mode bodies stay
  mounted (`hidden` attribute, not conditional unmount) so switching modes
  preserves each one's scroll position and in-flight state (#3759).
- **`GameTopBar.tsx`**: Character avatars, connection status, character
  switching. Each alt character's avatar carries a two-tier attention
  indicator (#2166, `sessionAttention` from `attention.ts`): a red numeric
  badge for _direct_ attention (an unseen whisper or @-target aimed at that
  character), else a muted dot for _ambient_ (any other unseen activity in
  that session), else nothing. The active character is structurally excluded
  (this bar only ever renders alts) — its own attention lives in
  `ConversationTabStrip`'s per-tab badges, not here. Also renders (#3412 S4,
  ADR-0247), for the active character: an own-sheet link (`/characters/:id`,
  `RosterEntry.id`-keyed, opens in a new tab so the live session is never
  disturbed) and a compact `ClockReadout` (season + paused indicator only,
  full date/time/phase in the title tooltip) reusing the Hall's
  `useClockQuery` directly — deliberately NOT `hh:mm`, since `WeatherWidget`
  (also rendered here) already surfaces `phase + hh:mm` from the same
  `game_clock` backend and a second hh:mm would just duplicate it.
- **`ConversationSidebar.tsx`**: The Conversations mode body inside
  `PlaySidebar` (not its own column). Renders the scene's
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
- **`HistoryNavigator.tsx`**: Search (2+ characters, filtered by type — Scenes /
  Whispers — and date range) plus browse authorized retained conversations
  (filtered by date range only; type does not scope the browse list, only the
  search query); the conversation list paginates via a cursor. An OOC filter
  option is deliberately not exposed here: `filter_kind`'s `scene_ooc`/`channel`
  branches can never match today (`InteractionMode` has no ooc/system/tt value
  until #3299 lands) — see `interaction_filters.py`.
  ("Load more"). Opening a search result or conversation switches the reader
  into reference mode via `onOpenReference` (#3759).
- **`ConversationTabStrip.tsx`**: The open-conversations tab strip rendered
  above the feed in `GameWindow` (#2165) — the room feed as a permanent,
  unclosable anchor tab plus one closable tab per broken-out thread
  (place/whisper/target), each with an unread badge. Selecting a tab dispatches
  `setActiveThreadTab`; closing one dispatches `closeThreadTab`. Renders
  nothing when no conversation tab is open (room-only sessions see no strip).

### Communication (`components/`)

- **`ThreadedNarrativeReader.tsx`**: The reader for both the live scene feed and
  reference-mode historical browsing (fed by `GamePage.tsx`'s `displaySceneFeed`
  swap — the component itself does not know which source its `interactions`
  prop came from). Threads view default-collapses all but the most recently
  active thread; Chronological view is a flat time-ordered alternative sharing
  the same read/collapse state. Anchors and collapse state persist per
  conversation via `playPreferences.ts`'s LRU store (#3759). **Save/restore
  ownership split with `GameWindow.tsx`:** this component owns restoring its
  own pose-identity anchor (mount, the Return-to-live `readOnly` transition,
  and font/measure preference changes — the last deferred a tick via
  `requestAnimationFrame` so it measures AFTER `DisplaySettings.tsx`'s
  sibling effect has actually applied the changed CSS variable, not before);
  `GameWindow.tsx` owns its OWN separate, ephemeral per-tab raw-scrollTop
  memory (#2165) and only steps out of the way for the anchor on the room
  tab's first visit each session (see its own doc entry above). The Threads-
  view scroll listener attaches at `document` with `capture: true` rather
  than resolving a specific ancestor once at mount — this component has no
  scroll container of its own in that view (GameWindow's own div is the real
  one), and resolving it just once, at mount, could permanently miss it on a
  cold load where the scene starts empty. `persistAnchor` (prop, default
  `true`) must be `false` whenever a non-room conversation tab is the one
  actually on screen, since `conversationKey` is always scoped to the scene
  regardless of tab — GameWindow passes `activeConvKey === 'room'`.
- **`ChatWindow.tsx`**: Retained legacy component for isolated compatibility tests; `/game` now uses `NarrativeMessageReader` —
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
  `SceneDetailPage`'s composer supplies the same shape from its own roster
  lookup — this covers combat too, since #2197 folded the standalone
  `CombatScenePage` into `SceneDetailPage`'s single composer (verified #3412
  S4: no separate combat composer remains; the fold-in already carries
  `speakingAs`).
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

- **Single contextual sidebar**: `PlaySidebar` (Here / Conversations / History
  modes) plus one wide reader/composer column — not the legacy three-column
  layout. Full layout/resize ownership: #3758.
- **Responsive**: Below the `lg` breakpoint (1024px) the layout shows one pane
  at a time — Story or Sidebar — via an explicit toggle, not a hidden sidebar;
  both panes render side by side at `lg` and up.
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
