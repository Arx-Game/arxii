# Stories System - Narrative Campaign Management

Structured narrative campaign management with hierarchical storytelling and trust-based participation system.

## Key Files

### `models/`
- **`stories.py`**: `Story`, `Chapter`, `Episode` - hierarchical story structure
- **`participation.py`**: `StoryParticipation` - character involvement tracking
- **`trust.py`**: `PlayerTrust`, `TrustCategory` - trust system foundation

### `views.py`
- **`StoryViewSet`**: Story CRUD operations and management
- **`ChapterViewSet`**: Chapter management within stories
- **`EpisodeViewSet`**: Episode management and scheduling
- **`TrustViewSet`**: Trust level administration

### `serializers.py`
- Story hierarchy serialization for API responses
- Trust level and participation data serialization

### `permissions.py`
- Trust-based story access control
- GM permissions for story management
- Visibility controls for public/private stories

### `filters.py`
- Filter stories by status, trust requirements, participation
- Search by GM, participants, story content
- Date-based filtering for archival

## Key Classes

- **`Story`**: Top-level campaign container with trust-based access
- **`Chapter`**: Major narrative arcs within stories  
- **`Episode`**: Individual sessions linking to scene recordings
- **`StoryParticipation`**: Character involvement with role management
- **`PlayerTrust`**: Trust levels across different categories (GM, approval, moderation)

## Hierarchical Structure

```
Story (Campaign)
└── Chapter (Major Arc)
    └── Episode (Individual Session)
        └── Scene (Roleplay Recording)
```
