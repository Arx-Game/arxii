# Scenes System - Roleplay Session Recording & Identity

Captures and manages roleplay sessions with participant tracking, interaction recording, story integration, and the unified Persona identity system.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary, privacy_mode
- **`SceneParticipation`**: Account participation tracking in scenes
- **`Persona`**: Unified identity model with PersonaType (PRIMARY/ESTABLISHED/TEMPORARY). FK to CharacterSheet (source of truth); partial unique constraint ensures one PRIMARY per sheet
- **`PersonaDiscovery`**: Records that a character discovered two personas are the same person
- **`Block`** (#1278): one player blocking another, persona-scoped by default (`blocker_persona` ↔ `blocked_persona`) with an `account_level` opt-in; keyed on `PlayerData` so it follows the person across re-rosters. Resolution + lifecycle in `block_services.py` (`coded_block_active`, `sheet_blocked_for_viewer`, `hidden_persona_ids_for_viewer`, `lift_block`, `finalize_expired_blocks`). Wired into the profile gate (404), the scene target picker, and feed visibility. Supersedes the removed `evennia_extensions.PlayerBlockList`. Remaining: the awareness/"Character Has You Blocked" surface + the cron job.
- **`Mute`** (#1278): the lighter, **one-way** sibling of Block — a player filters a persona out of their own view (IC and/or OOC), reversible, no enforcement, the muted party never aware. `mute_services.py` (`muted_persona_ids_for_viewer`, `set_mute`, `unmute`); the IC side is wired into the scene feed (muted personas skipped). The OOC channel, the "actions still show without text" refinement, the opt-in reveal, and the toggle UI are follow-ups.
- **`BlockContactFlag`** (#1278): the anti-derivation awareness layer. When a *blocked* player reaches the blocker via another identity (circumvention the coded block can't prevent without leaking the alt), `block_services.flag_blocked_contact_attempt` records it for staff (anchored on accounts + personas; zero signal to either player). Hooked into `action_services.create_action_request`. Staff triage via admin. Remaining contact vectors (targeted poses/whispers) + the player-facing generic "Character Has You Blocked" warning are follow-ups.
- **`Interaction`**: Atomic IC interaction record (pose, say, whisper, etc.) with privacy controls
- **`InteractionFavorite`**: Private bookmarks for cherished RP moments
- **`InteractionReaction`**: Emoji reactions on interactions
- **`InteractionTargetPersona`**: Explicit IC targets for thread derivation
- **`SceneSummaryRevision`**: Collaborative summary editing for ephemeral scenes

### `views.py`
- **`SceneViewSet`**: Scene CRUD operations and filtering
- **`PersonaViewSet`**: Persona management
- **`SceneSummaryRevisionViewSet`**: Summary revision management

### `interaction_views.py`
- **`InteractionViewSet`**: Interaction read + delete + mark_private
- **`InteractionFavoriteViewSet`**: Toggle favorites
- **`InteractionReactionViewSet`**: Toggle reactions

### `serializers.py`
- Scene and persona serialization for API responses
- Participant data serialization

### `filters.py`
- Scene filtering by status (Active/Paused/Finished)
- Persona filtering by scene, character, type
- Search by participants, location

### `permissions.py`
- Participation-based access control
- Privacy controls for disguised participation

### `place_services.py`
- **`ensure_scene_for_location(room, *, name, privacy_mode)`**: get-or-create the room's active scene; privacy auto-derived from room publicness when omitted (PUBLIC if publicly listed, else PRIVATE). Thin wrapper over `ensure_scene_for_location_created`, which returns `(scene, created)`.
- **`start_or_join_scene(room, *, owner_account, name, privacy_mode)`**: frictionless scene start (#1309). Get-or-creates the active scene; records `owner_account` as `SceneParticipation(is_owner=True)` ONLY when this call created the scene (a later actor just joins, no owner change). Idempotent.

### `interaction_services.py`
- **`maybe_finish_empty_scene(room, *, leaving=None)`**: auto-close (#1309). Finishes the room's active scene when no scene-participating character remains present (walks `room.contents`, excluding `leaving`, which may still be in contents at the `at_object_leave` hook). Called from `Room.at_object_leave`. Implicit scene start on a pose lives in `record_interaction`'s no-active-scene branch.

## Key Classes

- **`Scene`**: Contains participants and interactions
- **`SceneParticipation`**: Tracks account involvement in scenes
- **`Persona`**: Unified identity with `persona_type` field (PRIMARY/ESTABLISHED/TEMPORARY). Has `character_sheet` FK to CharacterSheet (the source-of-truth anchor). `is_established_or_primary` property for permission checks. Hosts `display_ic` / `display_with_history` / `display_to_staff` helpers
- **`PersonaDiscovery`**: Stores raw discovery pairs; service functions handle resolution logic
- **`Interaction`**: Universal building block of RP recording with privacy tiers
