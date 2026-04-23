# Stories System

Structured narrative campaign management: task-gated episode progression, multi-scope (CHARACTER / GROUP / GLOBAL) story arcs, and a full GM workflow (scheduling, AGM delegation, session requests).

**Phase 2 complete.** All backend models, services, and API endpoints are implemented. Phase 3 is the React frontend.

**Source:** `src/world/stories/`
**API Base:** `/api/stories/`, `/api/chapters/`, `/api/episodes/`, `/api/beats/`, `/api/transitions/`, `/api/story-progress/`, `/api/group-story-progress/`, `/api/global-story-progress/`, `/api/aggregate-beat-contributions/`, `/api/assistant-gm-claims/`, `/api/session-requests/`

---

## Enums

```python
# constants.py
from world.stories.constants import (
    EraStatus,              # UPCOMING, ACTIVE, CONCLUDED
    StoryScope,             # CHARACTER, GROUP, GLOBAL
    BeatPredicateType,      # GM_MARKED, CHARACTER_LEVEL_AT_LEAST, ACHIEVEMENT_HELD,
                            # CONDITION_HELD, CODEX_ENTRY_UNLOCKED, STORY_AT_MILESTONE,
                            # AGGREGATE_THRESHOLD
    StoryMilestoneType,     # STORY_RESOLVED, CHAPTER_REACHED, EPISODE_REACHED
    BeatOutcome,            # UNSATISFIED, SUCCESS, FAILURE, EXPIRED, PENDING_GM_REVIEW
    BeatVisibility,         # HINTED, SECRET, VISIBLE
    TransitionMode,         # AUTO, GM_CHOICE
    AssistantClaimStatus,   # REQUESTED, APPROVED, REJECTED, CANCELLED, COMPLETED
    SessionRequestStatus,   # OPEN, SCHEDULED, RESOLVED, CANCELLED
)

# types.py — pre-Phase-1 (unchanged)
from world.stories.types import (
    StoryStatus,            # ACTIVE, INACTIVE, COMPLETED, CANCELLED
    StoryPrivacy,           # PUBLIC, PRIVATE, INVITE_ONLY
    ParticipationLevel,     # CRITICAL, IMPORTANT, OPTIONAL
    TrustLevel,             # UNTRUSTED (0) .. EXPERT (4)
    ConnectionType,         # THEREFORE, BUT
    AnyStoryProgress,       # StoryProgress | GroupStoryProgress | GlobalStoryProgress
)
```

---

## Hierarchy

```
Era  (temporal tag — not a hierarchy parent)

Story (CHARACTER / GROUP / GLOBAL scope)
  -> Chapter (major arc)
    -> Episode (node in the episode DAG)

Episode <-- Transition --> Episode                 (directed edges; nullable target = authoring frontier)
Episode <-- Beat                                   (predicates attached to an episode)
Episode <-- EpisodeProgressionRequirement          (gates all outbound transitions from this episode)
Transition <-- TransitionRequiredOutcome           (gates this specific transition)
```

---

## Models

### Era

Temporal metaplot tag. One ACTIVE era enforced by partial unique constraint.

| Field | Type | Notes |
|-------|------|-------|
| `name` | SlugField (unique) | |
| `display_name` | CharField | Human-readable |
| `season_number` | PositiveIntegerField | Player-facing "Season N" |
| `description` | TextField | |
| `status` | EraStatus | UPCOMING / ACTIVE / CONCLUDED |
| `activated_at` | DateTimeField (nullable) | |
| `concluded_at` | DateTimeField (nullable) | |

`Era.objects.get_active()` — returns the single ACTIVE era or None.

---

### Story

Top-level campaign container.

| Field | Type | Notes |
|-------|------|-------|
| `title`, `description` | CharField / TextField | |
| `status` | StoryStatus | ACTIVE, INACTIVE, COMPLETED, CANCELLED |
| `privacy` | StoryPrivacy | PUBLIC, PRIVATE, INVITE_ONLY |
| `scope` | StoryScope | CHARACTER / GROUP / GLOBAL |
| `character_sheet` | FK → character_sheets.CharacterSheet (nullable) | For CHARACTER-scope stories |
| `created_in_era` | FK → stories.Era (nullable) | |
| `owners` | M2M → accounts.AccountDB | |
| `active_gms` | M2M → gm.GMProfile | |
| `primary_table` | FK → gm.GMTable (nullable) | Lead GM's table; used for AGM claim permission check |
| `required_trust_categories` | M2M through StoryTrustRequirement | |

---

### Chapter

Major arc within a story.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="chapters"` |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per story |
| `is_active` | BooleanField | |
| `summary`, `consequences` | TextField | |

---

### Episode

Node in the episode DAG. Transitions are the edges.

| Field | Type | Notes |
|-------|------|-------|
| `chapter` | FK → Chapter | `related_name="episodes"` |
| `title`, `description` | CharField / TextField | |
| `order` | PositiveIntegerField | Unique per chapter |
| `is_active` | BooleanField | |
| `summary`, `consequences` | TextField | |

`episode.outbound_transitions` — reverse from Transition.source_episode.
`episode.beats` — reverse from Beat.episode.
`episode.progression_requirements` — reverse from EpisodeProgressionRequirement.episode.

---

### Transition

First-class directed edge in the episode DAG.

| Field | Type | Notes |
|-------|------|-------|
| `source_episode` | FK → Episode | `related_name="outbound_transitions"` |
| `target_episode` | FK → Episode (nullable) | Null = authoring frontier |
| `mode` | TransitionMode | AUTO fires automatically; GM_CHOICE requires explicit pick |
| `connection_type` | ConnectionType | THEREFORE / BUT narrative flavor |
| `connection_summary` | TextField | Short narrative description |
| `order` | PositiveIntegerField | Tie-breaker for eligibility ordering |

`transition.required_outcomes` — reverse from TransitionRequiredOutcome.transition.

---

### EpisodeProgressionRequirement

Beat that must reach `required_outcome` before any outbound transition is eligible (AND across all rows per episode).

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="progression_requirements"` |
| `beat` | FK → Beat | |
| `required_outcome` | BeatOutcome | Default SUCCESS |

---

### TransitionRequiredOutcome

Per-transition routing predicate. All rows on a given transition must be satisfied (AND). OR semantics = multiple transitions.

| Field | Type | Notes |
|-------|------|-------|
| `transition` | FK → Transition | `related_name="required_outcomes"` |
| `beat` | FK → Beat | |
| `required_outcome` | BeatOutcome | |

---

### Beat

Boolean predicate attached to an episode. Flat discriminator model — all config fields are nullable; `clean()` enforces exactly the right fields for each predicate type.

**Core fields:**

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="beats"` |
| `predicate_type` | BeatPredicateType | See below for per-type config fields |
| `outcome` | BeatOutcome | Current state; history in BeatCompletion |
| `visibility` | BeatVisibility | HINTED (default) / SECRET / VISIBLE |
| `internal_description` | TextField | Author/staff view |
| `player_hint` | TextField | Shown while active (HINTED or VISIBLE) |
| `player_resolution_text` | TextField | Shown in story log after completion |
| `deadline` | DateTimeField (nullable) | Expiry triggers EXPIRED outcome via `expire_overdue_beats` |
| `agm_eligible` | BooleanField | True = AGM may claim this beat |
| `order` | PositiveIntegerField | |

**Per-predicate config fields (exactly one set should be non-null per predicate type):**

| Predicate type | Required field(s) |
|---------------|------------------|
| `CHARACTER_LEVEL_AT_LEAST` | `required_level` (PositiveIntegerField) |
| `ACHIEVEMENT_HELD` | `required_achievement` FK → achievements.Achievement |
| `CONDITION_HELD` | `required_condition_template` FK → conditions.ConditionTemplate |
| `CODEX_ENTRY_UNLOCKED` | `required_codex_entry` FK → codex.CodexEntry |
| `STORY_AT_MILESTONE` | `referenced_story` FK → Story, `referenced_milestone_type` (StoryMilestoneType), `referenced_chapter` FK → Chapter (nullable), `referenced_episode` FK → Episode (nullable) |
| `AGGREGATE_THRESHOLD` | `required_points` PositiveIntegerField |
| `GM_MARKED` | (no config fields) |

**Scope behaviour for auto-evaluation (`evaluate_auto_beats`):**
- CHARACTER scope: all predicate types evaluated against `progress.character_sheet`.
- GROUP / GLOBAL scope: predicates that require a CharacterSheet (ACHIEVEMENT_HELD, CONDITION_HELD, CODEX_ENTRY_UNLOCKED, CHARACTER_LEVEL_AT_LEAST) are skipped — the GM must mark these manually. STORY_AT_MILESTONE is evaluated without a sheet.
- AGGREGATE_THRESHOLD is write-path triggered (via `record_aggregate_contribution`), not evaluated by `evaluate_auto_beats`.

---

### AggregateBeatContribution

Per-character contribution ledger for AGGREGATE_THRESHOLD beats.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="aggregate_contributions"` |
| `character_sheet` | FK → CharacterSheet | Who contributed |
| `roster_entry` | FK → RosterEntry (nullable) | Audit: which tenure was active |
| `points` | PositiveIntegerField | |
| `era` | FK → Era (nullable) | Active era at time of contribution |
| `source_note` | TextField | What produced this contribution |
| `recorded_at` | DateTimeField (auto_now_add) | |

`AggregateBeatContribution.objects.total_for_beat(beat)` → int sum.

---

### AssistantGMClaim

AGM claim lifecycle on an `agm_eligible` beat.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="agm_claims"` |
| `assistant_gm` | FK → gm.GMProfile | The claiming AGM |
| `status` | AssistantClaimStatus | REQUESTED → APPROVED/REJECTED/CANCELLED → COMPLETED |
| `approved_by` | FK → gm.GMProfile (nullable) | Lead GM who approved/rejected |
| `rejection_note` | TextField | |
| `framing_note` | TextField | Scene framing authored by Lead GM |
| `created_at` | DateTimeField (auto_now_add) | |
| `updated_at` | DateTimeField (auto_now) | |

Partial unique constraint: no duplicate active claims per (beat, assistant_gm) where status is REQUESTED or APPROVED.

---

### SessionRequest

Scheduling request for an episode that requires GM involvement.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="session_requests"` |
| `status` | SessionRequestStatus | OPEN → SCHEDULED → RESOLVED (or CANCELLED) |
| `event` | FK → events.Event (nullable) | Set when SCHEDULED |
| `open_to_any_gm` | BooleanField | If True, any GM may claim |
| `assigned_gm` | FK → gm.GMProfile (nullable) | Specifically assigned GM |
| `initiated_by_account` | FK → accounts.AccountDB (nullable) | Who requested the session |
| `notes` | TextField | |
| `created_at` | DateTimeField (auto_now_add) | |
| `updated_at` | DateTimeField (auto_now) | |

---

### BeatCompletion

Append-only audit ledger. One row per beat outcome event. Scope-aware: exactly one of `character_sheet` / `gm_table` / neither is populated.

| Field | Type | Notes |
|-------|------|-------|
| `beat` | FK → Beat | `related_name="completions"` |
| `character_sheet` | FK → CharacterSheet (nullable) | CHARACTER scope |
| `gm_table` | FK → gm.GMTable (nullable) | GROUP scope |
| `roster_entry` | FK → roster.RosterEntry (nullable) | Audit: active tenure at time of completion |
| `outcome` | BeatOutcome | |
| `era` | FK → Era (nullable) | Active era at completion |
| `gm_notes` | TextField | |
| `recorded_at` | DateTimeField (auto_now_add) | |

`clean()` enforces scope consistency: CHARACTER → `character_sheet` required; GROUP → `gm_table` required; GLOBAL → both null.

---

### EpisodeResolution

Append-only audit ledger. One row per episode resolved. Scope-aware.

| Field | Type | Notes |
|-------|------|-------|
| `episode` | FK → Episode | `related_name="resolutions"` |
| `character_sheet` | FK → CharacterSheet (nullable) | CHARACTER scope |
| `gm_table` | FK → gm.GMTable (nullable) | GROUP scope |
| `chosen_transition` | FK → Transition (nullable) | Null = frontier pause |
| `resolved_by` | FK → gm.GMProfile (nullable) | |
| `era` | FK → Era (nullable) | |
| `gm_notes` | TextField | |
| `resolved_at` | DateTimeField (auto_now_add) | |

---

### StoryProgress

Per-character pointer into a CHARACTER-scope story's episode DAG.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="progress_records"` |
| `character_sheet` | FK → CharacterSheet | Must equal `story.character_sheet` (clean() enforced) |
| `current_episode` | FK → Episode (nullable) | Null = not started or frontier |
| `is_active` | BooleanField | |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | Updated on each advance |

Unique per (story, character_sheet).

---

### GroupStoryProgress

Per-GMTable pointer into a GROUP-scope story's episode DAG. The whole table shares one trail.

| Field | Type | Notes |
|-------|------|-------|
| `story` | FK → Story | `related_name="group_progress_records"` |
| `gm_table` | FK → gm.GMTable | |
| `current_episode` | FK → Episode (nullable) | |
| `is_active` | BooleanField | |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | |

Unique per (story, gm_table).

---

### GlobalStoryProgress

Singleton pointer per GLOBAL-scope story.

| Field | Type | Notes |
|-------|------|-------|
| `story` | OneToOneField → Story | `related_name="global_progress"` |
| `current_episode` | FK → Episode (nullable) | |
| `is_active` | BooleanField | |
| `started_at` | DateTimeField (auto_now_add) | |
| `last_advanced_at` | DateTimeField (auto_now) | |

---

## Service Functions

All services in `src/world/stories/services/`.

### beats.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `evaluate_auto_beats` | `(progress: AnyStoryProgress) -> None` | Re-evaluates all non-GM_MARKED beats; flips UNSATISFIED beats whose predicate is now met; writes BeatCompletion rows; calls `maybe_create_session_request` on exit |
| `record_gm_marked_outcome` | `(*, progress, beat, outcome, gm_notes="") -> BeatCompletion` | GM manually resolves a GM_MARKED beat; raises `BeatNotResolvableError` if wrong type or invalid outcome |
| `record_aggregate_contribution` | `(*, beat, character_sheet, points, source_note="") -> AggregateBeatContribution` | Records contribution, re-evaluates beat atomically, flips to SUCCESS if threshold crossed |
| `expire_overdue_beats` | `(now=None) -> int` | Idempotent bulk sweep; flips UNSATISFIED past-deadline beats to EXPIRED; returns count |

### transitions.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_eligible_transitions` | `(progress: AnyStoryProgress) -> list[Transition]` | Returns eligible outbound transitions; lazily expires overdue beats; raises `ProgressionRequirementNotMetError` if any gate is unmet |

### episodes.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `resolve_episode` | `(*, progress, chosen_transition=None, gm_notes="", resolved_by=None) -> EpisodeResolution` | Selects/validates transition, creates EpisodeResolution, advances progress; raises `NoEligibleTransitionError` or `AmbiguousTransitionError` on bad state |

### progress.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_active_progress_for_story` | `(story: Story) -> AnyStoryProgress \| None` | Dispatches on scope: CHARACTER → first active StoryProgress; GROUP → first active GroupStoryProgress; GLOBAL → global_progress OneToOne accessor |
| `advance_progress_to_episode` | `(progress, target_episode) -> None` | Updates `current_episode` and auto-stamps `last_advanced_at` |

### assistant_gm.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `request_claim` | `(*, beat, assistant_gm, framing_note="") -> AssistantGMClaim` | AGM requests claim; raises `BeatNotAGMEligibleError` if beat not flagged |
| `approve_claim` | `(*, claim, approver, framing_note=None) -> AssistantGMClaim` | Lead GM approves; raises `ClaimStateTransitionError` / `ClaimApprovalPermissionError` |
| `reject_claim` | `(*, claim, approver, note="") -> AssistantGMClaim` | Lead GM rejects |
| `cancel_claim` | `(*, claim) -> AssistantGMClaim` | AGM cancels own claim (REQUESTED only) |
| `complete_claim` | `(*, claim, completer) -> AssistantGMClaim` | Lead GM marks APPROVED claim COMPLETED |

### scheduling.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `maybe_create_session_request` | `(progress: AnyStoryProgress) -> SessionRequest \| None` | Idempotent; creates OPEN SessionRequest when episode has eligible transitions AND GM involvement is needed |
| `create_event_from_session_request` | `(*, session_request, name, scheduled_real_time, host_persona, location_id, description="", is_public=True) -> Event` | Bridges OPEN SessionRequest to Events system; transitions to SCHEDULED |
| `cancel_session_request` | `(*, session_request) -> SessionRequest` | OPEN → CANCELLED |
| `resolve_session_request` | `(*, session_request) -> SessionRequest` | SCHEDULED → RESOLVED |

### story_log.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `serialize_story_log` | `(story, requester_role) -> list[dict]` | Builds ordered chapter/episode/beat log with role-gated visibility |

### dashboards.py

| Function | Signature | Description |
|----------|-----------|-------------|
| `compute_story_status_line` | `(progress: AnyStoryProgress) -> str` | Returns a human-readable one-liner for the player dashboard |

---

## Exceptions

```python
from world.stories.exceptions import (
    StoryError,                         # Base; has user_message property
    BeatNotResolvableError,             # Wrong predicate type or invalid outcome
    NoEligibleTransitionError,          # No eligible transitions; or chosen_transition not valid
    AmbiguousTransitionError,           # Multiple eligible; or GM_CHOICE without explicit pick
    ProgressionRequirementNotMetError,  # Episode-level gate not satisfied
    BeatNotAGMEligibleError,            # beat.agm_eligible is False
    ClaimStateTransitionError,          # Claim not in expected state for transition
    ClaimApprovalPermissionError,       # Approver is not Lead GM or staff
    SessionRequestNotOpenError,         # Session request not in expected state
)
```

Never pass `str(exc)` to API responses — use `exc.user_message`.

---

## API Endpoints

### Dashboard / Custom Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/api/stories/{pk}/log/` | Participant or staff | Story log with visibility filtering |
| GET | `/api/stories/my-active/` | Authenticated | Player's active CHARACTER-scope stories |
| GET | `/api/stories/gm-queue/` | GMProfile required | Lead GM's episodes-ready-to-run dashboard |
| GET | `/api/stories/staff-workload/` | Staff | All active stories across all tables |
| POST | `/api/stories/{pk}/resolve-episode/` | Story owner or staff | Fire `resolve_episode`; body: `{chosen_transition?}` |
| POST | `/api/stories/expire-beats/` | Staff | Trigger `expire_overdue_beats` |

### Beat Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/beats/{pk}/mark/` | Story owner (GM) | `record_gm_marked_outcome`; body: `{outcome, gm_notes?}` |
| POST | `/api/beats/{pk}/contribute/` | Story participant | `record_aggregate_contribution`; body: `{points, source_note?}` |

### AGM Claim Lifecycle

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/assistant-gm-claims/{pk}/approve/` | Lead GM or staff | `approve_claim` |
| POST | `/api/assistant-gm-claims/{pk}/reject/` | Lead GM or staff | `reject_claim` |
| POST | `/api/assistant-gm-claims/{pk}/complete/` | Lead GM or staff | `complete_claim` |

### Session Request Actions

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| POST | `/api/session-requests/{pk}/create-event/` | Story owner | Bridge to events system |

### Standard ViewSet CRUD

All ViewSets support standard REST verbs (GET list/detail, POST create, PATCH/PUT update, DELETE) subject to permission class rules.

| ViewSet | Base URL | Writable by |
|---------|----------|-------------|
| StoryViewSet | `/api/stories/` | Story owners, staff |
| ChapterViewSet | `/api/chapters/` | Story owners, staff |
| EpisodeViewSet | `/api/episodes/` | Story owners, staff |
| BeatViewSet | `/api/beats/` | Story owners, staff |
| TransitionViewSet | `/api/transitions/` | Story owners, staff |
| StoryProgressViewSet | `/api/story-progress/` | Story owners, staff |
| GroupStoryProgressViewSet | `/api/group-story-progress/` | Lead GM of table, staff |
| GlobalStoryProgressViewSet | `/api/global-story-progress/` | Staff only |
| AggregateBeatContributionViewSet | `/api/aggregate-beat-contributions/` | Read-only |
| AssistantGMClaimViewSet | `/api/assistant-gm-claims/` | Read-only (AGM creates via custom action) |
| SessionRequestViewSet | `/api/session-requests/` | Read-only |

---

## Cross-App Integration

| System | Integration point |
|--------|------------------|
| **character_sheets** | `StoryProgress.character_sheet`, `BeatCompletion.character_sheet`; `CharacterSheet.cached_achievements_held` and `cached_active_condition_templates` for beat evaluation; `CharacterSheet.current_level` for `CHARACTER_LEVEL_AT_LEAST` |
| **achievements** | `Beat.required_achievement` FK; `CharacterAchievement` queried for `ACHIEVEMENT_HELD` evaluation; `sheet.invalidate_achievement_cache()` must be called after granting achievements |
| **conditions** | `Beat.required_condition_template` FK; `ConditionInstance` queried for `CONDITION_HELD` evaluation; `sheet.invalidate_condition_cache()` must be called after applying conditions |
| **codex** | `Beat.required_codex_entry` FK; `CharacterCodexKnowledge.status == KNOWN` per RosterEntry for `CODEX_ENTRY_UNLOCKED` evaluation |
| **gm** | `GMProfile` for `resolved_by`, `assigned_gm`, AGM claim actors; `GMTable` for GROUP scope progress and primary_table permission check; `GMTableMembership` for queryset filtering |
| **roster** | `RosterEntry` used in `BeatCompletion.roster_entry` and `AggregateBeatContribution.roster_entry` for audit trail |
| **events** | `SessionRequest.event` FK; `create_event_from_session_request` calls `events.services.create_event` |
| **scenes** | `EpisodeScene` links scenes to episodes; `Persona` used as `host_persona` for session event creation |
| **classes** | `CharacterClassLevel` queried for `CHARACTER_LEVEL_AT_LEAST` evaluation |
| **Era** | `BeatCompletion.era`, `EpisodeResolution.era`, `AggregateBeatContribution.era` — stamped with active era at event time; `Story.created_in_era` for grouping |

---

## Pre-Phase-1 Models (unchanged)

### Trust System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrustCategory` | Dynamic trust categories | `name`, `display_name`, `description`, `is_active` |
| `PlayerTrust` | Aggregate trust profile | `account` (OneToOne AccountDB), `gm_trust_level` |
| `PlayerTrustLevel` | Per-category trust level | `player_trust`, `trust_category`, `trust_level`, feedback counts |
| `StoryTrustRequirement` | Trust gate for story join | `story`, `trust_category`, `minimum_trust_level` |

### Participation & Feedback

| Model | Purpose |
|-------|---------|
| `StoryParticipation` | Character involvement in a story |
| `StoryFeedback` | Post-story trust-building feedback |
| `TrustCategoryFeedbackRating` | Per-category rating within feedback |
| `EpisodeScene` | Links scenes to episodes |
