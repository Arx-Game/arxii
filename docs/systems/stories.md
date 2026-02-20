# Stories System

Player-driven narrative campaign management with hierarchical storytelling and trust-based participation.

**Source:** `src/world/stories/`
**API Base:** `/api/stories/`, `/api/chapters/`, `/api/episodes/`, `/api/episode-scenes/`, `/api/story-participations/`, `/api/player-trust/`, `/api/story-feedback/`

---

## Enums (types.py)

```python
from world.stories.types import (
    StoryStatus,         # ACTIVE, INACTIVE, COMPLETED, CANCELLED
    StoryPrivacy,        # PUBLIC, PRIVATE, INVITE_ONLY
    ParticipationLevel,  # CRITICAL, IMPORTANT, OPTIONAL
    TrustLevel,          # UNTRUSTED (0), BASIC (1), INTERMEDIATE (2), ADVANCED (3), EXPERT (4)
    ConnectionType,      # THEREFORE, BUT
)

# Typed data structures
from world.stories.types import (
    SceneConnection,   # Dataclass: from_scene_id, to_scene_id, connection_type, summary
    EpisodeSummary,    # Dataclass: episode_id, summary, consequences, next_episode_setup
)
```

---

## Models

### Hierarchical Structure

```
Story (Campaign)
  -> Chapter (Major Arc)
    -> Episode (Individual Session)
      -> EpisodeScene (Link to Scene recording)
```

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Story` | Top-level campaign container | `title`, `description`, `status`, `privacy`, `owners` (M2M AccountDB), `active_gms` (M2M ObjectDB, GMCharacter only), `is_personal_story`, `personal_story_character` (FK ObjectDB) |
| `Chapter` | Major narrative arc within a story | `story` (FK), `title`, `description`, `order`, `is_active`, `summary`, `consequences` |
| `Episode` | Individual session within a chapter | `chapter` (FK), `title`, `description`, `order`, `is_active`, `summary`, `consequences`, `connection_to_next`, `connection_summary` |
| `EpisodeScene` | Links scenes to episodes | `episode` (FK), `scene` (FK scenes.Scene), `order`, `connection_to_next`, `connection_summary` |

### Trust System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrustCategory` | Dynamic trust categories (SharedMemoryModel) | `name`, `display_name`, `description`, `is_active`, `created_by` (FK AccountDB) |
| `PlayerTrust` | Aggregate trust profile for a player (1:1) | `account` (OneToOne AccountDB), `gm_trust_level` (IntegerChoices), `trust_categories` (M2M through PlayerTrustLevel) |
| `PlayerTrustLevel` | Per-category trust level for a player | `player_trust` (FK), `trust_category` (FK), `trust_level` (IntegerChoices), `positive_feedback_count`, `negative_feedback_count`, `notes` |
| `StoryTrustRequirement` | Trust required to join a story | `story` (FK), `trust_category` (FK), `minimum_trust_level` (IntegerChoices), `created_by` (FK AccountDB), `notes` |

### Participation & Feedback

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `StoryParticipation` | Character participation in a story | `story` (FK), `character` (FK ObjectDB), `participation_level`, `trusted_by_owner`, `is_active` |
| `StoryFeedback` | Post-story feedback for trust building | `story` (FK), `reviewer` (FK AccountDB), `reviewed_player` (FK AccountDB), `is_gm_feedback`, `comments` |
| `TrustCategoryFeedbackRating` | Per-category rating within feedback | `feedback` (FK), `trust_category` (FK), `rating` (-2 to +2), `notes` |

---

## Key Methods

### Story

```python
from world.stories.models import Story

# Check if story is active (has active GMs and ACTIVE status)
story.is_active()

# Check if a player can apply to participate
story.can_player_apply(account)  # Checks privacy + trust requirements

# Get trust requirements summary for display
story.get_trust_requirements_summary()
# Returns: [{"category": "Antagonistic Roleplay", "minimum_level": "Basic"}, ...]
```

### PlayerTrust

```python
from world.stories.models import PlayerTrust

# Get trust level for a specific category
trust_profile = account.trust_profile
level = trust_profile.get_trust_level_for_category(trust_category)

# Get trust level by category name string
level = trust_profile.get_trust_level_for_category_name("antagonism")

# Check if player meets multiple trust requirements
trust_profile.has_minimum_trust_for_categories([
    {"category": "antagonism", "minimum_level": TrustLevel.BASIC},
    {"category": "mature_themes", "minimum_level": TrustLevel.INTERMEDIATE},
])

# Aggregate feedback counts
trust_profile.total_positive_feedback  # Sum across all categories
trust_profile.total_negative_feedback
```

### StoryFeedback

```python
from world.stories.models import StoryFeedback

# Get average rating across all trust categories
feedback.get_average_rating()  # Returns float

# Check if feedback is overall positive
feedback.is_overall_positive()  # True if average > 0
```

---

## API Endpoints

### Stories (`/api/stories/`)
- `GET /api/stories/` - List stories (filtered by privacy/trust)
- `POST /api/stories/` - Create story (auto-adds creator as owner)
- `GET /api/stories/{id}/` - Story detail
- `PUT/PATCH /api/stories/{id}/` - Update story (owner/staff)
- `POST /api/stories/{id}/apply_to_participate/` - Apply with character_id
- `GET /api/stories/{id}/participants/` - List active participants
- `GET /api/stories/{id}/chapters/` - List chapters ordered by order

**Search:** `title`, `description`
**Ordering:** `created_at`, `updated_at`, `title`, `status`

### Chapters (`/api/chapters/`)
- `GET /api/chapters/` - List chapters
- `POST /api/chapters/` - Create chapter
- `GET /api/chapters/{id}/` - Chapter detail
- `GET /api/chapters/{id}/episodes/` - List episodes ordered by order

**Search:** `title`, `description`, `summary`

### Episodes (`/api/episodes/`)
- `GET /api/episodes/` - List episodes
- `POST /api/episodes/` - Create episode
- `GET /api/episodes/{id}/` - Episode detail
- `GET /api/episodes/{id}/scenes/` - List linked scenes ordered by order

**Search:** `title`, `description`, `summary`

### Episode-Scenes (`/api/episode-scenes/`)
- Full CRUD for linking scenes to episodes

### Story Participations (`/api/story-participations/`)
- Full CRUD for managing participation records

### Player Trust (`/api/player-trust/`)
- `GET /api/player-trust/` - List trust profiles (staff or story owners of participants)
- `GET /api/player-trust/my_trust/` - Get current user's trust profile

### Story Feedback (`/api/story-feedback/`)
- `GET /api/story-feedback/` - List feedback
- `POST /api/story-feedback/` - Create feedback (auto-sets reviewer to current user)
- `GET /api/story-feedback/my_feedback/` - Feedback received by current user
- `GET /api/story-feedback/feedback_given/` - Feedback given by current user

---

## Permissions

| Permission Class | Used For | Rule |
|-----------------|----------|------|
| `IsStoryOwnerOrStaff` | Story CRUD | Read: public visible to authenticated users, private/invite-only restricted; Write: owner only |
| `IsChapterStoryOwnerOrStaff` | Chapter CRUD | Delegates to parent story's owner check |
| `IsEpisodeStoryOwnerOrStaff` | Episode/EpisodeScene CRUD | Delegates through chapter to story owner check |
| `IsParticipationOwnerOrStoryOwnerOrStaff` | Participation management | Character owner can read own; story owner can manage all |
| `IsPlayerTrustOwnerOrStaff` | Trust profiles | Users read own; story owners read participants'; staff modify |
| `IsReviewerOrStoryOwnerOrStaff` | Feedback | Reviewer manages own; reviewed player reads; story owner reads |
| `IsGMOrStaff` | GM-only operations | Checks for active GMCharacter typeclass |
| `CanParticipateInStory` | Story application | Delegates to `story.can_player_apply()` for trust checks |

---

## Integration Points

- **Scenes System**: `EpisodeScene` links episodes to `scenes.Scene`, allowing scenes to update multiple stories
- **Connection Tracking**: Episodes and scenes use `ConnectionType` (THEREFORE/BUT) for narrative flow documentation

---

## Admin

- `StoryAdmin` - Full editing with horizontal filter for owners/active_gms; displays active GM and participant counts
- `ChapterAdmin` - Inline episodes; searchable by story title
- `EpisodeAdmin` - Inline episode-scenes; color-coded connection type display
- `TrustCategoryAdmin` - Manage dynamic trust categories
- `PlayerTrustLevelAdmin` - Color-coded trust levels with feedback summary (+N/-N)
- `StoryTrustRequirementAdmin` - Color-coded minimum trust level display
- `StoryFeedbackAdmin` - Inline category ratings; color-coded average rating display
