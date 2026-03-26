# Smart Composer Design

**Date:** 2026-03-26
**Status:** Design
**Depends on:** Conversation threading (built), Rich text editor (built), Scene actions (built)

## Problem Statement

The current composer has a static mode label, no way to switch modes without typing
commands or clicking thread bookmarks, no autocomplete for @mentions, and no way to
attach mechanical actions (flirt, intimidate) to poses from the UI. The composer
needs to feel like a polished MMO chat input that experienced RP writers won't find
patronizing.

## Composer Layout

```
[▾ Pose ▾] [B] [I] [S] [🎨] [⚡]  [⚔ Flirt → Bob]
[                                                   ]
[  Pose → The Grand Ballroom                        ]  ← ghost text, disappears on type
[                                                   ]
```

### Components (left to right)

**Mode Dropdown** — Clickable button showing current communication mode. Opens a
small dropdown with: Pose, Say, Emit, Whisper, Shout, Tabletalk (TT only if at a
place). Selecting a mode updates the composer default. Communication modes only —
actions are separate.

**Formatting Toolbar** — Bold, Italic, Strikethrough, Color picker. Already built.

**Action Button (⚡)** — Opens a popover with available actions. Lazy-loads
ActionTemplates from backend on first click (cached for session). Selecting an
action attaches it to the next submit. Clicking the action button again when an
action is already attached clears/detaches it (toggle behavior).

**Action Indicator** — When an action is attached, a chip appears in the toolbar
area: `⚔ Flirt → Bob`. Clicking the chip also detaches the action.

**Text Area** — Free-form rich text input. No placeholder text. Ghost text in light
grey shows the current default state (e.g., "Pose → The Grand Ballroom" or
"Whisper → Bob | ⚔ Flirt"). Ghost text disappears when the user starts typing and
reappears when the input is empty.

## Mode Dropdown

### Communication Modes

| Mode | Key | Always Available | Notes |
|------|-----|-----------------|-------|
| Pose | pose | Yes | Default. Free-form emoting |
| Say | say | Yes | Speech with quotes |
| Emit | emote | Yes | Third-person narration |
| Whisper | whisper | Yes | Private to target(s) |
| Shout | shout | Yes | Echoes to adjacent rooms |
| Tabletalk | tt | Only if at a Place | Scoped to current place |

### Dropdown Behavior

- Opens below the mode button
- Shows icon + name for each mode
- TT is grayed out / hidden if character isn't at a place
- Selecting a mode closes the dropdown and updates the ghost text
- Mode persists across submits (continue the conversation)
- Thread bookmark clicks also update the mode (existing behavior)

### No Actions in the Dropdown

Actions (flirt, intimidate, etc.) are NOT in the mode dropdown. They are attached
separately via the action button or right-click context menu. This keeps the
dropdown clean and fast — just 5-6 communication modes, not a growing list of
game mechanics.

## Action Attachment

### Via Action Button (⚡)

1. Click the ⚡ button in the toolbar
2. Popover opens with categorized action list
3. **First open**: fetches available ActionTemplates from backend (shows loading)
4. **Subsequent opens**: uses cached data (re-fetch on room change or periodically)
5. Each action shows: icon, name, whether it requires a target
6. Grayed out with tooltip if prerequisites not met
7. Select an action → action attaches to the composer
8. If action needs a target and none is set, prompt for target selection
9. Click ⚡ again or click the action chip → detaches the action (toggle)

### Via Right-Click Persona in Feed

The PersonaContextMenu (already built) is extended:

1. Right-click persona name → context menu shows:
   - "Add as target" (existing, adds @name)
   - Separator
   - Available actions: "Flirt with {name}", "Intimidate {name}", etc.
2. Selecting an action auto-sets the target AND attaches the action
3. Action chip appears in composer

### Action Indicator Chip

When an action is attached, a small chip appears in the toolbar area:
- `⚔ Flirt → Bob` (action + target)
- `⚔ Intimidate` (action without target, if the action doesn't require one)
- `⚔ Flirt (select target)` (action requires target but none set yet)
- Clicking the chip detaches the action

### Submit with Action

When Enter is pressed with an action attached:
1. The communication (pose text + mode + targets) is sent as an Interaction
2. The action is sent as a SceneActionRequest linked to the same scene
3. Both are created atomically on the backend
4. The action chip is cleared after submit
5. The communication mode and targets persist (continue the conversation)

## @Name Autocomplete

When the user types `@` in the text area, a dropdown appears showing characters
in the current room:

- Filters as you type: `@bo` shows "Bob", "Bobby", etc.
- Shows persona name + thumbnail
- Arrow keys to navigate, Enter/Tab to select
- Selecting inserts the full name: `@Bob`
- Escape or clicking away dismisses without selecting
- Only shows characters in the room (from room state data already in Redux)

### Implementation

- Trigger: detect `@` character typed (not at the start of a word — only after
  a space or at the start of input)
- Source: room state characters from Redux (`state.game.sessions[char].room.characters`)
- Position: dropdown anchored below the cursor position in the textarea
- Dismiss: on blur, Escape, or selecting

### Edge Cases

- Names with spaces: `@Crucible Mundi` — the autocomplete inserts the full name.
  The @target parser on the backend handles comma separation for multi-word names.
- No characters in room: dropdown doesn't appear
- `@@` or `@` at end of text: just shows the full list

## Ghost Text

When the text area is empty, light grey text shows the current composer state:

- `Pose → The Grand Ballroom` (default, no targets, no action)
- `Say → The Grand Ballroom` (say mode selected)
- `Whisper → Bob` (whisper mode with target)
- `Pose → Bob, Carol` (pose with targets from thread)
- `TT → Table by the fire` (tabletalk mode)
- `Pose → The Grand Ballroom | ⚔ Flirt → Bob` (pose with action attached)

Ghost text disappears instantly when any character is typed. Reappears when input
is cleared (after submit or manual clear).

This replaces both the old placeholder text ("Write a pose...") and the separate
mode label pill. The ghost text IS the mode indicator, just displayed in the
natural place where the user is looking — the text area itself.

## Backend Changes

### Action Submission Endpoint

The frontend needs to submit a pose + action atomically. Options:

**A) Extend the WebSocket command**: The command text includes action metadata:
`pose @bob waves flirtatiously --action=flirt --target=bob`

**B) REST endpoint**: After the pose command is sent via WebSocket, immediately
POST to `/api/scene-action-requests/` with the interaction reference.

**C) New combined WebSocket message type**: Send a structured payload via WebSocket
that includes both the pose data and the action data.

Recommendation: **B** — keep the WebSocket command for the communication (pose) and
use a REST call for the action request. The SceneActionRequest API already exists.
The frontend sends the pose via WebSocket, then immediately POSTs the action request.
They're linked by scene + timestamp proximity. This avoids changing the command
protocol.

Actually, the action request should reference the interaction. Since `push_interaction`
returns the interaction ID via WebSocket, the frontend can capture that ID and include
it in the action request POST. Sequence:

1. Send pose via WebSocket
2. Receive INTERACTION payload back (includes `id`)
3. POST action request with `interaction_id` reference

This requires the frontend to wait for the WebSocket response before POSTing the
action. A small latency (milliseconds) but ensures the link is correct.

### Available Actions Endpoint

The frontend needs to know what actions are available to the character:

`GET /api/action-templates/?available_for={character_id}`

Returns ActionTemplates the character can use, with:
- name, icon, category
- requires_target: boolean
- prerequisites_met: boolean (with reason if not met)

This endpoint should be efficient — cache ActionTemplates (they're lookup data)
and compute prerequisite checks per-character.

Check if this endpoint already exists from TehomCD's scene actions PR.

## Frontend Components

### ModeSelector

New component replacing the static mode label:

```
frontend/src/scenes/components/ModeSelector.tsx
```

- Renders as a compact button showing current mode
- Opens Radix DropdownMenu with communication modes
- TT conditionally shown based on place presence
- Emits mode changes to parent

### ActionAttachment

New component for the action button + indicator:

```
frontend/src/scenes/components/ActionAttachment.tsx
```

- ⚡ button that opens action selector popover
- Lazy-loads available actions on first open
- Shows action chip when attached
- Toggle behavior (click again to detach)

### NameAutocomplete

New component for @mention autocomplete:

```
frontend/src/components/NameAutocomplete.tsx
```

- Monitors textarea for `@` trigger
- Shows filtered dropdown of room characters
- Handles selection and insertion

### Updated PersonaContextMenu

Extend existing component to include available actions:

```
frontend/src/scenes/components/PersonaContextMenu.tsx
```

- Add action items below "Add as target"
- Lazy-load available actions (share cache with ActionAttachment)

## Open Questions

1. **Action request timing** — Should the frontend wait for the INTERACTION WebSocket
   response before POSTing the action request, or can they fire simultaneously? Waiting
   ensures a clean link but adds latency. Firing simultaneously risks the action
   request arriving before the interaction is created.

2. **Action availability caching** — How long to cache the available actions list?
   Character abilities could change mid-scene (conditions applied, items equipped).
   Suggestion: cache for 60 seconds, re-fetch on room change.

3. **Textarea cursor positioning for autocomplete** — Getting the cursor position
   within a textarea for dropdown anchoring is notoriously tricky. May need a
   library like `textarea-caret-position` or a contentEditable approach. Worth
   investigating before committing to the implementation approach.
