# SceneMessage Deprecation Design

**Date:** 2026-03-23
**Status:** Design
**Depends on:** Interaction system (built), Persona simplification (built)

## Problem Statement

The SceneMessage model is the legacy way scene RP is recorded. The Interaction model
replaces it with better privacy controls, guise/persona-based identity, and partitioned
storage. The frontend still reads SceneMessages via REST API for scene history, while
real-time RP arrives via WebSocket. Both need to switch to Interactions.

## Current Architecture

Two separate systems handle RP display in the frontend:

### Real-Time Feed (WebSocket)
```
Player poses → PoseAction → message_location() → Evennia msg_contents()
  → WebSocket push → useGameSocket → parseGameMessage() → Redux store
  → Game UI renders immediately
```

This is already real-time. Messages arrive as raw text strings through Evennia's
WebSocket. The frontend stores them in Redux as `GameMessage` objects with `content`,
`timestamp`, and `type`. They're displayed as plain text in the game interface.

**Problem:** These messages have no structure — no persona name, no mode indicator,
no interaction ID. They're just raw text strings that Evennia's funcparser resolved.
There's no way to favorite them, mark them private, or reference them for relationships.

### Historical Scene View (REST API)
```
SceneDetailPage → GET /api/messages/?scene={id} → SceneMessageSerializer
  → Renders with persona name, thumbnail, reactions
```

This is polled every 60 seconds for active scenes. It shows structured data (persona,
content, reactions) but is slow and separate from the real-time feed.

**Problem:** Uses SceneMessage, not Interaction. Needs to switch.

## Target Architecture

### Real-Time Feed for Active Scene Participants (WebSocket)

When `record_interaction()` creates an Interaction, it also pushes a structured
payload through the WebSocket to all connected clients in the room:

```
Player poses → PoseAction →
  1. message_location() broadcasts raw text (Evennia real-time delivery)
  2. record_interaction() creates Interaction record
  3. push_interaction() sends structured payload via WebSocket
```

The WebSocket payload includes the Interaction's structured data:

```typescript
interface InteractionPayload {
  id: number;
  persona: { id: number; name: string; thumbnail_url?: string };
  content: string;
  mode: string;  // pose, say, whisper, etc.
  timestamp: string;
  scene_id: number | null;
  target_personas: { id: number; name: string }[];
}
```

The frontend receives this as a new `WS_MESSAGE_TYPE.INTERACTION` and adds it
to the scene's interaction list in real-time. No polling needed for active
participants.

### Historical Scene View for Non-Participants (REST API)

SceneDetailPage switches from `/api/messages/` to `/api/interactions/?scene={id}`.
Uses the existing InteractionViewSet with cursor pagination. The 60-second poll
stays for non-participants browsing finished scenes — they don't need real-time.

For active participants who are IN the scene, the page uses the WebSocket feed
instead of polling. The REST endpoint loads initial history on page open, then
WebSocket handles new interactions.

## Backend Changes

### 1. InteractionReaction Model (new)

Simple reaction model on Interaction, replacing SceneMessageReaction:

```
InteractionReaction (SharedMemoryModel)
├── interaction: FK Interaction (db_constraint=False for partitioned table)
├── timestamp: DateTimeField (denormalized for composite FK)
├── account: FK AccountDB
├── emoji: CharField(32)
├── created_at: DateTimeField
├── Unique: (interaction, account, emoji)
```

This is a bridge — it will be replaced by the proper kudos/voting/favorite
engagement system later.

### 2. push_interaction() Service Function

New function in `interaction_services.py` that sends a structured interaction
payload to connected clients via Evennia's `msg()`:

```python
def push_interaction(interaction: Interaction) -> None:
    """Push a structured interaction payload to all audience members via WebSocket."""
    location = interaction.persona.character.location
    if location is None:
        return

    payload = {
        "id": interaction.pk,
        "persona": {
            "id": interaction.persona_id,
            "name": interaction.persona.name,
            "thumbnail_url": interaction.persona.thumbnail_url,
        },
        "content": interaction.content,
        "mode": interaction.mode,
        "timestamp": interaction.timestamp.isoformat(),
        "scene_id": interaction.scene_id,
    }

    # Send to all connected clients in the room
    for obj in location.contents:
        try:
            obj.msg(interaction=((), payload))
        except (AttributeError, TypeError):
            continue
```

This uses Evennia's `msg()` which routes through the WebSocket to connected
clients. The message type `interaction` becomes a new `WS_MESSAGE_TYPE`.

### 3. Wire push_interaction into record_interaction

After `create_interaction()` returns a non-None Interaction, call
`push_interaction()` to deliver it in real-time.

### 4. Update Action Classes

PoseAction/SayAction currently call both `message_location()` (raw broadcast)
and `record_interaction()` (persistence). With push_interaction wired into
record_interaction, the structured payload is delivered automatically.

The raw `message_location()` broadcast is still needed for:
- Telnet clients that don't understand structured payloads
- Characters without CharacterIdentity (NPCs, system objects)
- The case where record_interaction returns None (solo in room)

So both calls stay. The frontend will eventually prefer the structured
interaction payload over the raw text, but both are delivered.

### 5. Interaction Serializer Updates

The `InteractionListSerializer` needs to include reaction data (once
InteractionReaction exists) in the same shape the frontend expects:

```python
reactions = serializers.SerializerMethodField()

def get_reactions(self, obj):
    # Aggregate emoji counts, include whether current user reacted
    ...
```

## Frontend Changes

### 1. New WebSocket Message Type

Add `INTERACTION` to `WS_MESSAGE_TYPE` in `hooks/types.ts`:

```typescript
export const WS_MESSAGE_TYPE = {
  // ... existing types
  INTERACTION: 'interaction',
} as const;
```

Add `InteractionPayload` interface to types.

### 2. Handle Interaction Payloads

In `useGameSocket.ts`, add a handler for the new message type:

```typescript
if (msgType === WS_MESSAGE_TYPE.INTERACTION) {
  handleInteractionPayload(character, kwargs as InteractionPayload, dispatch);
  return;
}
```

The handler adds the interaction to a scene-specific interaction list in Redux
(or React Query cache) so it renders immediately.

### 3. SceneDetailPage — Dual Mode

When the user is an active participant in the scene:
- Load initial history via REST (`/api/interactions/?scene={id}`)
- Receive new interactions via WebSocket (no polling)
- Merge both into a single chronological feed

When the user is browsing a finished/inactive scene:
- Load history via REST with cursor pagination
- No WebSocket (scene is done)

### 4. Interaction Component

Replace SceneMessages component (or create a new one) that renders Interactions:
- Persona name + thumbnail
- Content with mode-appropriate formatting (SAY gets quotes, POSE is raw, etc.)
- Reaction buttons (bridge until kudos system)
- Favorite button (private bookmark)
- Timestamp
- Privacy indicator (if applicable)

### 5. Scene Queries

New query functions in `scenes/queries.ts`:
- `fetchInteractions(sceneId, cursor)` — replaces `fetchSceneMessages`
- `postInteractionReaction(interactionId, emoji)` — replaces message reactions
- `toggleInteractionFavorite(interactionId)` — new

## Migration Path

### Phase 1: Backend (this PR)
- Add InteractionReaction model + migration
- Add push_interaction() service
- Wire into record_interaction()
- Add reaction serializer support to InteractionViewSet
- Add InteractionReactionViewSet

### Phase 2: Frontend
- Add INTERACTION WebSocket handler
- Create Interaction display component
- Update SceneDetailPage to use Interactions
- Update scene queries to use Interaction API
- Implement dual mode (WebSocket for active, REST for history)

### Phase 3: Cleanup
- Remove SceneMessage creation from any remaining code paths
- Remove SceneMessageViewSet, serializer, tests
- Remove SceneMessage model (or mark as legacy)
- Remove old SceneMessages component

## What About message_location()?

`message_location()` stays as a raw text broadcast for telnet compatibility.
The frontend will receive BOTH the raw text message (via TEXT type) and the
structured interaction payload (via INTERACTION type). The frontend should
prefer the structured payload and ignore the raw text when both arrive for
the same action.

To avoid duplicate display, the frontend can:
- Check if a TEXT message arrived within the same timestamp as an INTERACTION
- Or: suppress TEXT messages entirely when in a scene with active interactions
- Or: have the backend skip `message_location()` for web clients and only
  use `push_interaction()` — but this breaks telnet

The simplest approach: the game UI component that displays the scene feed
reads from the interaction list (populated by WebSocket INTERACTION payloads),
not from the general message list (populated by TEXT payloads). The general
message list continues to show system messages, channels, etc. — just not
scene RP.

## Open Questions

1. **Reaction bridge model** — Should InteractionReaction denormalize
   `timestamp` for the partitioned table FK, like InteractionAudience does?
   Probably yes for consistency.

2. **WebSocket payload size** — Each interaction payload is ~200-500 bytes.
   In a room with 30 people, each pose generates 30 WebSocket pushes of
   this size. At thousands of concurrent users with average 10 people per
   room, that's manageable. But rooms with 50+ people during events could
   create burst traffic. Monitor and batch if needed.

3. **Deduplication** — The frontend will receive both a raw TEXT message and
   a structured INTERACTION payload for the same pose. Need a clean strategy
   for which one to display. The scene feed should use INTERACTION only;
   the general chat log can use TEXT for non-scene messages.
