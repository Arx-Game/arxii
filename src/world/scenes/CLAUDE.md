# Scenes System - Roleplay Session Recording & Identity

Captures and manages roleplay sessions with participant tracking, message logging, story integration, and the unified Persona identity system.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary, privacy_mode
- **`SceneParticipation`**: Account participation tracking in scenes
- **`Persona`**: Unified identity model with PersonaType (PRIMARY/ESTABLISHED/TEMPORARY). Links to CharacterIdentity (character_sheets app) and denormalized character FK
- **`PersonaDiscovery`**: Records that a character discovered two personas are the same person
- **`Interaction`**: Atomic IC interaction record (pose, say, whisper, etc.) with privacy controls
- **`InteractionAudience`**: Tracks who could see an interaction at creation time
- **`InteractionFavorite`**: Private bookmarks for cherished RP moments
- **`InteractionTargetPersona`**: Explicit IC targets for thread derivation
- **`SceneMessage`**: Legacy message model (to be replaced by Interaction)
- **`SceneMessageReaction`**: Character reactions to specific messages
- **`SceneSummaryRevision`**: Collaborative summary editing for ephemeral scenes

### `views.py`
- **`SceneViewSet`**: Scene CRUD operations and filtering
- **`SceneMessageViewSet`**: Message management within scenes
- **`SceneParticipationViewSet`**: Participant management
- **`InteractionViewSet`**: Interaction read + delete + mark_private
- **`InteractionFavoriteViewSet`**: Toggle favorites

### `serializers.py`
- Scene and message serialization for API responses
- Participant and persona data serialization

### `filters.py`
- Scene filtering by status (Active/Paused/Finished)
- Search by participants, location, story integration

### `permissions.py`
- Participation-based access control
- Trust level requirements for scene observation
- Privacy controls for disguised participation

## Key Classes

- **`Scene`**: Links to episodes, contains participants and messages
- **`SceneParticipation`**: Tracks account involvement in scenes
- **`Persona`**: Unified identity with `persona_type` field (PRIMARY/ESTABLISHED/TEMPORARY). Has `character_identity` FK to CharacterIdentity and denormalized `character` FK. `is_established_or_primary` property for permission checks
- **`PersonaDiscovery`**: Stores raw discovery pairs; service functions handle resolution logic
- **`Interaction`**: Universal building block of RP recording with privacy tiers
- **`SceneMessage`**: Legacy scene communication (being replaced by Interaction)
