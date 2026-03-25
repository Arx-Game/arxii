# Conversation Threading & Smart Composer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add conversation threading (thread sidebar, filtering, per-persona hiding)
and a smart composer with mode indicator, @target parsing, and thread-aware defaulting.

**Architecture:** Backend adds receiver/target IDs + place name to serializer and
WebSocket payload, plus @target parsing in pose/say commands. Frontend adds a
useThreading hook for client-side thread grouping, ThreadSidebar with filter modal,
and a mode indicator on the composer that auto-fills from thread selection.

**Tech Stack:** Django/DRF (backend), React 18/TypeScript/Tailwind/Radix UI (frontend),
Vitest (frontend tests), FactoryBoy (backend tests)

**Design doc:** `docs/plans/2026-03-25-conversation-threading-design.md`

**Key conventions:**
- Backend: SharedMemoryModel, type annotations, absolute imports, line length 100
- Frontend: Functional components, React Query, Redux for client state, Radix UI
- Run backend: `echo "yes" | arx test world.scenes` / `uv run arx test`
- Run frontend: `pnpm --dir frontend test -- --run` / `pnpm --dir frontend typecheck`

---

## Task 1: Backend — Serializer + WebSocket Payload Updates

**Files:**
- Modify: `src/world/scenes/interaction_serializers.py`
- Modify: `src/world/scenes/interaction_services.py` (push_interaction payload)
- Modify: `src/world/scenes/interaction_views.py` (prefetch receivers)
- Modify: `frontend/src/scenes/types.ts` (Interaction type)
- Modify: `frontend/src/hooks/types.ts` (InteractionWsPayload type)
- Test: `src/world/scenes/tests/test_interaction_services.py`

### Backend serializer

Add three fields to `InteractionListSerializer`:

```python
receiver_persona_ids = serializers.SerializerMethodField()
place_name = serializers.SerializerMethodField()
target_persona_ids = serializers.SerializerMethodField()

def get_receiver_persona_ids(self, obj: Interaction) -> list[int]:
    return [r.persona_id for r in obj.cached_receivers]

def get_place_name(self, obj: Interaction) -> str | None:
    return obj.place.name if obj.place_id else None

def get_target_persona_ids(self, obj: Interaction) -> list[int]:
    return [p.pk for p in obj.cached_target_personas]
```

Add `"receiver_persona_ids"`, `"place_name"`, `"target_persona_ids"` to Meta.fields.

Add `cached_receivers` property to Interaction model if not present (same
getter/setter pattern as other cached properties). Add InteractionReceiver prefetch
to InteractionViewSet.get_queryset().

### WebSocket payload

Update `_build_interaction_payload` in interaction_services.py to include:
```python
"place_id": place_id,
"place_name": place_name,
"receiver_persona_ids": receiver_persona_ids,
"target_persona_ids": target_persona_ids,
```

Update `push_interaction` to pass these — query receivers and targets from the
just-created interaction. For push_ephemeral_interaction, pass from the function
parameters.

### Frontend types

Update `Interaction` in types.ts:
```typescript
export interface Interaction {
  ...existing fields...
  place: number | null;         // already exists
  place_name: string | null;    // NEW
  receiver_persona_ids: number[];  // NEW
  target_persona_ids: number[];    // NEW
}
```

Update `InteractionWsPayload` in hooks/types.ts:
```typescript
export interface InteractionWsPayload {
  ...existing fields...
  place_id: number | null;
  place_name: string | null;
  receiver_persona_ids: number[];
  target_persona_ids: number[];
}
```

Update `wsPayloadToInteraction` in SceneMessages.tsx to map the new fields.

### Tests
- Backend: verify serializer includes new fields
- Backend: verify push payload includes new fields
- Frontend: update type expectations in existing tests

Commit: `feat: add thread-grouping data to interaction serializer and WebSocket payload`

---

## Task 2: Backend — @Target Parsing in Pose/Say Commands

**Files:**
- Modify: `src/commands/evennia_overrides/communication.py` (CmdPose, CmdSay)
- Modify: `src/actions/definitions/communication.py` (PoseAction, SayAction)
- Modify: `src/world/scenes/interaction_services.py` (record_interaction)
- Create: `src/commands/parsing.py` (or add to existing helpers)
- Test: `src/commands/tests/test_target_parsing.py`

### Target parsing utility

Create a parser that extracts @name tokens from command text:

```python
def parse_targets(text: str, location) -> tuple[str, list]:
    """Extract @name targets from command text.

    Returns (remaining_text, resolved_targets) where targets are
    character objects found in the location.

    Example: "@bob,@carol waves hello" -> ("waves hello", [bob_obj, carol_obj])
    """
    # Match @name patterns at the start of text (before the pose content)
    # Names can contain spaces if comma-separated: @bob,@carol smith,@alice
    # Stop parsing targets when we hit text that doesn't start with @
```

The parsing logic:
1. Split text by spaces
2. Collect leading tokens that start with `@` (or are comma-separated @names)
3. Resolve each name against characters in the room (`location.contents`)
4. Return remaining text + resolved targets
5. If no @targets found, return original text + empty list

### Wire into CmdPose

```python
class CmdPose(ArxCommand):
    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            raise CommandError("Pose what?")
        # Parse @targets
        remaining, targets = parse_targets(text, self.caller.location)
        result = {"text": remaining}
        if targets:
            result["targets"] = targets
        return result
```

### Wire into PoseAction

```python
class PoseAction(Action):
    def execute(self, actor, context=None, **kwargs):
        text = kwargs.get("text", "")
        targets = kwargs.get("targets", [])
        ...
        # Pass targets to record_interaction
        target_personas = resolve_target_personas(targets) if targets else None
        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.POSE,
            target_personas=target_personas,
        )
```

Need a helper `resolve_target_personas` that converts character objects to their
active personas via CharacterIdentity.

### Tests
- Parse `"@bob waves hello"` → ("waves hello", [bob])
- Parse `"@bob,@carol waves"` → ("waves", [bob, carol])
- Parse `"waves hello"` → ("waves hello", [])
- Parse `"@nonexistent waves"` → handles gracefully
- Integration: pose with targets creates interaction with target_personas

Commit: `feat: add @target parsing for pose and say commands`

---

## Task 3: Backend — Tabletalk Command

**Files:**
- Modify: `src/commands/evennia_overrides/communication.py` (add CmdTabletalk)
- Modify: `src/commands/default_cmdsets.py` (register command)
- Modify: `src/actions/definitions/communication.py` (add TabletalkAction or reuse PoseAction)
- Test: `src/commands/tests/test_tabletalk.py`

Tabletalk is a pose that goes to the character's current Place. If they're not at a
place, it's an error.

```python
class CmdTabletalk(ArxCommand):
    key = "tt"
    aliases = ["tabletalk"]
    locks = "cmd:all()"
    action = PoseAction()  # Reuse PoseAction

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            raise CommandError("Tabletalk what?")
        # Find current place
        place = get_current_place(self.caller)
        if place is None:
            raise CommandError("You are not at a place. Use 'join <place>' first.")
        return {"text": text, "place": place}
```

PoseAction.execute needs to accept optional `place` kwarg and pass it to
record_interaction.

### Tests
- tt with text at a place → creates interaction with place FK
- tt without being at a place → error
- tt with no text → error

Commit: `feat: add tabletalk (tt) command for place-scoped interactions`

---

## Task 4: Frontend — useThreading Hook

**Files:**
- Create: `frontend/src/scenes/hooks/useThreading.ts`
- Test: `frontend/src/scenes/hooks/__tests__/useThreading.test.ts`

Pure logic hook that groups interactions into threads:

```typescript
interface Thread {
  key: string;           // "room" | "place:123" | "whisper:1,2" | "target:1,2"
  label: string;         // "The Grand Ballroom" | "Table by the fire" | "Whisper: Bob"
  participants: InteractionPersona[];
  latestTimestamp: string;
  unreadCount: number;
  interactions: Interaction[];
}

interface ThreadingState {
  threads: Thread[];
  visibleThreadKeys: Set<string>;   // which threads are shown
  hiddenPersonaIds: Map<string, Set<number>>;  // per-thread hidden personas
  activeThreadKey: string;           // which thread the composer targets
}

function useThreading(interactions: Interaction[], roomName: string) {
  // Group interactions by thread key
  // Track visibility state
  // Track per-thread hidden personas
  // Return threads, filtered interactions, state setters
}
```

Thread key derivation:
```typescript
function getThreadKey(interaction: Interaction): string {
  if (interaction.mode === 'whisper' && interaction.receiver_persona_ids.length > 0) {
    return `whisper:${[...interaction.receiver_persona_ids].sort().join(',')}`;
  }
  if (interaction.place_id) {
    return `place:${interaction.place_id}`;
  }
  if (interaction.target_persona_ids.length > 0) {
    return `target:${[...interaction.target_persona_ids].sort().join(',')}`;
  }
  return 'room';
}
```

### Tests
- Groups room-wide interactions into "room" thread
- Groups place interactions by place ID
- Groups whispers by sorted receiver IDs
- Groups targeted interactions by sorted target IDs
- Filtering: hiding a thread removes its interactions
- Filtering: hiding a persona removes their interactions
- Active thread tracking

Commit: `feat(frontend): add useThreading hook for client-side thread grouping`

---

## Task 5: Frontend — ThreadSidebar Component

**Files:**
- Create: `frontend/src/scenes/components/ThreadSidebar.tsx`
- Test: `frontend/src/scenes/components/__tests__/ThreadSidebar.test.tsx`

Narrow sidebar showing thread bookmarks:

```tsx
interface ThreadSidebarProps {
  threads: Thread[];
  visibleThreadKeys: Set<string>;
  activeThreadKey: string;
  onToggleThread: (key: string) => void;
  onSelectThread: (key: string) => void;
  onShowAll: () => void;
  onOpenFilter: (threadKey: string) => void;
}
```

- "All" button at top (highlighted when no filtering)
- Thread bookmarks below, each showing label + unread count
- Click → toggle visibility + set as active thread
- Right-click → calls onOpenFilter
- Thread labels: room name for room thread, place name for place threads,
  "Whisper: Name" for whisper threads, "Alice, Bob, Carol..." for targeted
  (truncate at 3 with "..." and title attribute for full list)
- Highlighted if visible, dimmed if hidden

### Tests
- Renders All button
- Renders thread bookmarks with labels
- Click toggles thread visibility
- Truncates long participant lists

Commit: `feat(frontend): add ThreadSidebar component`

---

## Task 6: Frontend — ThreadFilterModal Component

**Files:**
- Create: `frontend/src/scenes/components/ThreadFilterModal.tsx`
- Test: `frontend/src/scenes/components/__tests__/ThreadFilterModal.test.tsx`

Modal showing personas in a thread with checkboxes:

```tsx
interface ThreadFilterModalProps {
  thread: Thread;
  hiddenPersonaIds: Set<number>;
  onTogglePersona: (personaId: number) => void;
  onClose: () => void;
}
```

- Shows all personas who have interacted in the thread
- Each has a checkbox (checked = visible, unchecked = hidden)
- Toggling updates immediately (no "apply" button needed)
- Use Radix Dialog for the modal

### Tests
- Shows all personas with checkboxes
- Toggling calls onTogglePersona
- All checked by default

Commit: `feat(frontend): add ThreadFilterModal for per-persona hiding`

---

## Task 7: Frontend — Composer Mode Indicator

**Files:**
- Modify: `frontend/src/components/RichTextInput.tsx` (add mode indicator slot)
- Modify: `frontend/src/game/components/CommandInput.tsx` (mode state + display)
- Test: `frontend/src/game/components/__tests__/CommandInput.test.tsx`

Add a mode indicator to the left of the toolbar in RichTextInput:

```tsx
interface RichTextInputProps {
  ...existing...
  modeLabel?: string;  // e.g., "Pose → Room" or "TT → Table"
}
```

In CommandInput, manage the mode state:
- Default: "Pose → {room name}"
- When a thread bookmark is clicked: update to match thread
- Display as a small label left of the toolbar
- Clicking the mode indicator could cycle through modes (pose/say/whisper) — or just display

The mode indicator is purely visual. The actual command prefix is injected when
the user submits without an explicit command.

### Submit behavior

When the user submits text without a command prefix:
1. Check the mode indicator state
2. If mode is "Pose → Room": prepend `pose ` to the text
3. If mode is "Pose → Bob, Carol": prepend `pose @bob,@carol `
4. If mode is "TT → Table": prepend `tt `
5. If mode is "Whisper → Bob": prepend `whisper @bob `
6. Send the full command via WebSocket

If the user typed an explicit command prefix (text starts with `pose `, `say `,
`tt `, `whisper `, etc.), use that as-is without prepending.

### Tests
- Mode indicator displays current target
- Submitting without prefix prepends the default command
- Explicit command prefix overrides mode indicator
- Mode indicator doesn't erase text on change

Commit: `feat(frontend): add composer mode indicator with smart defaulting`

---

## Task 8: Frontend — Double-Click Persona to Add Target

**Files:**
- Modify: `frontend/src/scenes/components/SceneMessages.tsx`

When a user double-clicks a persona name in the interaction feed, append `@name`
to the command input. This requires the SceneMessages component to communicate
with CommandInput — use a callback prop or a shared context/event.

Simplest approach: a callback prop `onAddTarget(personaName: string)` passed down
from the game page, which CommandInput listens to and appends to the text area.

### Implementation
- Add `onDoubleClickPersona` handler on persona names in SceneMessages
- The handler calls a callback that appends `@{name}` to the command input
- If the command input is empty, also prepend the current mode command

Commit: `feat(frontend): double-click persona name to add as target`

---

## Task 9: Frontend — Integration

**Files:**
- Modify: `frontend/src/scenes/pages/SceneDetailPage.tsx` (add ThreadSidebar)
- Modify: `frontend/src/scenes/components/SceneMessages.tsx` (use useThreading)
- Modify: `frontend/src/game/components/GameWindow.tsx` (or wherever the layout is)

Wire everything together:
1. SceneDetailPage gets a two-column layout: ThreadSidebar on left, feed on right
2. SceneMessages uses useThreading to filter interactions
3. CommandInput receives active thread state for mode indicator
4. Thread bookmark clicks update both the filter and the composer mode
5. Right-click bookmark opens ThreadFilterModal

### Tests
- Integration: selecting a thread filters the feed
- Integration: mode indicator updates when thread selected

Commit: `feat(frontend): wire threading into scene layout`

---

## Task 10: Full Verification

Run:
- `uv run arx test` (full backend)
- `pnpm --dir frontend test -- --run` (all frontend tests)
- `pnpm --dir frontend typecheck && pnpm --dir frontend lint && pnpm --dir frontend build`

Fix any failures.

Commit: `fix: test and lint fixes for conversation threading`

---

## Summary

| Task | What | Backend/Frontend |
|------|------|-----------------|
| 1 | Serializer + WebSocket payload | Backend + Frontend types |
| 2 | @target parsing | Backend |
| 3 | Tabletalk command | Backend |
| 4 | useThreading hook | Frontend |
| 5 | ThreadSidebar | Frontend |
| 6 | ThreadFilterModal | Frontend |
| 7 | Composer mode indicator | Frontend |
| 8 | Double-click add target | Frontend |
| 9 | Integration | Frontend |
| 10 | Full verification | Both |

### Not in this plan
- Account preferences for default filter behavior (future PR)
- Block/ignore system (separate PR, distinct from session-level hiding)
- Shout across rooms (future, treated as room-wide for now)
- Thread unread count persistence across sessions (all client-side, resets)
