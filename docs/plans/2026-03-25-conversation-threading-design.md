# Conversation Threading & Smart Composer Design

**Date:** 2026-03-25
**Status:** Design
**Depends on:** Interaction system (built), Places (built), Rich text editor (built)

## Problem Statement

In a room with 30+ people, the interaction feed is an overwhelming wall of text.
Players need to filter, focus, and manage multiple simultaneous conversations without
losing track of what's happening. The compose input needs to default to the right
audience so players can seamlessly continue conversations.

## Thread Model

Threads are derived on the frontend from interaction data. No new backend model needed.
A thread is identified by its **audience pattern**:

### Thread Types

| Type | Identified By | Visibility | Example |
|------|--------------|------------|---------|
| **Room-wide** | No place, no receivers, no targets | Everyone | Main meeting discussion |
| **Place** | `place` FK set | People at that place | Tabletalk at a table |
| **Whisper** | mode=WHISPER, specific receivers | Writer + receivers only | Private aside |
| **Targeted** | `target_personas` set, visible to room | Everyone (but groupable) | Two people debating |

Two interactions are in the same thread if they share the same audience pattern:
- Same `place` ID, OR
- Same sorted set of receiver persona IDs (for whispers), OR
- Same sorted set of target persona IDs (for targeted), OR
- Both are room-wide (no place, no receivers, no targets)

### Thread State is Client-Side

All threading state is ephemeral — resets on page leave/refresh:
- Which threads are expanded/collapsed
- Which thread the composer is targeting
- Which personas are hidden via filter modal
- No backend persistence needed

### What Creates a Thread

Threads form ONLY from explicit targeting in the command — selecting recipients in the
composer, choosing a place, or using whisper mode. Text content mentioning someone's
name does NOT create a thread. In the default "All" view, targeted interactions are
visually indistinguishable from the main flow — they only become distinct groupings
when a player wants to filter.

## UI Layout

### Left Sidebar: Thread Bookmarks

A narrow strip showing active conversations:

**Top level:** An **"All"** button showing the unfiltered chronological feed.

**Below it:** Expandable list of active threads, auto-populated from interaction data:
- **"The Grand Ballroom"** — room name (helps distinguish when playing multiple
  characters across rooms). Always present.
- **"Table by the fire"** — place thread (if you or others are at a place)
- **"Whisper: Bob"** — whisper thread
- **"Ariel & Bob"** — targeted thread between those personas

Each bookmark shows:
- Thread name/label
- Unread count (new interactions since you last viewed this thread)
- Highlighted if currently active, dimmed if not

**Clicking "All":** Shows everything unfiltered. Composer targets the main room.

**Clicking a specific thread:** Filters the feed to show only that thread's
interactions. Sets the composer to target that thread's audience.

Multiple threads can be visible simultaneously — clicking additional thread
bookmarks toggles them on/off.

### Thread Filter Modal

Right-click any thread bookmark → **"Filter participants"** option → modal opens
showing every persona that has interacted in that thread, each with a checkbox.

- All checked by default
- Unchecking a persona hides their interactions in that thread
- Modal stays open while toggling — check/uncheck several people quickly
- Close modal → feed updates immediately

Works for the main room thread too — right-click "The Grand Ballroom" → filter
modal → uncheck 7 noisy players → now you see the 33 you care about.

### Main Feed: Interaction Stream

**Default (All):** Everything merged chronologically, exactly like the current feed
with no thread awareness. Players who don't want threading see no difference.

**Filtered:** Only interactions from visible threads appear. Hidden threads are
completely removed from the feed (not dimmed — gone). A compact indicator at the
top shows: "Showing: The Grand Ballroom, Table by the fire (2 threads hidden)"

### Composer: Auto-Targets Last Thread

The compose area shows the current target context above the toolbar:

- "Posing to: The Grand Ballroom" (room-wide)
- "Posing to: Table by the fire" (place)
- "Whispering to: Bob" (whisper)
- "Posing at: Ariel, Bob" (targeted)

**Auto-defaulting behavior:**
- When you click a thread bookmark, the composer switches to that thread's audience
- When you submit a pose, the composer stays on the same thread (continue the
  conversation without re-selecting)
- When you change targets manually in the composer, that becomes the new default
  for that thread
- When in "All" mode, the composer targets your most recent thread

## Backend Changes

### Serializer Updates

The Interaction serializer needs additional fields for thread grouping:

```python
# Add to InteractionListSerializer:
receiver_persona_ids = SerializerMethodField()
place_name = SerializerMethodField()
target_persona_ids = SerializerMethodField()

def get_receiver_persona_ids(self, obj):
    return [r.persona_id for r in obj.cached_receivers]

def get_place_name(self, obj):
    return obj.place.name if obj.place else None

def get_target_persona_ids(self, obj):
    return [p.pk for p in obj.cached_target_personas]
```

All derived from already-prefetched data — zero additional queries.

### WebSocket Payload Updates

The push_interaction payload needs the same thread-grouping data:

```python
payload = {
    ...existing fields...
    "place_id": interaction.place_id,
    "place_name": interaction.place.name if interaction.place else None,
    "receiver_persona_ids": [r.persona_id for r in receivers],
    "target_persona_ids": [p.pk for p in targets],
}
```

This requires prefetching receivers and targets when building the payload. For
persisted interactions, this is a query after create. For ephemeral, we already
have the data from the function parameters.

### Shout Mode (future)

Shout echoes to adjacent rooms. For threading purposes, a shout shows up in the
main room-wide thread of whatever room sees it. If a shout crosses into a room
with an active scene, it appears in that scene's feed as a room-wide interaction.
Implementation deferred — for now shout is just another mode in the main thread.

## Frontend Components

### ThreadSidebar

New component for the left sidebar thread bookmarks:

```
frontend/src/scenes/components/ThreadSidebar.tsx
```

- Reads interactions from the scene feed (React Query + WebSocket)
- Groups interactions into threads by audience pattern
- Renders thread bookmarks with names and unread counts
- Manages which threads are visible (local state)
- Provides the active thread to the composer via context

### ThreadFilterModal

Modal for per-persona filtering within a thread:

```
frontend/src/scenes/components/ThreadFilterModal.tsx
```

- Shows all personas that have interacted in the selected thread
- Checkboxes for each persona
- Updates a local set of hidden persona IDs

### useThreading Hook

Custom hook that encapsulates all threading logic:

```
frontend/src/scenes/hooks/useThreading.ts
```

- Takes the interaction list (REST + WebSocket merged)
- Groups into threads by audience pattern
- Manages filter state (which threads visible, which personas hidden)
- Returns: threads, filtered interactions, active thread, setter functions
- Purely client-side state

### Composer Target Display

Update `RichTextInput` or `CommandInput` to show the current target context:

```
"Posing to: The Grand Ballroom"
```

With a small dropdown/selector to switch targets manually.

## Thread Identification Algorithm

Given an interaction, determine its thread:

```typescript
function getThreadKey(interaction: Interaction): string {
  // Whisper: sorted receiver IDs
  if (interaction.mode === 'whisper' && interaction.receiver_persona_ids.length > 0) {
    const ids = [...interaction.receiver_persona_ids].sort();
    return `whisper:${ids.join(',')}`;
  }
  // Place: place ID
  if (interaction.place_id) {
    return `place:${interaction.place_id}`;
  }
  // Targeted: sorted target IDs
  if (interaction.target_persona_ids.length > 0) {
    const ids = [...interaction.target_persona_ids].sort();
    return `target:${ids.join(',')}`;
  }
  // Room-wide: no qualifiers
  return 'room';
}
```

Threads are dynamically built from this grouping. New threads appear in the sidebar
when a new unique thread key is seen. Threads with no recent activity could fade or
move to the bottom.

## Implementation Phases

### Phase 1: Backend serializer + payload updates
- Add receiver_persona_ids, place_name, target_persona_ids to serializer
- Add the same to WebSocket push payload
- Update frontend Interaction type
- Tests

### Phase 2: useThreading hook
- Thread identification algorithm
- Thread grouping from interaction list
- Filter state management (visible threads, hidden personas)
- Tests

### Phase 3: ThreadSidebar component
- Thread bookmark rendering
- Click to filter/unfilter
- Unread counts
- Right-click → filter modal

### Phase 4: ThreadFilterModal component
- Persona list with checkboxes
- Apply/clear filters

### Phase 5: Composer target integration
- Display current target context
- Auto-switch on thread selection
- Persist last target per thread

### Phase 6: Integration
- Wire ThreadSidebar into SceneDetailPage layout
- Wire useThreading into SceneMessages
- Wire composer target into CommandInput
- End-to-end testing

## Composer Design (Refined)

The composer has two independent parts:

### Mode Indicator (left of text area)

A small box showing the current default command and targets:
- `[Pose → Room]`
- `[Pose → Bob, Carol]`
- `[TT → Table by the fire]`
- `[Whisper → Bob]`

Set by clicking thread bookmarks. Persists until changed. NEVER erases the text
area when changed — it only affects what happens when you submit text without an
explicit command prefix.

### Text Area (free-form)

The user types freely. If they just type text, the mode indicator's default applies.
If they start with an explicit command (`tt `, `whisper @bob `, `pose @alice,@bob `),
that overrides the mode indicator for this submission only.

**Double-click a persona name** in the feed → `@name` is appended to the command
line as a target. If no command prefix is present, one is added based on the current
mode indicator.

### Command Syntax

Current telnet syntax:
- `pose <text>` → pose to room
- `say <text>` → say to room
- `whisper <target>=<text>` → whisper to one person

New targeting syntax (extends existing):
- `pose @bob,@carol <text>` → pose targeting Bob and Carol
- `tt <text>` → tabletalk at current place
- `whisper @bob <text>` → whisper to Bob (simplified from `whisper bob=text`)

The `@name` parsing is new — the current command system doesn't support it. This
needs backend work: PoseAction needs to accept optional `targets` kwarg, and
the command parser needs to extract `@name` tokens from the text.

### Behavior Rules

- Text is NEVER erased by clicking bookmarks
- Mode indicator only changes the default, not the content
- Explicit command in text always overrides mode indicator
- After submit, mode indicator stays the same (continue conversation)
- After changing targets in text, mode indicator updates to match

## Backend: Target Parsing

The current CmdPose passes all text to PoseAction as `{"text": text}`. For
targeting, we need:

1. Parse `@name` tokens from the command text
2. Resolve names to character objects in the room
3. Pass resolved targets to PoseAction as `{"text": remaining_text, "targets": [...]}`
4. PoseAction passes targets to record_interaction as target_personas

This parsing belongs in `CmdPose.resolve_action_args()` on the telnet side, and
in the web action dispatcher for the frontend side.

## Design Decisions

- **Thread naming for 5+ people:** "Alice, Bob, Carol..." with mouseover for full list
- **Thread staleness:** No auto-collapse. Hiding is always a player choice. Future
  account preferences PR could let players set defaults.
- **Initial load:** Only show interactions from the current session onward. Players
  entering a room don't see what happened before they arrived — prevents privacy
  violations and is consistent with how physical rooms work. Historical scene logs
  are a separate view (scene detail page).
- **Composer target UI:** Mode indicator to the left + free-form text area. Bookmarks
  set the default mode. No separate dropdown — the command text is the source of truth.
