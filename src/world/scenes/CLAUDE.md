# Scenes System - Roleplay Session Recording & Identity

Captures and manages roleplay sessions with participant tracking, interaction recording, story integration, and the unified Persona identity system.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary, privacy_mode
- **`SceneParticipation`**: Account participation tracking in scenes
- **`Persona`**: Unified identity model with PersonaType (PRIMARY/ESTABLISHED/TEMPORARY). Links to CharacterIdentity (character_sheets app) and denormalized character FK
- **`PersonaDiscovery`**: Records that a character discovered two personas are the same person
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

## Key Classes

- **`Scene`**: Contains participants and interactions
- **`SceneParticipation`**: Tracks account involvement in scenes
- **`Persona`**: Unified identity with `persona_type` field (PRIMARY/ESTABLISHED/TEMPORARY). Has `character_identity` FK to CharacterIdentity and denormalized `character` FK. `is_established_or_primary` property for permission checks
- **`PersonaDiscovery`**: Stores raw discovery pairs; service functions handle resolution logic
- **`Interaction`**: Universal building block of RP recording with privacy tiers
