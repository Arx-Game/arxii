# Scenes System - Roleplay Session Recording

Captures and manages roleplay sessions with participant tracking, message logging, and story integration.

## Key Files

### `models.py`
- **`Scene`**: Primary scene entity with title, status, location, summary
- **`SceneParticipation`**: Character participation tracking with persona support
- **`Persona`**: Identity management including disguises and alternate appearances
- **`SceneMessage`**: Dialogue, actions, and system messages within scenes
- **`SceneMessageReaction`**: Character reactions to specific messages

### `views.py`
- **`SceneViewSet`**: Scene CRUD operations and filtering
- **`SceneMessageViewSet`**: Message management within scenes
- **`SceneParticipationViewSet`**: Participant management

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
- **`SceneParticipation`**: Tracks character involvement with persona system
- **`Persona`**: Manages character identities and disguises
- **`SceneMessage`**: Stores all scene communication with type classification
