# Stories System

Structured narrative campaign management: trust-based participation, task-gated episode progression, and per-character story arcs.

**Source:** `src/world/stories/`
**API Base:** `/api/stories/`, `/api/chapters/`, `/api/episodes/`, `/api/episode-scenes/`, `/api/story-participations/`, `/api/player-trust/`, `/api/story-feedback/`

---

## Enums (constants.py and types.py)

```python
# constants.py — Phase 1 additions
from world.stories.constants import (
    EraStatus,           # UPCOMING, ACTIVE, CONCLUDED
    StoryScope,          # CHARACTER, GROUP, GLOBAL
    BeatPredicateType,   # GM_MARKED, CHARACTER_LEVEL_AT_LEAST
    BeatOutcome,         # UNSATISFIED, SUCCESS, FAILURE, EXPIRED, PENDING_GM_REVIEW
    BeatVisibility,      # HINTED, SECRET, VISIBLE
    TransitionMode,      # AUTO, GM_CHOICE
)

# types.py — pre-Phase-1 (unchanged)
from world.stories.types import (
    StoryStatus,         # ACTIVE, INACTIVE, COMPLETED, CANCELLED
    StoryPrivacy,        # PUBLIC, PRIVATE, INVITE_ONLY
    ParticipationLevel,  # CRITICAL, IMPORTANT, OPTIONAL
    TrustLevel,          # UNTRUSTED (0), BASIC (1), INTERMEDIATE (2), ADVANCED (3), EXPERT (4)
    ConnectionType,      # THEREFORE, BUT
)
```

---

## Hierarchy

```
Era  (temporal tag — not a hierarchy parent)

Story (CHARACTER / GROUP / GLOBAL scope)
  -> Chapter (Major Arc)
    -> Episode (node in the episode DAG)

Episode <-- Transition --> Episode   (directed edges; may be null target = authoring frontier)
Episode <-- Beat                     (predicates attached to an episode)
Episode <-- EpisodeProgressionRequirement  (gates all outbound transitions)
Transition <-- TransitionRequiredOutcome   (gates this specific transition)
```

---

## Phase 1 Models — Episode Engine

### Era

| Field | Type | Notes |
|-------|------|-------|
| `name` | SlugField | Unique slug |
| `display_name` | CharField | Human-readable |
| `season_number` | PositiveIntegerField | Player-facing "Season N" |
| `description` | TextField | |
| `status` | TextChoices (EraStatus) | UPCOMING / ACTIVE / CONCLUDED |
| `activated_at` | DateTimeField | Nullable |
| `concluded_at` | DateTimeField | Nullable |

Partial unique constraint: at most one Era may be ACTIVE at a time (`only_one_active_era`).

### Story (extended in Phase 1)

Pre-Phase-1 fields unchanged. Phase 1 adds:

| Field | Type | Notes |
|-------|------|-------|
| `scope` | TextChoices (StoryScope) | CHARACTER / GROUP / GLOBAL; default CHARACTER |
| `character_sheet` | FK → character_sheets.CharacterSheet | Nullable; set for CHARACTER-scope stories |
| `created_in_era` | FK → stories.Era | Nullable; null = pre-era or ungrouped |

Existing fields: `title`, `description`, `status`, `privacy`, `owners` (M2M AccountDB), `active_gms` (M2M gm.GMProfile), `primary_table` (FK gm.GMTable), `required_trust_categories` (M2M through StoryTrustRequirement), `is_personal_story`, `personal_story_character` (FK ObjectDB).

### Chapter

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per story |
| `is_active` | BooleanField | |
| `summary`, `consequences` | TextField | Narrative tracking |

### Episode

| Field | Type | Notes |
|-------|------|-------|
| `chapter` | FK → Chapter | |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per chapter |
| `is_active` | BooleanField | |
| `summary`, `consequences` | TextField | Narrative tracking |

`connection_to_next` and `connection_summary` removed in Phase 1 — those semantics live on Transition.

### Transition

First-class directed edge in the episode DAG.

| Field | Type | Notes |
|-------|------|-------|
| `source_episode` | FK → Episode | `related_name="outbound_transitions"` |
| `target_episode` | FK → Episode (nullable) | Null = authoring frontier |
| `mode` | TextChoices (TransitionMode) | AUTO (fires on eligibility) / GM_CHOICE (requires explicit GM pick) |
| `connection_type` | TextChoices (ConnectionType) | THEREFORE / BUT narrative flavor |
| `connection_summary` | TextField | Short narrative description |
| `order` | PositiveIntegerField | Tie-breaker for eligibility ordering |

### EpisodeProgressionRequirement

A beat that must reach `required_outcome` before **any** outbound transition from the episode is eligible (episode-level gate; AND semantics across all rows).

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | |
| `beat` | FK → Beat | |
| `required_outcome` | TextChoices (BeatOutcome) | Default SUCCESS |

### TransitionRequiredOutcome

Per-transition routing predicate. All rows on a given transition must be satisfied (AND). OR semantics expressed by creating multiple transitions.

| Field | Type | Notes |
|-------|------|-------|
| `transition` | FK → Transition | |
| `beat` | FK → Beat | |
| `required_outcome` | TextChoices (BeatOutcome) | |

### Beat

Boolean predicate attached to an episode. Phase 1 implements two concrete predicate types via a flat discriminator column; `clean()` enforces that exactly the right nullable config fields are populated.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | |
| `predicate_type` | TextChoices (BeatPredicateType) | GM_MARKED / CHARACTER_LEVEL_AT_LEAST |
| `outcome` | TextChoices (BeatOutcome) | Current state; history in BeatCompletion |
| `visibility` | TextChoices (BeatVisibility) | HINTED (default) / SECRET / VISIBLE |
| `internal_description` | TextField | Author/staff view |
| `player_hint` | TextField | Shown while active (if HINTED or VISIBLE) |
| `player_resolution_text` | TextField | Shown in story log after completion |
| `required_level` | PositiveIntegerField (nullable) | For CHARACTER_LEVEL_AT_LEAST predicate |
| `deadline` | DateTimeField (nullable) | Scaffolded; expiry handling in Phase 3+ |
| `order` | PositiveIntegerField | |

### BeatCompletion

Append-only audit ledger. One row per beat outcome event applied to a character.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | |
| `character_sheet` | FK → character_sheets.CharacterSheet | |
| `roster_entry` | FK → roster.RosterEntry (nullable) | Which player tenure was active |
| `outcome` | TextChoices (BeatOutcome) | |
| `era` | FK → Era (nullable) | Active era at time of completion |
| `gm_notes` | TextField | |
| `recorded_at` | DateTimeField (auto_now_add) | |

### EpisodeResolution

Append-only audit ledger. One row per episode resolved for a character.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | |
| `character_sheet` | FK → character_sheets.CharacterSheet | |
| `chosen_transition` | FK → Transition (nullable) | Null = frontier pause |
| `resolved_by` | FK → gm.GMProfile (nullable) | |
| `era` | FK → Era (nullable) | |
| `gm_notes` | TextField | |
| `resolved_at` | DateTimeField (auto_now_add) | |

### StoryProgress

Per-character pointer into a CHARACTER-scope story's DAG.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | |
| `character_sheet` | FK → character_sheets.CharacterSheet | |
| `current_episode` | FK → Episode (nullable) | Null = frontier or not started |
| `is_active` | BooleanField | |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | Updated on each `resolve_episode` call |

Unique constraint: one StoryProgress per (story, character_sheet).

---

## Pre-Phase-1 Models — Trust System & Participation

These models are orthogonal to the episode engine and unchanged.

### Trust System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrustCategory` | Dynamic trust categories | `name`, `display_name`, `description`, `is_active`, `created_by` (FK AccountDB) |
| `PlayerTrust` | Aggregate trust profile (1:1 per account) | `account` (OneToOne AccountDB), `gm_trust_level`, `trust_categories` (M2M through PlayerTrustLevel) |
| `PlayerTrustLevel` | Per-category trust level | `player_trust` (FK), `trust_category` (FK), `trust_level`, `positive_feedback_count`, `negative_feedback_count` |
| `StoryTrustRequirement` | Trust required to join a story | `story` (FK), `trust_category` (FK), `minimum_trust_level`, `created_by` (FK AccountDB) |

### Participation & Feedback

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `StoryParticipation` | Character participation in a story | `story` (FK), `character` (FK ObjectDB), `participation_level`, `trusted_by_owner`, `is_active` |
| `StoryFeedback` | Post-story feedback for trust building | `story` (FK), `reviewer` (FK AccountDB), `reviewed_player` (FK AccountDB), `is_gm_feedback`, `comments` |
| `TrustCategoryFeedbackRating` | Per-category rating within feedback | `feedback` (FK), `trust_category` (FK), `rating` (-2 to +2) |

---

## Service Functions

All services are in `src/world/stories/services/`.

```python
from world.stories.services.beats import evaluate_auto_beats, record_gm_marked_outcome
from world.stories.services.transitions import get_eligible_transitions
from world.stories.services.episodes import resolve_episode
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `evaluate_auto_beats` | `(progress: StoryProgress) -> None` | Re-evaluates all non-GM_MARKED beats in the current episode; flips UNSATISFIED beats whose predicate is now met and writes BeatCompletion rows |
| `record_gm_marked_outcome` | `(*, progress: StoryProgress, beat: Beat, outcome: BeatOutcome, gm_notes: str = "") -> BeatCompletion` | GM manually resolves a GM_MARKED beat with SUCCESS or FAILURE; raises BeatNotResolvableError if beat is wrong type or outcome is invalid |
| `get_eligible_transitions` | `(progress: StoryProgress) -> list[Transition]` | Returns outbound transitions eligible to fire: all EpisodeProgressionRequirements met AND each transition's TransitionRequiredOutcomes met; returns [] if any gate is unmet |
| `resolve_episode` | `(*, progress: StoryProgress, chosen_transition: Transition \| None = None, gm_notes: str = "", resolved_by: GMProfile \| None = None) -> EpisodeResolution` | Selects or validates a transition, creates EpisodeResolution, advances StoryProgress.current_episode; raises NoEligibleTransitionError or AmbiguousTransitionError on bad state |

---

## Exceptions

```python
from world.stories.exceptions import (
    StoryError,                       # Base; has user_message property
    BeatNotResolvableError,           # Wrong predicate type or invalid outcome for GM resolution
    NoEligibleTransitionError,        # No transitions eligible, or chosen_transition not in eligible set
    AmbiguousTransitionError,         # Multiple eligible or GM_CHOICE mode with no explicit pick
    ProgressionRequirementNotMetError, # Episode-level gate not satisfied (raised defensively)
)
```

All exceptions expose a safe `user_message` string suitable for API responses. Never pass `str(exc)` to response bodies — use `exc.user_message`.

---

## Integration Points

- **CharacterSheet** — CHARACTER-scope `StoryProgress` and `BeatCompletion` FK to CharacterSheet; `CharacterSheet` owns the character identity
- **CharacterClassLevel** (classes app) — `CHARACTER_LEVEL_AT_LEAST` predicate queries CharacterClassLevel for the character's current level
- **GMProfile** (gm app) — `EpisodeResolution.resolved_by`; `Story.active_gms` M2M; `Story.primary_table` FK to GMTable
- **RosterEntry** (roster app) — `BeatCompletion.roster_entry` captures which tenure (player) was active at resolution time; audit only
- **Era** — `BeatCompletion.era` and `EpisodeResolution.era` stamp the active metaplot era at resolution time; `Story.created_in_era` for grouping
- **Scenes** — `EpisodeScene` links scenes to episodes (unchanged from pre-Phase-1)
- **Trust system** — `StoryParticipation` and trust models are orthogonal; their APIs and logic are unchanged

---

## Admin

- `EraAdmin` — season number, status, activation timestamps; enforces at-most-one-active constraint via DB
- `StoryAdmin` — full editing with horizontal filter for owners/active_gms; scope + character_sheet fields
- `ChapterAdmin` — inline episodes
- `EpisodeAdmin` — inline episode-scenes
- `BeatAdmin` — predicate_type filter; outcome coloring; required_level display conditional on type
- `TransitionAdmin` — source/target episode; mode + connection_type display
- `StoryProgressAdmin` — per-character episode pointer; is_active filter
- `TrustCategoryAdmin`, `PlayerTrustLevelAdmin`, `StoryTrustRequirementAdmin`, `StoryFeedbackAdmin` — unchanged from pre-Phase-1

---

## Key Methods (pre-Phase-1, unchanged)

```python
# Story
story.is_active()                              # True if ACTIVE status + has active GMs
story.can_player_apply(account)                # Privacy + trust requirement check
story.get_trust_requirements_summary()         # [{"category": ..., "minimum_level": ...}, ...]

# PlayerTrust
trust_profile.get_trust_level_for_category(trust_category)
trust_profile.get_trust_level_for_category_name("antagonism")
trust_profile.has_minimum_trust_for_categories([...])
trust_profile.total_positive_feedback          # sum across all categories
trust_profile.total_negative_feedback

# StoryFeedback
feedback.get_average_rating()                  # float
feedback.is_overall_positive()                 # True if average > 0
```
