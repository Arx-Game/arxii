# Game - Real-Time RPG Interface

Core game interface for real-time RPG interaction with WebSocket communication and dynamic command system.

## Key Files

### Main Interface

- **`GamePage.tsx`**: Composition root for `/game` (#2156). Derives the active
  session's `sceneId`/`roomName`, calls `useSceneInteractions` +
  `useThreading` once, owns `composerMode` state, and feeds the result down
  as props to `PlaySidebar` (via `GameLayout`'s `sidebar` prop) and `GameWindow`
  (center) — no duplicate roster/scene-interaction queries in the children. Also owns the
  **rail selection** (#4129): `activeThreadTab` lives in `gameSlice` per session (a
  thread key, `room`, a page row's `page:<persona id>`, or `null` for All), and
  `GamePage` builds the rail's rows (`railRows.ts`'s `buildRailRows` over the
  scene's threads, the quiet room's `ambientInteractions` grouped the same way, and
  the session's page notes), derives the narrowed feed (`tabInteractions`,
  `feedAmbient`, `feedNotes`) and the row-locked composer mode
  (`effectiveComposerMode`, via `tabKeyToComposerMode`) from that selection every
  render — the composer's audience is never stored, only derived, which is the
  mis-send guard. All and the room row keep the pose/say/emit choice (every one of
  them is the room's); any other row locks. It owns the find box's text
  (`findText`, cleared on every character or scene change) and the rail's
  per-person information-flow actions (the #4128 batch reducers over every line of
  theirs the session holds). The slice resets the selection on scene change, the
  room row excepted. It also owns `sidebarMode`/`hereActiveTab` and
  `jumpToCombat()` (#3761) — the whole cross-mode encounter-reachability
  mechanism that routes both the top-bar banner and the sidebar's Combat nav
  button to the same Here-mode Room-tab destination where `CombatRail`
  renders — and, per Finding I1, `lingeringEncounterId`/`dismissedEncounterId`,
  which keep `CombatRail` mounted after `useEncounterForScene`'s poll drops a
  completed encounter, until the player dismisses the outcome banner.
- **`GameWindow.tsx`**: Central communication hub with session tabs and
  command input. When the composition root passes a `sceneFeed` prop (an
  active scene), the center renders the structured prose-line feed
  (`ThreadedNarrativeReader`) instead of a terminal transcript; with no scene it
  renders `ExplorationReader`. Both take the session's `notes` (#3856) and show
  them at their time among the poses; a reference view gets none. Owns the feed
  filter chips (#3856 PR 2): reads them from the per-account preferences (the
  `accountId` prop from `GamePage`), renders `FeedChipStrip` above the
  conversation tabs, filters the scene feed, ambient poses and notes through
  `visibleInteractions`/`visibleNotes` before either reader sees them, shows
  "Everything is switched off. Press a chip to bring one kind back." while All is
  off, and provides `FeedBlockControlsContext` from the session's minimized and
  dismissed keys. A reference view gets neither strip nor filtering. A selected
  conversation (`selectedConversation`, #4129) shows **in full**: dismissed and
  minimized keys are ignored there (the chips still apply), which is the way back
  to a line sorted away in All. The find needle (`find`) narrows the scene feed,
  the ambient poses and the notes after the chips (`feedFind.ts`), provides
  `FeedFindContext` so the line renderers mark matches, and shows one quiet line
  (`feed-find-empty`) when nothing matches. Remembers each conversation's scroll
  offset (`Map<threadKey, scrollTop>`), restoring it on a rail switch and
  re-pinning to the bottom only when the reader was already at the bottom for that
  conversation. Following the newest line between switches is
  `hooks/useStickToBottom.ts`'s (see its entry below); the switch effect only tells
  it, through `pinnedRef`, where the switch left the reader. **All is
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
  `GameTopBar` (#2166); since #3774, both call the same `characterAttention`
  helper (`attention.ts`) rather than deriving the count from session data
  alone, so a puppet tab badges correctly even before this tab has seen
  anything new arrive for that character, with one guard `GameTopBar`
  doesn't need: the **active** puppet's own tab never badges (`name !==
active`), since its attention already surfaces on the conversation rail's
  rows; badging it too would double-count the active character's own unseen
  activity on its own already-highlighted tab.
- **`railRows.ts`**: The conversation rail's rows as pure data (#4129).
  `buildRailRows({threads, ambientInteractions, notes, roomName, viewerPersonaId,
lastSeenByThread, sceneBaselineId})` returns `{here, pages}`: **Here** is the
  room row (always, once there is a room), then every scene thread and every
  quiet-room conversation (`groupThreads`, the hook's grouping run over
  `session.ambientInteractions`, a key held by both merged into one row), newest
  first; **OOC Pages** is one row per correspondent from the session's `page`
  notes (`pageRowKey`, `isPageRowKey`). A whisper row is named after the other
  party and carries their face; a page row's unread mark is a time, not an id.
- **`feedFind.ts`**: Find in this session (#4129). `findInteractions`/`findNotes`
  narrow a list to lines containing the needle (the shown `line`, the recorded
  `content`, the speaker; a note's content or subject); `markMatches` (React
  nodes) and `markMatchesInHtml` (a note's Evennia markup, after sanitizing) wrap
  matches in `<mark data-find-match>`; `FeedFindContext`/`useFeedFind` carry the
  needle from `GameWindow` to `FormattedContent`, `ActorLine` and `EvenniaMessage`
  without a prop through every reader. History's search is a different thing.
- **`feedKinds.ts`**: The closed `FeedKind` union (#3856) every feed entry carries,
  the list the filter chips will offer. `classifyText(kwargs.type, kwargs.category)`
  maps a `text` frame's wire type (`look`, `item`, `error`, `move`, `arrive`;
  `narrative` and `gemit` to `ambience`, except a `narrative` frame in the `visions`
  category, which is the `vision` kind (#3779); anything else `system`) and `classifyInteraction(mode)`
  maps an interaction's mode. A new kind is a deliberate addition here, never an ad
  hoc string.
- **`feedChips.ts`**: The filter chips' pure model (#3856 PR 2). `FeedChip {id, label,
kinds, on, wake, custom}`; a kind belongs to at most one chip; `DEFAULT_FEED_CHIPS`
  are the demo's five plus Visions (#3779) (Roleplay, Whispers and Visions wake;
  Movement, Ambience, System do not). **System owns the `system` kind** (#3933): it is
  the hide-system button, so pressing it has to hide login and connection chatter, not
  just look/item/error. `normalizeFeedChips` migrates a stored layout once, and only
  under both guards: the `sy` chip still has exactly the pre-#3933 default kinds
  (a re-kinded chip is the player's own choice and is left alone) and nothing else
  owns `system`. Rules: `isKindShown` (All off hides everything; an unowned
  kind shows), `wakingKinds` (on and wake), `toggleChip` (with All off, a press turns
  All on with only that chip), `toggleAll`, `setKindOwner` (moves a kind between
  chips), `renameChip`, `setChipWake`, `addCustomChip` (cap 3), `deleteChip` (its
  kinds keep showing), `normalizeFeedChips` (repairs a stored layout),
  `visibleInteractions`/`visibleNotes` (chips plus the viewer's dismissed keys),
  `feedItemKey` (`i:<id>` / `n:<id>`). The layout lives in `PlayPreferences`
  (`feedChips`, `feedAll`), per account per browser.
- **`feedBlockControls.ts`**: The context `FeedBlockFrame` reads: the session's
  minimized keys and the minimize/restore/dismiss dispatchers `GameWindow` provides;
  null in a reference view, so history renders without controls.
- **`feedRows.ts`**: `interleaveNotes(items, notes)` (#3856) sorts an item list and
  the session's `FeedNote`s into one column by parsed time (server timestamps may
  lack milliseconds; note timestamps are the client clock at receipt), stable, items
  first on a tie. Both readers use it; the scene reader feeds it thread groups at
  their root pose's time in Threads view and the flat pose list in Chronological.
- **`attention.ts`**: `sessionAttention(session, personaId, sinceId?, options?)` (#2166,
  extended #3774): pure, selector-side two-tier attention derivation for one
  character's session, no new Redux write path. Reuses `getThreadKey`/
  `countUnread` (exported from `useThreading.ts`) against
  `threadLastSeen`/`sceneBaselineId`, the same grouping #2165's tab strip
  badges use. `direct` = unread on `whisper:*` threads plus `target:*` threads
  that include `personaId` (an @-target, duel challenge, or consent request
  aimed at that persona specifically); `ambient` = any other thread unread, or
  the legacy `session.unread` scalar. Requires a resolved `personaId` to route
  to `direct` at all: before the roster loads, whisper/target unread routes
  to `ambient` instead, so a session's own echoed whisper never misreads as
  direct pre-roster-load. Since #3774, `sessionAttention`'s result is no
  longer the whole picture on its own: it is the local-tab DELTA on top of a
  server-computed baseline. `sinceId` is that server's watermark
  (`MyRosterEntry.attention_as_of_id`): anything at or below it is dropped, so
  the caller can add the delta to the server count without double-counting a
  pose the server already saw. `characterAttention(char, session)` is the
  combination (server baseline `unread_direct`/`has_ambient_unread` plus
  this delta), and it is the one callers should reach for; `GameTopBar` and
  `GameWindow`'s puppet-tab row both call it, so the two can never diverge. A
  character with no local session in this tab renders the server value alone,
  which is the fresh-device case #3774 exists for. `AttentionBadge` (the
  render, capped at `99+` since a server-side count can run to three digits)
  now lives in its own module, `components/AttentionBadge.tsx`, extracted from
  byte-identical copies that used to live in `GameTopBar`/`GameWindow`. Since #3856
  PR 2 both take `AttentionOptions`: `wakingKinds` (from the chips; an interaction
  under a chip that is off or silent counts for nothing) and `dismissed` (a block
  the viewer removed cannot keep a badge lit). `chipUnread(session, personaId,
chips, dismissed?)` counts unread per waking chip for the strip's "new" pills,
  the same threshold rule as `countUnread` read per row.

### Layout (`components/`)

- **`GameLayout.tsx`**: App shell for play — one wide reader/composer column and
  one contextual sidebar (`PlaySidebar`), not three columns. `sidebar`/
  `leftSidebar`/`rightSidebar` props exist for caller compatibility, but only
  one sidebar ever renders; below the `lg` breakpoint (1024px) the user
  explicitly toggles between Story and Sidebar panes rather than losing either.
- **`ConversationRail.tsx`**: The conversation rail (#4129), the play shell's
  far-left column (`GameLayout`'s `rail` prop). **All** at the top, then the
  groups `railRows.ts` builds (Here, OOC Pages; Channels is reserved for #3299 and
  not drawn), each row with its name, a kind word, its unread count and, for a
  person's conversation, their face. One row is selected at a time
  (`aria-current`): left-click the face for `PersonaMenu` (play flow), left-click
  the row to select it, right-click the row for the information-flow menu
  (Minimize all from them, Hide all from them, Expand all, Unhide all, the
  per-character half of #4128's `LineMenu`). « folds the rail to a 44px strip of
  counts (`railCollapsed` in the play preferences; a count press reopens it on
  that row); the find box at the foot (`feed-find`, Esc clears) is the needle
  `GameWindow` narrows by. Width (`railWidth`, 200 to 320) is dragged on the
  pane's right edge in `GameLayout`.
- **`PlaySidebar.tsx`**: The single contextual sidebar — Here / History mode tabs
  sharing one scroll container (Conversations mode left for the rail, #4129).
  Both mode bodies stay mounted (`hidden` attribute, not conditional unmount) so
  switching modes preserves each one's scroll position and in-flight state
  (#3759). A "Combat" nav button (#3761) appears only while `hasActiveEncounter` is true
  and jumps to Here mode's Room tab, where `CombatRail` renders. `mode`/
  `onModeChange` are REQUIRED controlled props owned by `GamePage` (not
  internal state) — a future caller must supply both.
- **`SidebarTabPanel.tsx`**: The Here mode's body (#3856 PR 3, the approved demo's
  side panel). The room view (`roomPanel`: `FocusPanel` or `DreamspacePanel`) with an
  "Actions" `<details>` fold at its foot holding the eight reference sections (Who,
  Stories, Events, Codex, Status, Items, Journal, Travel) as a three-column grid,
  open by default and folding on its arrow. Pressing a section shows it in place of
  the room with a "← <room or focused subject>" way back at the top (`roomTabLabel`
  names it, truncated with the full name in `title`). Replaces the nine-trigger tab
  row that sat above the room; `activeTab`/`onTabChange` stay controlled by
  `GamePage` (#3761, `jumpToCombat` sets `'room'`), and each section still mounts
  lazily on first open. Nothing was dropped: every section keeps its panel and
  fallback text.
- **`GameTopBar.tsx`**: Character avatars, connection status, character
  switching, and the world menu (#3818): the leading button opens a
  `DropdownMenu` (Your characters → `/hall`, Roster, Settings, "Leave the world
  as <active>", Log out). It was a `<Link to="/">`, and `/` (`GatefoldPage`)
  redirects an in-world player straight back to `/game`, so it flickered and
  did nothing; `/hall` is the Hall on a route that never redirects. Navigating
  away keeps every character tab connected (sessions and sockets live in
  Redux/module scope, and `GamePage` has no teardown); "Leave the world" is
  `useGameSocket().disconnect(name)`, which closes that one socket so the
  server unpuppets the character (nobody stands unpiloted on the grid) and
  drops the session, while the account stays signed in with its selection
  intact. `useLogout` already closes every socket. Every non-active
  character's avatar carries a two-tier attention
  indicator (#2166, `characterAttention` from `attention.ts` since #3774):
  a red numeric badge for _direct_ attention (an unseen whisper or @-target
  aimed at that character), else a muted dot for _ambient_ (any other unseen
  activity), else nothing; since #3774 this badges every non-active
  character, not just ones with a local session in this browser tab (a
  character with no session renders the server's baseline count alone). The
  active character's own badge row is gated on `active` (a #3774 review
  fold-in fix: without the gate, with no active character every character's
  avatar rendered twice, once from this row and once from the named-button
  row below); its attention lives on the conversation rail's rows
  instead, which is the only reason it stays excluded now: the old
  "this bar only ever renders alts" framing no longer holds, since the bar
  can render every character when nobody is active. Also renders (#3412 S4,
  ADR-0247), for the active character: an own-sheet link (`/characters/:id`,
  `RosterEntry.id`-keyed, opens in a new tab so the live session is never
  disturbed) and a compact `ClockReadout` (season + paused indicator only,
  full date/time/phase in the title tooltip) reusing the Hall's
  `useClockQuery` directly — deliberately NOT `hh:mm`, since `WeatherWidget`
  (also rendered here) already surfaces `phase + hh:mm` from the same
  `game_clock` backend and a second hh:mm would just duplicate it. Also
  renders `CombatBanner` (#3761), a second full-width strip below the main
  bar shown while `hasActiveEncounter` is true, that jumps the sidebar to the
  combat rail on click.
- **`HistoryNavigator.tsx`**: Search (2+ characters, filtered by type — Scenes /
  Whispers — and date range) plus browse authorized retained conversations
  (filtered by date range only; type does not scope the browse list, only the
  search query); the conversation list paginates via a cursor ("Next page" —
  replaces the current page rather than appending to it, per its own name).
  An OOC filter option is deliberately not exposed here: `filter_kind`'s
  `scene_ooc`/`channel` branches can never match today (`InteractionMode` has
  no ooc/system/tt value until #3299 lands) — see `interaction_filters.py`.
  Opening a search result or conversation switches the reader into reference
  mode via `onOpenReference` (#3759).
  **Conversation drill-down (#3772):** each readable conversation row also carries a
  `Threads` disclosure; at most one is open at a time, and nothing is fetched until it is
  opened (a count on every collapsed row would mean querying all thirty visible rows up
  front). A row the viewer cannot read gets no disclosure.
- **`ConversationThreadList.tsx`**: One conversation's reply threads, from
  `GET /api/play/threads/` (#3772). Owns its own cursor, so collapsing a conversation
  discards it. A row is labelled by the thread's opening line, matching how the reader
  titles a thread, and falls back to `N poses from <date>` when that line is blanked for
  a muted persona (#2087) or not comprehended (#2993). The unread pill is
  `ThreadSidebar`'s, so one badge means one thing in live and historical surfaces.
  Pressing a row calls `onOpenThread`, which `HistoryNavigator` turns into an
  `onOpenReference` anchored at the thread's `firstVisible` pose.

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
  `true`) must be `false` whenever a rail row other than All is the one
  actually on screen, since `conversationKey` is always scoped to the scene
  regardless of selection — GameWindow passes `activeConvKey === 'room'`.
  Chronological scrolls inside its own container, so it calls `useStickToBottom`
  itself for that container; `restoreChronoAnchor` clears the hook's `pinnedRef`
  when it puts the reader back on a saved row.
- **`ExplorationReader.tsx`**: The no-scene reader. Room facts stay structured
  (name, description); below them one `Activity` list of the room's ambient
  interactions and the session's notes, ordered by time through `feedRows.ts`.
  An ambient row's body is the server's `line` (#3858) through
  `scenes/components/ActorLine.tsx`, the actor in the sentence, as in `PoseUnit`, and
  since #4128 the same prose line: avatar as indent, time on hover, no header row;
  left-click on the avatar is the persona menu, the right button is the frame's.
  It owns its scroll container and follows its newest line through
  `useStickToBottom`.
- **`hooks/useStickToBottom.ts`**: The one rule for every feed: the newest line
  stays in view while the reader is at the bottom, and a reader who scrolled up
  is left where they are until they come back down. It watches the content's
  **size** with a `ResizeObserver`, never a count of poses: a feed also grows
  when a note arrives, when a virtualised row is measured taller than its
  estimate and when an image loads, and the count-based effect this replaced
  followed none of those (and the quiet-room reader had no following at all).
  **Only the reader unpins it**: a move up that follows a wheel turn, a touch, a
  key press, or a pointer held on the scrollbar. Distance from the bottom alone
  proves nothing (the event from an earlier follow can fire after the next line
  landed), and neither does a move up alone: a virtualised list pulls the
  position up by itself when rows measure shorter than their estimate. Treating
  that as the reader scrolling stopped Chronological following in about one
  browser run in two, with every jsdom test green; `e2e/feed-follow.spec.ts`
  found it, and only when repeated. Callers: `GameWindow` (the scene feed's container;
  off for a reference view), `ExplorationReader`, and `ThreadedNarrativeReader`
  for Chronological's inner container. A caller that places the reader itself
  (a tab switch, a restored anchor) writes `pinnedRef`. Tests fire the observer
  by hand through `test/utils/resizeObserver.ts`, since jsdom lays nothing out.
- **`DisplaySettings.tsx`**: The per-account reading controls in the sidebar; it
  writes the preferences to CSS variables on `<html>`. **The text fills the story
  pane by default**: `--play-reading-measure` is `none` unless the player sets
  Line length to Limited (`limitMeasure`), which caps the column at `measure`
  characters and centres it. Every reader's column is
  `max-w-[var(--play-reading-measure,none)]`. The cap used to be always on at
  90ch, which on a wide window left hundreds of pixels empty on both sides of
  the text.
- **`FeedChipStrip.tsx`**: The strip above the column (#3856 PR 2): one plain label
  per chip (`aria-pressed` = All and on; a "new" pill from `chipUnread`), `+`
  while a custom chip can still be added, All at the right end. Left click
  toggles; right click opens `FeedChipEditor` in a popover anchored to the chip:
  name (Enter commits and closes), every kind with a checkbox and "(in X)" where
  another chip carries it, "Wake me when this arrives", Delete chip. Controlled;
  every change writes through to the preferences at once. No explainer text, by
  ruling.
- **`FeedBlockFrame.tsx`**: Wraps any block in the column (#3856 PR 2; gestures #4128,
  ADR-4128) and owns its sorting. Nothing sits on the block: a quick right-click on the
  text folds it to a one-line stub ("Nyx · 11:29", "Look · 11:30") and unfolds it again;
  a held right-click (`HOLD_MS`), a long-press, or a right-click on the avatar
  (`[data-pose-avatar]`) opens `LineMenu` at the pointer. The stub keeps a reopen press
  and a Hide control. Callers pass `persona`, `keysOf` and `allKeys` so the menu's
  per-character and all-lines items act on every loaded line: `PoseReadTarget` (the
  reader's `sorting` memo) for poses in both scene views, `ExplorationReader` for its
  ambient lines; `FeedNoteBlock` passes none, so a note's menu has no per-character
  items. Outside a provider it renders the block as it is and no gesture fires.
- **`LineMenu.tsx`**: The sorting menu (#4128): information flow only, how text renders.
  A controlled Radix `DropdownMenu` anchored to a zero-size trigger at the pointer, headed
  by who and when: Minimize or Expand, Hide; Minimize all from <name>, Hide all from
  <name>; Minimize all, Expand all, Unhide all. There is no hide-everything, by ruling.
  While open it suppresses the browser's own context menu at document level: on Windows
  `contextmenu` fires on mouse up, after a held press has already opened ours under the
  pointer, so a guard on the line never sees it. Labels are American English (Minimize).
- **`hooks/useLineGestures.ts`**: The right button and the long-press on a line (#4128):
  `onFold` on a quick right-click on the text, `onMenu(x, y)` on a held one, on a
  right-click on the avatar, or on a touch held for `HOLD_MS`; a plain tap does nothing,
  so scrolling on a phone never folds; `contextmenu` is always prevented. Left click is
  play flow and is not read here. The test pointer polyfill carries `pointerType`.
- **`FeedNoteBlock.tsx`**: One typed text line in either reader (#3856), styled
  by `FeedKind` after the approved demo: a boxed note for `look` (subject title +
  prose body), `item` and `system`; the destructive tokens and `role="alert"` for
  `error`; a bare italic line for `arrive`/`move`; the italic line with a hairline
  for `ambience`. Every body renders through `EvenniaMessage` in prose
  presentation, since the server sends Evennia's HTML (colour spans, `<br>`).
  There is no separate system strip any more: `SystemLane` was removed with
  #3856, since every text frame is a note in the column now.
- **`ChatWindow.tsx`**: Retained legacy component for isolated compatibility tests; `/game` now uses `ExplorationReader` —
  the fallback center feed when there's no active scene to structure into
  prose lines.
- **`CommandInput.tsx`**: Textarea input with Enter to submit, Shift+Enter for
  newline, command history. **The label is the truth (#3857):** `GamePage`'s
  `effectiveComposerMode` derives Pose for the room anchor whenever no mode is
  chosen (a fresh connection, the reset on every character or scene change), so a
  typed line is `pose <line>` and never a raw command by accident; picking a mode
  works before any was set. A line starting with `/` is the command after the
  slash, sent as typed whatever the mode (`slashEscape`); `//` poses a literal
  slash; a typed speech verb or `page` (`KNOWN_COMMANDS`) still passes through,
  and any other word is prose (`look` on its own is the pose "look"). Staff
  (`isStaff`, from `account.is_staff` via `GameWindow`) get a Commands entry in
  `ModeSelector`; in that mode the formatting controls, the companion selector and
  the scene controls step aside, the box takes the monospace face, and every line
  goes through `useGameSocket().sendConsole`.
  **The entrance is a state, not a toggle (#3867):**
  `isEntrance` is derived from the room state's `scene.viewer_entered === false`; the
  right slot shows "✨ Entrance" (`data-testid="entrance-state"`) with the
  technique attachment (#2183) beside it until the first pose lands, which goes
  out as `pose_kind: 'entry'` (the server marks it either way). The old
  "Make an entrance" button is gone. **All composer text lives in `useDraftStore`**
  (#3784): `draft.content` is the textarea's `value` and `setContent` is the
  only write path — never add a second local string or storage key mirroring
  it. Clearing on a successful send is `acknowledge(clientRequestId)` alone;
  it already no-ops when a newer edit has nulled that id, so no extra
  "is the textarea still showing what was sent" check is needed.
  `draftScopeSettling` names the conversation a draft belongs to and whether
  its scope can address that conversation yet (`GameWindow`'s `room:unknown`
  during entry), so the draft moves with the scope when it settles rather
  than being stranded — and never moves to a different audience. Optional `speakingAs?: { name, thumbnailUrl }`
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
- **`StaffConsole.tsx`**: The staff console (#3857): a Console control in the
  composer's toolbar (staff only) and the `Sheet` it opens over the play surface,
  holding `session.consoleLines`: each Commands-mode line echoed (`sent`, muted,
  after a `›`) above everything the server said back to it, in the terminal face
  inside the app's own sheet (title, Clear, Close). It opens itself when a line
  arrives while Commands mode is active and stays closed once closed until the
  next; the control counts the answers that arrived while it was closed.
- **`EvenniaMessage.tsx`**: Game message display and formatting for the plain-text
  frames (look results, command replies, Evennia's own errors). Renders sanitized
  HTML rather than going through `FormattedContent`, so it carries the feed's
  `[overflow-wrap:anywhere]` wrap rule itself (#3862; the rule's home is
  `frontend/src/components/FormattedContent.tsx`).

### Room Panel (`components/room-panel/`)

- **`RoomPanel.tsx`**: Right sidebar container with room info, scene controls, navigation
- **`RoomHeader.tsx`**: Room name and scene start/end controls
- **`RoomDescription.tsx`**: Collapsible room description
- **`CharactersList.tsx`**: Characters present in the room with avatars. A row whose
  `in_scene` is false, and the viewer's own row when `viewerInScene` is false, carries
  the threshold mark (#3867): an asterisk after the name, `title="Not yet in the
scene"`, no explainer. Lists the
  viewer first with a "you" tag (#3856) — the room state's `characters` excludes
  them, so `RoomPanel` supplies `viewer` from its `character` prop and
  `FocusPanel` supplies the portrait from the roster entry. Pressing the row sends
  `look me` (never the name, which could prefix-match another occupant), so what
  others see when they look at you lands as a look note in the column.
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

### Persona Menu (`persona-menu/`, #4030)

The one right-click menu for a persona lives in `frontend/src/scenes/components/PersonaMenu.tsx`
(see `frontend/src/scenes/CLAUDE.md`); this directory holds its shared, scene-independent pieces,
used by every persona surface (pose name and avatar, the quiet-room reader, the room character
list, the Who panel):

- **`personaMenuApi.ts`**: `fetchPersonaMenu`/`usePersonaMenuQuery`, the React Query wrapper over
  `GET /api/actions/characters/<characterId>/personas/<personaId>/menu/`. This is the only source
  for what the menu shows and why an item is greyed out; nothing in the frontend re-derives
  availability from a scene cache or a hardcoded item list.
- **`LookDialog.tsx`**: the Look result, in a draggable dialog built directly on
  `@radix-ui/react-dialog` (not `components/ui/dialog.tsx`, whose `DialogContent` always renders
  the dimming overlay). Closes on Esc, the close button, or an outside click; carries a View sheet
  button.
- **`useDraggable.ts`**: the pointer-drag hook `LookDialog` uses to move by its title bar. Local to
  this one dialog; no drag library exists in the frontend and one dialog does not justify adding
  one.
- **`PersonaCardContext.tsx`**: lets any persona surface (room list, Who panel, the quiet-room
  reader) call the `openCharacterCard` handler `GamePage` owns, so View sheet opens the existing
  `CharacterCardDrawer` from anywhere the persona menu renders, not only from `PoseUnit`.

This replaces `EntityContextMenu.tsx`/`QuickAction.tsx` (the 2025 left-click quick-action row that
never got a caller outside its own test) and the `BaseState.dispatcher_tags` per-object command
list (never populated in production): the server-composed persona menu is that feature, built.

### Helpers (`helpers/`)

- **`commandHelpers.ts`**: Command processing utilities

## Key Features

- **Rail, reader, sidebar**: the conversation rail on the far left
  (`ConversationRail`, #4129, 200 to 320px or a 44px strip), one wide
  reader/composer column, and `PlaySidebar` (Here / History, plus a Combat mode
  shown only during an active encounter, #3761). Layout/resize ownership:
  `GameLayout` (#3758, ADR-4129).
- **Responsive**: Below 960px the layout shows one pane at a time — Rail, Story
  or Sidebar — via an explicit toggle, not a hidden pane; all three render side
  by side from 960px up.
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
- **Two menus by button (#4128, ADR-4128)**: left click is play flow (the avatar's
  persona menu with Reply and Kudos first), right click is information flow (fold, hide,
  per-character and all-lines sorting through `LineMenu`)
- **Message formatting**: Rich text display for game messages

## Integration Points

- **WebSocket hooks**: Real-time communication with game server
- **Redux state**: Game session and message management
- **Command discovery**: Dynamic form generation from server metadata
