# CharacterIdentity & Interaction Wiring Design

**Date:** 2026-03-21
**Status:** Design
**Depends on:** Interaction system (built), Identity hierarchy (built), Guise (existing)
**Blocks:** Communication flow integration, action-type interactions, SceneMessage deprecation

## Problem Statement

There is no single source of truth for "who is this character right now?" Guises, personas,
and character sheets all point independently to ObjectDB. The interaction system needs a
non-nullable persona for every record, but there's no clean way to resolve a character's
current persona. Additionally, `message_location()` still creates SceneMessages instead of
Interactions, and only records when a scene is active.

## CharacterIdentity Model

A new model that sits alongside CharacterSheet as the identity anchor for a character.
CharacterSheet = what they are (stats, demographics). CharacterIdentity = who they present
as and what they know.

```
CharacterIdentity (SharedMemoryModel, OneToOne with ObjectDB)
├── character: OneToOneField ObjectDB
├── primary_guise: FK Guise (non-nullable — their "real" identity)
├── active_guise: FK Guise (non-nullable — defaults to primary_guise)
├── active_persona: FK Persona (non-nullable — defaults to active_guise's default persona)
```

**All three FKs are non-nullable.** At any point in time, you can ask "who is this character
right now?" and get a definitive answer.

### Lifecycle

- **Character creation:** CharacterIdentity created alongside CharacterSheet. A default guise
  is created with the character's name and `is_default=True`. A default persona is created
  from that guise with `is_fake_name=False`. All three FKs point to these defaults.
- **Guise switching:** Player activates an alternate guise (e.g., secret identity "The Masked
  Robber"). `active_guise` changes. `active_persona` changes to that guise's default persona.
- **Disguise application:** Player puts on a temporary disguise in a scene. A new persona is
  created on the active guise with `is_fake_name=True` and a custom name. `active_persona`
  changes to this disguise persona.
- **Disguise removal:** Player removes the disguise. `active_persona` reverts to the active
  guise's default persona.
- **Login:** Character enters the game. CharacterIdentity persists — they resume as whoever
  they were.

### Resolution for Interactions

`record_interaction()` just reads `character_identity.active_persona`. Always valid, always
non-nullable. No resolution logic, no creation, no guessing.

### Future: Knowledge Anchor

CharacterIdentity will also anchor what a character knows:
- PersonaIdentification (already built — "this character identified that disguise")
- Codex knowledge entries (future — what lore/secrets the character has discovered)
- Any other knowledge that persists through RosterEntry changes (new players of the same
  character inherit the character's knowledge, not the previous player's)

This is the "Character model" we identified as a TODO — CharacterIdentity fills that role
for identity and knowledge, while CharacterSheet continues to handle demographics and stats.

## Interaction Wiring: Separated Broadcast and Record

### Architecture

Two independent concerns, called explicitly by action classes:

**Broadcast (real-time delivery):** `message_location()` stays as a pure broadcast function.
Sends text to connected clients in the room via Evennia's `msg_contents`. No persistence,
no database writes. All SceneMessage/Persona/Participation creation code is removed from it.

**Record (persistence):** `record_interaction()` is a new service function in
`world/scenes/interaction_services.py`. Handles all interaction persistence logic.

Action classes call both explicitly:
```python
class PoseAction(Action):
    def execute(self, actor, context, **kwargs):
        # 1. Broadcast to room (real-time delivery)
        message_location(caller_state, text)
        # 2. Record the interaction (persistence)
        record_interaction(character=actor, content=text, mode=InteractionMode.POSE)
```

Future action-type interactions (FlirtAction, TauntAction, etc.) call
`record_interaction()` directly with `mode=ACTION` and attach check results.

### record_interaction() Service Function

```python
def record_interaction(
    *,
    character: ObjectDB,
    content: str,
    mode: str,
    scene: Scene | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
```

Steps:
1. Get `character_identity = character.character_identity`
2. Get `persona = character_identity.active_persona` (always valid, never creates)
3. Resolve audience: other characters in the room → their active guises
4. If audience is empty (solo in room), return None — no interaction recorded
5. If scene is ephemeral, return None — content never stored
6. Call `create_interaction(persona=persona, content=content, mode=mode, ...)`
7. Return the Interaction

### Audience Resolution

A helper function resolves the audience from the room:

```python
def resolve_audience(character: ObjectDB) -> list[Guise]:
    """Get the active guises of all other characters in the room."""
```

This looks at `character.location.contents`, filters to characters (not objects/exits),
excludes the acting character, and returns each one's
`character_identity.active_guise`. Characters without a CharacterIdentity (NPCs, etc.)
are skipped.

### Why Interactions Only Record With an Audience

Interactions are the RP memory system — they exist so players can reference them for
relationship updates and browse their character's history. A character alone in a room
isn't interacting with anyone. Recording solo poses would create massive noise in the
interaction ledger with zero value.

The broadcast still happens (the player sees their own pose). Only persistence is skipped.

## SceneMessage Deprecation

### Migration Path

SceneMessage is replaced by Interaction for all new RP recording. The transition:

1. **Phase 1 (this work):** `record_interaction()` creates Interactions. `message_location()`
   stops creating SceneMessages. Old SceneMessage data is preserved but no new records
   are created.

2. **Phase 2 (frontend):** Scene detail views switch from querying SceneMessage to querying
   Interaction (filtered by scene FK). The frontend components update to use the
   Interaction serializer format.

3. **Phase 3 (cleanup):** Once the frontend is fully migrated, SceneMessage model and
   related code (SceneMessageViewSet, serializers, factories) can be removed. No rush —
   the model doesn't hurt anything sitting there unused.

### What SceneMessage Did That Interaction Now Handles

| SceneMessage feature | Interaction equivalent |
|---|---|
| `scene` FK | `scene` FK (same) |
| `persona` FK | `persona` FK (same) |
| `content` | `content` (same) |
| `context` (PUBLIC/TABLETALK/PRIVATE) | Derived from audience scope + scene privacy_mode |
| `mode` (POSE/EMIT/SAY/WHISPER/OOC) | `mode` (POSE/EMIT/SAY/WHISPER/SHOUT/ACTION, no OOC) |
| `receivers` M2M | InteractionAudience (guise-based) |
| `sequence_number` | `timestamp` microsecond precision (sufficient) |
| `SceneMessageSupplementalData` | Future: supplemental data for ACTION mode interactions |

### What SceneMessage Had That Interaction Does NOT Need

- **OOC mode:** Interactions are purely IC. OOC communication uses a different channel.
- **MessageContext (PUBLIC/TABLETALK/PRIVATE):** The privacy tier system (4-tier model)
  replaces this with more granular control.
- **`sequence_number`:** Microsecond timestamps provide sufficient ordering.

## Action-Type Interaction Support

The Interaction model's `mode=ACTION` covers mechanical actions (flirt, seduce, taunt,
pickpocket, cast spell). These are future Action subclasses that:

1. Accept text (the player's pose describing what they're doing)
2. Execute a mechanical check (the game system resolving the action)
3. Call `record_interaction(mode=InteractionMode.ACTION, ...)` with the text
4. Attach check results as supplemental data (model TBD — lightweight FK or JSON)

The Interaction model doesn't need to change for this — `mode=ACTION` is already defined.
The supplemental data model for check results is a future addition when the first
action-type interaction is built.

## message_location() Cleanup

After this refactor, `message_location()` becomes:

```python
def message_location(caller, text, target=None, mapping=None, location_state=None):
    """Broadcast text in the caller's location. Pure real-time delivery."""
    # Resolve location and mapping
    # Parse text with funcparser
    # location.msg_contents(text, from_obj=caller.obj, mapping=resolved_mapping)
    # That's it. No database writes.
```

All the SceneParticipation/Persona/Guise/SceneMessage creation code is removed. The
function is ~15 lines instead of ~50.

## Open Questions

1. **Where does CharacterIdentity live?** Options: `world/character_sheets/` (alongside
   CharacterSheet), or a new `world/identity/` app. Recommendation: `character_sheets`
   since it's the same conceptual domain (character data) and avoids a new app for one
   model.

2. **NPC identity:** Do NPCs get CharacterIdentity? Probably not for MVP — NPCs don't
   need guise switching or knowledge tracking. They can get a simpler treatment later.
   `resolve_audience()` skips characters without CharacterIdentity.

3. **Default persona auto-creation timing:** When a guise is created, should the default
   persona be auto-created immediately? Yes — the `Guise.save()` method should ensure
   a default persona exists. This guarantees `active_persona` always has something valid
   to point to.

4. **SceneParticipation still needed?** Yes — it tracks who joined a scene, GM/owner roles,
   join/leave times. Separate from identity. Persona's nullable `participation` FK still
   links a persona to a scene participation when relevant.
