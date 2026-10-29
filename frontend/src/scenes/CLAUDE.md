# Scenes - Scene Management Interface

Scene management interface for RP (roleplay) scenes with filtering, viewing, and participation tracking.

## Key Directories

### `components/`

- **`SceneHeader.tsx`**: Scene title and metadata display. Renders the scene room's art
  (`scene.art_url`, #3556) as a scrimmed banner behind the title when present; nothing when
  the room has no art (render-or-vanish, never a card). See `docs/systems/scenes.md`'s
  "Room art backdrop" section.
- **`SceneTacticalMap.tsx`**: wraps `frontend/src/areas/components/TacticalMap.tsx`, passing
  `scene.art_url` as its `artUrl` prop for the same room-art backdrop behind the node graph
  (#3556). Outside a fight only: during an encounter the scene page's map is `CombatMainMap`
  (`frontend/src/combat/components/`), in the left column above the pose log, and
  `SceneTacticalMap` is not mounted (#4670). `CombatTacticalMap.tsx` no longer uses `TacticalMap`;
  it draws the SVG `BattleMap` (place areas, terrain art, tokens on squares).
- **`SceneMessages.tsx`**: Scene interaction/dialogue display using the Interaction system;
  passes `onReply` through to each pose's play menu (#4128).
- **`PoseUnit.tsx`** (POSE branch since #4128, ADR-4128): one prose line. The avatar floats
  left as an indent (`[data-pose-avatar]`, `data-testid="pose-avatar"`), the first line
  starts beside it and later lines wrap back under it; paragraph breaks are kept
  (`whitespace-pre-line`); the time is a hover-only `<time>` at the top right; no header
  row, role label or bubble, a hover tint instead. Left-click on the avatar, and on the
  name that opens the line (`[data-pose-actor]`, `data-testid="pose-actor"`, through
  `ActorLine`'s `renderName`; #4791), is `PersonaMenu` with `poseActions` (Reply, Kudos)
  first and `contextMenu={false}`, since the right button belongs to `FeedBlockFrame`'s
  sorting menu, which both open at once; double-click on either is the add-target
  affordance; a read-only line renders both plain. A companion pose's name is the
  companion's and its menu is the owner's, as the avatar's is (a companion has no face or
  menu of its own, #3294); it keeps its "(via <owner>)" tell after the line. Action chips, the parent chip, reactions, badges,
  nominate and endorsements keep their places after the text. The ACTION, OUTCOME and
  narration branches are unchanged.
- **`hooks/useKudos.ts`** (#2031, #4128): the first kudos on a pose, lazily opening its
  kudos window and recording the reaction in one call; was `ReactionStrip`'s standalone
  chip, now the play menu's Kudos item. An opened kudos window still renders as a strip row.
- **`ActorLine.tsx`** (#3858, ADR-0299): the body of a pose or say, the server's `line` (the
  actor in the sentence) through `FormattedContent`, with the leading name set semibold
  when the line opens with the card's own name (the companion's for a companion pose); a row
  without a line renders its `content`. Used by `PoseUnit` and the game's `ExplorationReader`.
  Presentation only: the name is the one the server sent, never a second formatter. The
  optional `renderName` (#4791) wraps the found name in the caller's play menu; it is never
  called for a line that does not open with the name, which renders as sent.
- **`ActionPanel.tsx`**: Scene action request panel. A challenge approach (`ref.backend ===
'challenge'`, a wall's climb, a door's lock) resolves through the dispatch endpoint
  (`useDispatchPlayerAction`), never a scene action request: it has no one to ask (#4606; before
  it, the request was keyed by the button text and could never resolve).
  Since #4675 `ActionPanel` and `ActionAttachment` drop registry entries that `isMapOnlyAction`
  (`combat/roundActionHelpers.ts`) names: those carrying `position_id` or `feature_id` (moves, stunts, GM
  place) and `gm_attach_feature`. They belong to the battle map and the combat panels, and their stable ids
  include the position and feature so two stunts never share a key. `fetchAvailableActions` asks for
  `page_size=100`. The battle map's feature layer and `GMFeatureControls` are described in
  `docs/systems/areas.md`, "Features and stunts".
- **`ActionResult.tsx`**: Action result display
- **`ConsentPrompt.tsx`**: Consent prompt for scene actions
- **`PersonaMenu.tsx`** (#4030): The one action menu for a persona — right-click
  (Radix `ContextMenu`) anywhere, plus an optional left-click `DropdownMenu`
  trigger (`leftClick` prop, today's name-click). Since #4128 `contextMenu={false}`
  turns the right-click trigger off (a pose line's right button is the sorting menu)
  and `poseActions` lists Reply and Kudos as the first group when opened from a pose. Fed only a persona id; its
  content (Look, View sheet, and every other item/group) is composed entirely
  by `GET /api/actions/characters/<characterId>/personas/<personaId>/menu/`
  (`frontend/src/game/persona-menu/personaMenuApi.ts`) — no client-side `canX`
  gating and no scene cache read for availability. Replaces the scene-bound
  `PersonaContextMenu` and the never-wired `EntityContextMenu`.
- **`PlaceBar.tsx`**: Place bar for sub-location display

### `pages/`

- **`ScenesListPage.tsx`**: Browsable scenes list with status filtering
- **`SceneDetailPage.tsx`**: Detailed scene view with interactions and participants

## Key Files

### API Integration

- **`queries.ts`**: React Query hooks for scene and interaction data
- **`types.ts`**: TypeScript definitions for scene and interaction data structures
- **`sceneFeedCache.ts`** (#4508): the one home of the scene feed's query keys
  (`sceneFeedAllKey`, `sceneFeedSceneKey`, `sceneFeedQueryKey`, scene id second) and
  `refreshSceneFeedRow`. Every feed read, write to the cache and invalidation goes through it;
  never spell the key inline, or an invalidation will miss the feed.

## Key Features

- **Scene Browsing**: Filter scenes by status (Active/Paused/Finished)
- **Scene Details**: View scene interactions and participant list
- **Real-time Updates**: Active scenes update via WebSocket
- **Participation Tracking**: Character involvement with persona support
- **Interactions**: All RP content recorded via the Interaction system

## Integration Points

- **Backend Models**: Direct integration with world.scenes Django models
- **WebSocket**: Real-time updates for active scenes
- **Stories System**: Scenes linked to story episodes
- **Character System**: Persona integration for disguised participation
