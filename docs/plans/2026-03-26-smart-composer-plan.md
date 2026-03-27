# Smart Composer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refine the composer with a mode dropdown, action attachment UI, @name
autocomplete, ghost text, and updated context menus — making the input feel like
a polished MMO chat box.

**Architecture:** Backend adds a read-only ActionTemplate ViewSet for available
actions. Frontend replaces the static mode label with a dropdown, adds an action
attachment button/chip, implements @autocomplete below the textarea, shows ghost
text for current defaults, and extends PersonaContextMenu with action items.

**Tech Stack:** Django/DRF (backend), React 18/TypeScript/Tailwind/Radix UI (frontend),
Vitest (frontend tests), FactoryBoy (backend tests)

**Design doc:** `docs/plans/2026-03-26-smart-composer-design.md`

**Key conventions:**
- Backend: SharedMemoryModel, type annotations, absolute imports, line length 100,
  FilterSets, Prefetch with to_attr
- Frontend: Functional components, React Query, Redux, Radix UI, Tailwind
- Backend tests: `echo "yes" | arx test actions` / `uv run arx test`
- Frontend tests: `pnpm --dir frontend test -- --run`
- Frontend checks: `pnpm --dir frontend typecheck && pnpm --dir frontend lint`

---

## Task 1: Backend — ActionTemplate Read-Only ViewSet

**Files:**
- Create: `src/actions/views.py`
- Create: `src/actions/serializers.py`
- Create: `src/actions/filters.py`
- Modify: `src/actions/urls.py` (create if doesn't exist)
- Modify: `src/server/conf/web_plugins.py` or wherever URLs are registered
- Test: `src/actions/tests/test_views.py`

### Serializer

```python
class ActionTemplateSerializer(serializers.ModelSerializer):
    requires_target = serializers.SerializerMethodField()

    class Meta:
        model = ActionTemplate
        fields = ["id", "name", "description", "target_type", "requires_target"]

    def get_requires_target(self, obj: ActionTemplate) -> bool:
        return obj.target_type in (ActionTargetType.SINGLE, ActionTargetType.FILTERED_GROUP)
```

### ViewSet

Read-only, with filter by target_type. Authentication required.

```python
class ActionTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActionTemplateSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ActionTemplatePagination  # small page size, these are lookup data
    filterset_class = ActionTemplateFilter
    queryset = ActionTemplate.objects.all()
```

### Filter

```python
class ActionTemplateFilter(django_filters.FilterSet):
    target_type = django_filters.CharFilter(field_name="target_type")

    class Meta:
        model = ActionTemplate
        fields = ["target_type"]
```

### URL Registration

Register at `/api/action-templates/`. Check how other apps register URLs
(look at `src/world/scenes/urls.py` for the pattern) and follow the same
approach. The actions app may need a `urls.py` and registration in the
main URL config.

### Tests
- List endpoint returns action templates
- Authenticated only
- Filter by target_type works
- requires_target is true for SINGLE/FILTERED_GROUP, false for SELF/AREA

Commit: `feat(actions): add read-only ActionTemplate API`

---

## Task 2: Frontend — ModeSelector Dropdown

**Files:**
- Create: `frontend/src/scenes/components/ModeSelector.tsx`
- Create: `frontend/src/scenes/components/ModeSelector.test.tsx`
- Modify: `frontend/src/components/RichTextInput.tsx` (replace modeLabel with slot)
- Modify: `frontend/src/game/components/CommandInput.tsx`

### ModeSelector Component

A Radix DropdownMenu showing communication modes:

```tsx
interface ModeSelectorProps {
  currentMode: string;           // "pose" | "say" | "emit" | "whisper" | "shout" | "tt"
  onModeChange: (mode: string) => void;
  isAtPlace: boolean;            // controls TT visibility
}

const COMMUNICATION_MODES = [
  { key: 'pose', label: 'Pose', icon: '✍' },
  { key: 'say', label: 'Say', icon: '💬' },
  { key: 'emit', label: 'Emit', icon: '📝' },
  { key: 'whisper', label: 'Whisper', icon: '🤫' },
  { key: 'shout', label: 'Shout', icon: '📢' },
  { key: 'tt', label: 'Tabletalk', icon: '🪑' },
];
```

Renders as a compact button: `[▾ Pose]`. Opens dropdown on click. TT hidden
if `isAtPlace` is false. Selecting a mode calls `onModeChange` and closes.

Use Radix `DropdownMenu` from `frontend/src/components/ui/dropdown-menu.tsx`.

### RichTextInput Update

Replace the `modeLabel` string prop with a `leftSlot` React node:

```tsx
interface RichTextInputProps {
  ...existing...
  leftSlot?: React.ReactNode;  // replaces modeLabel
}
```

This lets the parent pass the ModeSelector component (or any other element)
into the toolbar area. Remove the old `modeLabel` rendering.

### CommandInput Update

Replace `modeLabel={composerMode?.label}` with the ModeSelector:

```tsx
<RichTextInput
  leftSlot={
    <ModeSelector
      currentMode={composerMode?.command ?? 'pose'}
      onModeChange={handleModeChange}
      isAtPlace={isAtPlace}
    />
  }
  ...
/>
```

`handleModeChange` updates the `composerMode` command while preserving targets.

### Tests
- Renders current mode label
- Opens dropdown on click
- All communication modes shown
- TT hidden when not at place
- Selecting mode calls onModeChange

Commit: `feat(frontend): ModeSelector dropdown replacing static label`

---

## Task 3: Frontend — Ghost Text

**Files:**
- Modify: `frontend/src/components/RichTextInput.tsx`
- Modify: `frontend/src/game/components/CommandInput.tsx`

### Ghost Text in RichTextInput

Add a `ghostText` prop that renders as light grey text behind the textarea
when the input is empty:

```tsx
interface RichTextInputProps {
  ...existing...
  ghostText?: string;
}
```

Implementation: overlay a div with the ghost text behind the textarea. The
textarea has a transparent background so the ghost shows through. When the
user types, the ghost text is hidden (via the `value` being non-empty).

```tsx
<div className="relative">
  {!value && ghostText && (
    <div className="pointer-events-none absolute inset-0 px-3 py-2 text-muted-foreground/50 text-sm">
      {ghostText}
    </div>
  )}
  <Textarea
    ref={textareaRef}
    value={value}
    className="bg-transparent ..."
    ...
  />
</div>
```

### CommandInput Ghost Text

Build the ghost text string from the current composer state:

```typescript
function buildGhostText(mode: ComposerMode, actionAttachment?: ActionInfo): string {
  let text = `${capitalize(mode.command)}`;
  if (mode.targets.length > 0) {
    text += ` → ${mode.targets.join(', ')}`;
  } else if (mode.label) {
    // Extract the "→ XXX" part from the label
    text = mode.label;
  }
  if (actionAttachment) {
    text += ` | ⚔ ${actionAttachment.name}`;
    if (actionAttachment.target) {
      text += ` → ${actionAttachment.target}`;
    }
  }
  return text;
}
```

Remove the old placeholder="Write a pose..." from RichTextInput usage.

### Tests
- Ghost text shows when input is empty
- Ghost text hides when input has content
- Ghost text reflects current mode
- No placeholder text

Commit: `feat(frontend): ghost text showing current composer defaults`

---

## Task 4: Frontend — @Name Autocomplete

**Files:**
- Create: `frontend/src/components/NameAutocomplete.tsx`
- Create: `frontend/src/components/__tests__/NameAutocomplete.test.tsx`
- Modify: `frontend/src/components/RichTextInput.tsx`

### NameAutocomplete Component

A dropdown that appears below the textarea when `@` is typed:

```tsx
interface NameAutocompleteProps {
  characters: Array<{ name: string; thumbnail_url?: string }>;
  query: string;              // text after the @
  onSelect: (name: string) => void;
  onDismiss: () => void;
}
```

- Shows filtered list of characters matching the query
- Each item: thumbnail + name
- Arrow keys navigate, Enter/Tab selects, Escape dismisses
- Anchored below the textarea (Discord-style, not at cursor)

### RichTextInput Integration

Add @-detection logic to RichTextInput:

```tsx
// New props:
interface RichTextInputProps {
  ...existing...
  autocompleteItems?: Array<{ name: string; thumbnail_url?: string }>;
}
```

On every keystroke, check if the user is currently typing an @mention:
1. Find the last `@` before the cursor
2. If found and preceded by a space or start-of-input, extract the query text
3. Show NameAutocomplete with the query
4. On select, replace the `@query` with `@fullname`

The character list comes from the room state in Redux (already available via
`state.game.sessions[char].room.characters`). The parent passes it as
`autocompleteItems`.

### Tests
- Typing `@` shows autocomplete dropdown
- Typing `@bo` filters to names starting with "bo"
- Selecting inserts the full name
- Escape dismisses
- Arrow keys navigate the list
- No dropdown when @ is in the middle of a word

Commit: `feat(frontend): @name autocomplete for character targeting`

---

## Task 5: Frontend — Action Attachment

**Files:**
- Create: `frontend/src/scenes/components/ActionAttachment.tsx`
- Create: `frontend/src/scenes/components/ActionAttachment.test.tsx`
- Create: `frontend/src/scenes/hooks/useAvailableActions.ts`
- Modify: `frontend/src/game/components/CommandInput.tsx`

### useAvailableActions Hook

React Query hook that lazy-loads ActionTemplates:

```typescript
function useAvailableActions(enabled: boolean) {
  return useQuery({
    queryKey: ['action-templates'],
    queryFn: () => apiFetch('/api/action-templates/').then(r => r.json()),
    enabled,
    staleTime: 60_000,   // cache for 60 seconds
  });
}
```

Only fetches when `enabled` is true (first time the action popover opens).

### ActionAttachment Component

```tsx
interface ActionAttachmentProps {
  attachment: ActionInfo | null;        // current attached action
  onAttach: (action: ActionInfo) => void;
  onDetach: () => void;
  availableActions: ActionTemplate[];
  isLoading: boolean;
  targetName?: string;                  // if a target is already set
}

interface ActionInfo {
  templateId: number;
  name: string;
  target?: string;
  requiresTarget: boolean;
}
```

Renders:
- ⚡ button in the toolbar
- On click: if action already attached, detach it (toggle). If no action,
  open Radix Popover with action list.
- Popover shows available actions with names. Loading spinner while fetching.
- Selecting an action calls onAttach
- When attached: show chip `⚔ Flirt → Bob` next to the button. Clicking
  the chip also detaches.

### CommandInput Integration

Add action state to CommandInput:

```typescript
const [actionAttachment, setActionAttachment] = useState<ActionInfo | null>(null);
const [actionsPopoverOpen, setActionsPopoverOpen] = useState(false);
const { data: actions, isLoading } = useAvailableActions(actionsPopoverOpen);
```

On submit with action attached:
1. Send the pose via WebSocket (existing flow)
2. Wait for INTERACTION WebSocket response (get the interaction ID)
3. POST to `/api/scene-action-requests/` with the action template + target + interaction
4. Clear the action attachment

### Tests
- ⚡ button renders
- Clicking opens popover with actions
- Selecting attaches action (chip shows)
- Clicking chip detaches
- Toggle: click ⚡ when attached → detaches

Commit: `feat(frontend): action attachment with lazy-loaded templates`

---

## Task 6: Frontend — PersonaContextMenu Actions

**Files:**
- Modify: `frontend/src/scenes/components/PersonaContextMenu.tsx`

### Extend Context Menu

Read the current PersonaContextMenu. Add action items below the existing
"Add as target" option:

```tsx
// After "Add as target" separator:
<ContextMenuSeparator />
<ContextMenuLabel>Actions</ContextMenuLabel>
{availableActions?.map(action => (
  <ContextMenuItem
    key={action.id}
    onSelect={() => onAttachAction({
      templateId: action.id,
      name: action.name,
      target: personaName,
      requiresTarget: action.requires_target,
    })}
  >
    ⚔ {action.name}
  </ContextMenuItem>
))}
```

The action list shares the same `useAvailableActions` cache. Right-clicking
a persona name auto-sets both the target AND the action.

### Props Update

Add `onAttachAction` callback prop to PersonaContextMenu.

### Tests
- Context menu shows action items
- Selecting action calls onAttachAction with persona name as target

Commit: `feat(frontend): actions in persona context menu`

---

## Task 7: Frontend — Submit with Action (WebSocket + REST)

**Files:**
- Modify: `frontend/src/game/components/CommandInput.tsx`
- Modify: `frontend/src/scenes/queries.ts` (add action request function)

### Action Request API Function

```typescript
export async function createSceneActionRequest(data: {
  scene: number;
  action_template: number;
  target_persona: number;
  interaction?: number;
}) {
  const res = await apiFetch('/api/scene-action-requests/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create action request');
  return res.json();
}
```

### Submit Flow

In CommandInput.handleSubmit, when an action is attached:

```typescript
// 1. Send pose via WebSocket (existing)
send(character, fullCommand);

// 2. Wait for the INTERACTION response to get the ID
// Listen for the next INTERACTION WebSocket message matching our content
// Use a one-time listener or a small state machine

// 3. POST action request
if (actionAttachment) {
  // The interaction ID comes back via the WebSocket INTERACTION payload.
  // Use a callback/promise pattern to capture it:
  waitForInteractionId().then((interactionId) => {
    createSceneActionRequest({
      scene: sceneId,
      action_template: actionAttachment.templateId,
      target_persona: targetPersonaId,
      interaction: interactionId,
    });
  });
  setActionAttachment(null);
}
```

For the "wait for interaction ID" pattern: add a one-time callback to the
WebSocket handler that resolves when an INTERACTION message with matching
content arrives. Or simpler: store the action request data and submit it
when the next INTERACTION WebSocket message arrives in the scene.

### Tests
- Submit with action sends pose AND creates action request
- Submit without action just sends pose
- Action attachment cleared after submit

Commit: `feat(frontend): atomic pose + action submit via WebSocket + REST`

---

## Task 8: Full Verification

Run:
- `uv run arx test` (full backend)
- `pnpm --dir frontend test -- --run`
- `pnpm --dir frontend typecheck && pnpm --dir frontend lint && pnpm --dir frontend build`

Fix any failures.

Commit: `fix: test and lint fixes for smart composer`

---

## Summary

| Task | What | Backend/Frontend |
|------|------|-----------------|
| 1 | ActionTemplate ViewSet | Backend |
| 2 | ModeSelector dropdown | Frontend |
| 3 | Ghost text | Frontend |
| 4 | @Name autocomplete | Frontend |
| 5 | Action attachment UI | Frontend |
| 6 | PersonaContextMenu actions | Frontend |
| 7 | Submit with action | Frontend |
| 8 | Full verification | Both |

### Not in this plan
- Prerequisite checking for actions (graying out unavailable) — future iteration
- Action resolution/consent flow UI refinement — TehomCD's domain
- Shout across rooms implementation — future
