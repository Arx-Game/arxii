# Stories System Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the stories-system backend: add GROUP and GLOBAL scope progress models, all reasonable beat predicate types, deadline expiry, Assistant GM claim workflow, SessionRequest integration with Events, full API surface (ViewSets + dashboards + action endpoints), and legacy Story field cleanup. No frontend in this phase.

**Architecture:** Extend the Phase 1 backend. Reuse the existing flat-Beat discriminator pattern for new predicate types (nullable config fields + `clean()` invariant). Each scope gets its own progress model (not a single polymorphic table). API uses DRF ViewSets with filter classes and permission classes following existing project conventions. Story log visibility filtering lives in serializers, reading request.user's role vs. the story's scope.

**Tech Stack:** Django 4.x, DRF, PostgreSQL, SharedMemoryModel, FactoryBoy, django-filter, Evennia test runner (`arx test`).

**Design Reference:** `docs/plans/2026-04-20-stories-system-design.md`
**Phase 1 Plan (for pattern reference):** `docs/plans/2026-04-20-stories-system-phase1-implementation.md`

---

## Phase Scope

**In Phase 2 (this plan):**

### Model/service extensions
- **GROUP scope** — `GroupStoryProgress(story, gm_table, current_episode)` model + service. One row per GROUP-scope story.
- **GLOBAL scope** — `GlobalStoryProgress(story, current_episode)` model + service. Singleton per GLOBAL-scope story.
- **Additional beat predicate types:**
  - `ACHIEVEMENT_HELD` — references `achievements.Achievement`
  - `CONDITION_HELD` — references `conditions.ConditionTemplate` (checks for active `ConditionInstance`)
  - `CODEX_ENTRY_UNLOCKED` — references `codex.CodexEntry` (per-character discovery)
  - `STORY_AT_MILESTONE` — cross-story; references another Story, with a milestone discriminator (reached specific chapter / reached specific episode / story resolved)
  - `AGGREGATE_THRESHOLD` — references nothing external; tracks contribution via new `AggregateBeatContribution` ledger
- **`AggregateBeatContribution` ledger** — per character (and roster_entry audit), per beat, points contributed, era, timestamp.
- **Deadline expiry** — service that flips `outcome=EXPIRED` on any beat whose `deadline` has passed. Lazy (called on episode eligibility check) + cron-ready (idempotent; safe to call repeatedly).
- **Assistant GM claim flow** — new `AssistantGMClaim` model + service for beat-scoped claims. Lead GM or Staff approves.
- **`SessionRequest` model + Events integration** — when an episode becomes ready-to-run (AUTO or GM_CHOICE transition eligible AND target is GM-run), a SessionRequest is created. Lead GM / player (depending on scope) uses it to book an Event via the existing Events system. SessionRequest FKs Episode + optionally Event (set when scheduled).
- **Progress auto-creation hooks:**
  - CG finalization creates CHARACTER StoryProgress when it creates a CHARACTER-scope Story.
  - Covenant/group creation hook creates GroupStoryProgress when a GROUP-scope Story is assigned to a GMTable. (If covenant creation path doesn't exist yet, document as hook point.)
  - GLOBAL Stories get a singleton GlobalStoryProgress on first access or at creation — whichever is simpler.
- **Legacy Story field cleanup:**
  - Drop `Story.is_personal_story` (replaced by `scope == CHARACTER`)
  - Drop `Story.personal_story_character` (replaced by `character_sheet`; original was an ObjectDB FK anti-pattern)
  - Migration removes the columns.
- **`ProgressionRequirementNotMetError` wiring** — `get_eligible_transitions` raises this instead of returning `[]` when progression requirements are unmet. View layer surfaces the distinction between "progression unmet" and "frontier pause."

### API surface
- **ViewSets** — one per model (Story, Chapter, Episode, Transition, Beat, EpisodeProgressionRequirement, TransitionRequiredOutcome, BeatCompletion, EpisodeResolution, StoryProgress, GroupStoryProgress, GlobalStoryProgress, AggregateBeatContribution, AssistantGMClaim, SessionRequest). Read-only for players; CRUD for Lead GMs/staff subject to permission classes.
- **Visibility-filtered story log serializer** — HINTED/SECRET/VISIBLE rules applied per beat at serialization time based on requester role (player vs. Lead GM vs. staff).
- **Player dashboard endpoint** — `/api/stories/my-active/` returning all active stories across all scopes that the requester participates in, with status one-liners.
- **Lead GM dashboard endpoint** — `/api/stories/gm-queue/` returning episodes ready to run across stories the requester is Lead GM on, plus AGM-flagged beats awaiting claim/approval.
- **Staff workload dashboard endpoint** — `/api/stories/staff-workload/` aggregating per-GM queue depth, stories stale for N days, stories at frontier, etc.
- **Action endpoints** (custom actions on ViewSets):
  - `POST /api/episodes/{id}/resolve/` — calls `resolve_episode` service
  - `POST /api/beats/{id}/mark/` — GM marks a GM_MARKED beat outcome
  - `POST /api/beats/{id}/contribute/` — records an aggregate contribution
  - `POST /api/assistant-claims/` — AGM requests a claim
  - `POST /api/assistant-claims/{id}/approve/` — Lead GM / staff approves
  - `POST /api/assistant-claims/{id}/reject/` — Lead GM / staff rejects
  - `POST /api/session-requests/{id}/create-event/` — caller turns a SessionRequest into an actual Event
  - `POST /api/stories/expire-overdue-beats/` — staff-only trigger for deadline sweep (or just internal service)

### Docs
- Update `docs/systems/stories.md` + `docs/roadmap/stories-gm.md`.
- Regenerate `docs/systems/MODEL_MAP.md`.

**Deferred to Phase 3+:**
- React frontend
- `MISSION_COMPLETE` predicate (missions system not built)
- Authoring UX polish beyond Django admin + basic CRUD endpoints
- Covenant leadership model (PC leader / group vote / assigned GM) — outside stories scope

---

## Existing State Audit

- **Phase 1 is live** (commit `30263485` on main, PR #397). All Phase 1 models + services in `src/world/stories/`.
- **GMTable lives in `src/world/gm/models.py`** at line 114. `GMProfile` at line 15, `GMTableMembership` at 141, `GMRosterInvite` at 204. GROUP progress will FK `GMTable`.
- **Events system** — `Event`, `EventHost`, `EventInvitation`, `EventModification` in `src/world/events/models.py`. `src/world/events/services.py` exists. SessionRequest can reference Events but should live in stories.
- **Achievement** — `src/world/achievements/models.py` line 88.
- **ConditionTemplate** + **ConditionInstance** — `src/world/conditions/models.py` lines 141 and 799.
- **CodexEntry** — `src/world/codex/models.py` line 163. Investigate per-character discovery model (likely something like `CharacterCodexEntry` or similar).
- **CovenantRole** exists in `src/world/covenants/models.py` but the Covenant app is skeletal — do NOT make GROUP scope depend on covenants. Use GMTable.

---

## Conventions for this plan

Same as Phase 1 — don't re-explain, just follow:
- SharedMemoryModel for all concrete models
- Absolute imports only
- `world.stories` is in the typed apps list — full type annotations
- `Prefetch(..., to_attr=...)` against a `cached_property`
- No JSON fields, TextChoices in `constants.py`
- `git -C <abs-path>`, never `gh` CLI, never `cd &&`
- `arx test <app> --keepdb` for inner loop; fresh-DB run before commit
- Pre-commit hooks run on commit — fix and re-stage; never `--no-verify`
- Typed exceptions with `user_message` for API-facing errors
- Service functions take model instances or pks, never slugs
- Permissions in permission classes, not inline checks in views
- Validation in serializers' `validate()` / `validate_<field>()`, not in views
- FilterSets for all list endpoints — never `request.query_params`
- Factories with `django_get_or_create` for lookup-style fixtures; SubFactory for relational

---

## Execution structure

The plan is organized into **waves**. Each wave is a cohesive group of tasks that make sense to land together. Order between waves matters (later waves depend on earlier). Within a wave, tasks are independent unless noted.

- **Wave 1** — Foundations (constants, exception wiring, legacy cleanup, CG hook)
- **Wave 2** — GROUP + GLOBAL scope progress models
- **Wave 3** — New beat predicate types
- **Wave 4** — Aggregate contribution ledger
- **Wave 5** — Deadline expiry
- **Wave 6** — Assistant GM claim flow
- **Wave 7** — SessionRequest + Events integration
- **Wave 8** — API ViewSets (base CRUD)
- **Wave 9** — Story log visibility-filtered serializer
- **Wave 10** — Dashboard endpoints (player / GM / staff)
- **Wave 11** — Action endpoints
- **Wave 12** — Integration test + docs

Each wave's task block is below.

---

## Wave 1 — Foundations

### Task 1.1: Add new constants and enum values

**Files:**
- Modify: `src/world/stories/constants.py`

Add these new `TextChoices` members to `BeatPredicateType`:
```python
ACHIEVEMENT_HELD = "achievement_held", "Achievement held"
CONDITION_HELD = "condition_held", "Condition held"
CODEX_ENTRY_UNLOCKED = "codex_entry_unlocked", "Codex entry unlocked"
STORY_AT_MILESTONE = "story_at_milestone", "Referenced story at milestone"
AGGREGATE_THRESHOLD = "aggregate_threshold", "Aggregate threshold reached"
```

Add a new `TextChoices` for `StoryMilestoneType`:
```python
class StoryMilestoneType(models.TextChoices):
    """Which kind of milestone a STORY_AT_MILESTONE beat checks against."""
    STORY_RESOLVED = "story_resolved", "Story resolved"
    CHAPTER_REACHED = "chapter_reached", "Chapter reached or passed"
    EPISODE_REACHED = "episode_reached", "Episode reached or passed"
```

Add `AssistantClaimStatus`:
```python
class AssistantClaimStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
```

Add `SessionRequestStatus`:
```python
class SessionRequestStatus(models.TextChoices):
    OPEN = "open", "Open — awaiting scheduling"
    SCHEDULED = "scheduled", "Scheduled (Event created)"
    RESOLVED = "resolved", "Resolved (session complete)"
    CANCELLED = "cancelled", "Cancelled"
```

Commit: `feat(stories): add Phase 2 constants (new predicate types, claim & session-request statuses, milestone types)`

---

### Task 1.2: Wire `ProgressionRequirementNotMetError` into `get_eligible_transitions`

**Files:**
- Modify: `src/world/stories/services/transitions.py`
- Modify: `src/world/stories/tests/test_services_transitions.py`

**Change:** when progression requirements are unmet, raise `ProgressionRequirementNotMetError` instead of returning `[]`. Current behavior returns `[]` for both "progression not met" and "no transitions authored (frontier)" — the view layer needs to distinguish these.

**Update callers:** `resolve_episode` catches `ProgressionRequirementNotMetError` and re-raises it (or lets it propagate — `resolve_episode` already raises typed exceptions). Check `src/world/stories/services/episodes.py` for the interaction.

**Tests:** add `test_get_eligible_transitions_raises_when_progression_unmet` and update existing tests that expected `[]` from progression-unmet state to expect the exception instead. Keep the "frontier pause (no progression requirements at all; no transitions authored)" test — that should still return `[]`.

Commit: `feat(stories): raise ProgressionRequirementNotMetError for unmet progression gates`

---

### Task 1.3: Auto-create StoryProgress during CG finalization

**Files:**
- Modify: `src/world/character_creation/services.py` (the `finalize_gm_character` around line 1261 area)
- Modify: relevant test module

After `Story.objects.create(...)` in `finalize_gm_character`, also create the matching `StoryProgress`:
```python
StoryProgress.objects.create(
    story=story,
    character_sheet=sheet,
    current_episode=None,  # starts at pre-story / frontier; no episode yet
)
```

Add a test asserting that a freshly-created CG story has exactly one `StoryProgress` row for the character. This is the first time we're testing the CG → StoryProgress path.

Commit: `feat(stories): auto-create StoryProgress during CG finalization`

---

### Task 1.4: Drop legacy `Story.is_personal_story` and `Story.personal_story_character`

**Files:**
- Modify: `src/world/stories/models.py` (Story class)
- Modify: `src/world/stories/admin.py` (StoryAdmin if it references these)
- Modify: `src/world/stories/serializers.py` if any serializer references them
- Modify: `src/world/stories/filters.py` if any filter uses them
- Grep and remove any usages across the codebase (`grep -rn "is_personal_story\|personal_story_character" src/`)
- Migration auto-generated by `makemigrations`

Both fields are superseded by `scope` (CHARACTER/GROUP/GLOBAL) and `character_sheet` (the properly-typed FK). `personal_story_character` was an `ObjectDB` FK anti-pattern. Per CLAUDE.md: "No Backwards Compatibility in Dev — Accept only the current format."

Run full regression across `world.stories world.character_creation world.gm world.roster world.societies` to catch any remaining reference.

Commit: `refactor(stories): drop legacy is_personal_story and personal_story_character fields`

---

## Wave 2 — GROUP + GLOBAL scope progress models

### Task 2.1: `GroupStoryProgress` model + factory + admin + tests

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_group_story_progress.py`

**Model shape (follow StoryProgress pattern from Phase 1):**
```python
class GroupStoryProgress(SharedMemoryModel):
    """Per-group pointer into a GROUP-scope story's current state.

    One row per story; the whole GMTable shares the progress trail. Members
    never diverge onto separate branches — the group resolves episodes as
    a unit.
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="group_progress_records")
    gm_table = models.ForeignKey("gm.GMTable", on_delete=models.CASCADE, related_name="story_progress")
    current_episode = models.ForeignKey(Episode, null=True, blank=True, on_delete=models.SET_NULL, related_name="active_group_progress_records")
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["story", "gm_table"], name="unique_group_progress_per_story_per_table"),
        ]
        indexes = [models.Index(fields=["gm_table", "is_active"])]

    def clean(self) -> None:
        super().clean()
        if self.story.scope != StoryScope.GROUP:
            raise ValidationError({"story": "GroupStoryProgress requires a GROUP-scope story."})

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)
```

**Factory:** `GroupStoryProgressFactory` with SubFactory on story (scope=GROUP) and gm_table (import GMTableFactory).

**Tests:**
- Creation + round-trip
- Unique constraint (`TransactionTestCase`)
- `clean()` rejects CHARACTER/GLOBAL scope stories
- Frontier case (`current_episode=None`)

Commit: `feat(stories): add GroupStoryProgress model for GROUP-scope stories`

---

### Task 2.2: `GlobalStoryProgress` model + factory + admin + tests

**Files:** same locations as 2.1.

**Model shape:**
```python
class GlobalStoryProgress(SharedMemoryModel):
    """Singleton pointer into a GLOBAL-scope story's current state.

    One row per story; the whole server shares the progression trail.
    GLOBAL stories opt-in/out by character (via StoryParticipation), but
    the story itself progresses as a single shared thread.
    """

    story = models.OneToOneField(Story, on_delete=models.CASCADE, related_name="global_progress")
    current_episode = models.ForeignKey(Episode, null=True, blank=True, on_delete=models.SET_NULL, related_name="active_global_progress_records")
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def clean(self) -> None:
        super().clean()
        if self.story.scope != StoryScope.GLOBAL:
            raise ValidationError({"story": "GlobalStoryProgress requires a GLOBAL-scope story."})

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)
```

The `OneToOneField` enforces the singleton-per-story invariant at the DB level — no unique constraint needed.

**Factory + tests** mirror `GroupStoryProgress`.

Commit: `feat(stories): add GlobalStoryProgress model for GLOBAL-scope metaplot stories`

---

### Task 2.3: Generalize progress-lookup helpers in services

**Files:**
- Create: `src/world/stories/services/progress.py` (new module for scope-aware helpers)
- Modify: `src/world/stories/services/episodes.py` (use the new helpers)

Add scope-aware helpers:
```python
def get_active_progress_for_story(story: Story):
    """Return the progress record for a story, dispatching on scope.

    Returns: StoryProgress | GroupStoryProgress | GlobalStoryProgress | None
    depending on whether one exists.
    """
    if story.scope == StoryScope.CHARACTER:
        return story.progress_records.filter(is_active=True).first()
    if story.scope == StoryScope.GROUP:
        return story.group_progress_records.filter(is_active=True).first()
    if story.scope == StoryScope.GLOBAL:
        return getattr(story, "global_progress", None)
    return None


def advance_progress_to_episode(progress, target_episode):
    """Update current_episode on whichever progress type is passed.

    All three progress models have the same shape (current_episode,
    last_advanced_at via auto_now); this is just a scope-polymorphic wrapper.
    """
    progress.current_episode = target_episode
    progress.save(update_fields=["current_episode", "last_advanced_at"])
```

`resolve_episode` currently types its `progress` param as `StoryProgress`. Widen to `StoryProgress | GroupStoryProgress | GlobalStoryProgress` via a type alias in `types.py`:
```python
# src/world/stories/types.py
AnyStoryProgress = StoryProgress | GroupStoryProgress | GlobalStoryProgress
```

Update services and tests accordingly.

Commit: `feat(stories): scope-aware progress helpers; widen resolve_episode to all scope progress types`

---

## Wave 3 — New beat predicate types

For each new predicate type below, follow the Phase 1 pattern: add nullable config FK(s) to `Beat`, add an entry to `_REQUIRED_CONFIG`, add an evaluator case in `services/beats.py::_evaluate_predicate`, add tests.

### Task 3.1: `ACHIEVEMENT_HELD` predicate type

**Files:**
- Modify: `src/world/stories/models.py` (Beat — add `required_achievement` FK)
- Modify: `src/world/stories/services/beats.py` (evaluator case)
- Modify: `src/world/stories/tests/test_beat.py` (clean invariant tests)
- Modify: `src/world/stories/tests/test_services_beats.py` (evaluator tests)

**Model addition:**
```python
required_achievement = models.ForeignKey(
    "achievements.Achievement",
    null=True,
    blank=True,
    on_delete=models.CASCADE,  # If achievement deleted, beat is broken — cascade to remove.
    related_name="+",
    help_text="For ACHIEVEMENT_HELD predicates.",
)
```

Add to `_REQUIRED_CONFIG`:
```python
BeatPredicateType.ACHIEVEMENT_HELD: ("required_achievement",),
```
And add `required_achievement` to `all_config_fields` in the `clean()` method.

**Evaluator** (`_evaluate_predicate`): investigate `world.achievements` for the proper way to check "does this character hold this achievement?" Likely something like `Achievement.objects.filter(characters=sheet.character).exists()` or via a per-character ledger. Use a cached_property on CharacterSheet (`cached_achievements_held`) following the same pattern established in Phase 1 for `current_level`. Add a helper in the achievements app if one doesn't exist (scope-creep is fine per user).

**Tests:**
- `clean()` rejects config when predicate is ACHIEVEMENT_HELD with no achievement, or GM_MARKED with an achievement set
- Evaluator: SUCCESS when character holds the achievement, UNSATISFIED otherwise

Commit: `feat(stories): add ACHIEVEMENT_HELD beat predicate type`

---

### Task 3.2: `CONDITION_HELD` predicate type

**Files:** same shape as 3.1.

**Model addition:**
```python
required_condition_template = models.ForeignKey(
    "conditions.ConditionTemplate",
    null=True,
    blank=True,
    on_delete=models.CASCADE,
    related_name="+",
    help_text="For CONDITION_HELD predicates.",
)
```

**Evaluator:** check whether the character has an active `ConditionInstance` whose template matches `required_condition_template`. Investigate `world.conditions.ConditionInstance` to find the proper FK from condition instances to character/sheet.

Add a cached_property on CharacterSheet if one doesn't already exist (`cached_active_conditions`). Follow the Phase 1 caching pattern.

Tests same shape.

Commit: `feat(stories): add CONDITION_HELD beat predicate type`

---

### Task 3.3: `CODEX_ENTRY_UNLOCKED` predicate type

**Files:** same shape.

**Investigation first:** `world.codex` has `CodexEntry`. Need to find the per-character discovery model (likely `CharacterCodexEntry`, `CodexDiscovery`, or similar). If none exists, note it and ask — codex-per-character may be modeled differently than expected.

**Model addition:**
```python
required_codex_entry = models.ForeignKey(
    "codex.CodexEntry",
    null=True,
    blank=True,
    on_delete=models.CASCADE,
    related_name="+",
    help_text="For CODEX_ENTRY_UNLOCKED predicates.",
)
```

Evaluator: SUCCESS if the character has discovered/unlocked the entry (via the codex discovery model).

Tests same shape.

Commit: `feat(stories): add CODEX_ENTRY_UNLOCKED beat predicate type`

---

### Task 3.4: `STORY_AT_MILESTONE` predicate type (cross-story reference)

**Files:** same shape.

**Model addition (multiple nullable fields — milestone discriminator drives which is populated):**
```python
referenced_story = models.ForeignKey(
    "stories.Story",
    null=True,
    blank=True,
    on_delete=models.CASCADE,
    related_name="referenced_by_beats",
    help_text="For STORY_AT_MILESTONE predicates.",
)
referenced_milestone_type = models.CharField(
    max_length=30,
    choices=StoryMilestoneType.choices,
    blank=True,
    default="",
    help_text="Which kind of milestone to check on referenced_story.",
)
referenced_chapter = models.ForeignKey(
    "stories.Chapter",
    null=True,
    blank=True,
    on_delete=models.CASCADE,
    related_name="+",
    help_text="For referenced_milestone_type=CHAPTER_REACHED.",
)
referenced_episode = models.ForeignKey(
    "stories.Episode",
    null=True,
    blank=True,
    on_delete=models.CASCADE,
    related_name="+",
    help_text="For referenced_milestone_type=EPISODE_REACHED.",
)
```

Update `_REQUIRED_CONFIG` with a more sophisticated entry — STORY_AT_MILESTONE requires `referenced_story`, `referenced_milestone_type`, AND the matching `referenced_chapter`/`referenced_episode` based on type. Refactor `clean()` if needed to support conditional requirements (may want a `_validate_predicate_config()` helper method on Beat that returns error dict for this case).

**Evaluator:**
- STORY_RESOLVED: check if referenced Story has reached a terminal state (`status=COMPLETED` or similar — investigate existing StoryStatus values)
- CHAPTER_REACHED: check if the active progress for the referenced story's scope has advanced past `referenced_chapter`'s order within its story
- EPISODE_REACHED: same but for episodes

Tests:
- Each milestone type is satisfied when expected
- Invalid config combinations (STORY_RESOLVED with a chapter set, CHAPTER_REACHED without a chapter, etc.) raise ValidationError

Commit: `feat(stories): add STORY_AT_MILESTONE cross-story reference beat predicate`

---

### Task 3.5: `AGGREGATE_THRESHOLD` predicate type (depends on Wave 4)

Skip for now — wave 4 creates the `AggregateBeatContribution` ledger, then this task adds the predicate type that reads it. See Task 4.2.

---

## Wave 4 — Aggregate contribution ledger

### Task 4.1: `AggregateBeatContribution` ledger model

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_aggregate_contribution.py`

**Model:**
```python
class AggregateBeatContribution(SharedMemoryModel):
    """Per-character contribution toward an AGGREGATE_THRESHOLD beat."""

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="aggregate_contributions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="aggregate_contributions",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    points = models.PositiveIntegerField(
        help_text="Contribution points toward the beat's target.",
    )
    era = models.ForeignKey(Era, null=True, blank=True, on_delete=models.SET_NULL, related_name="aggregate_contributions")
    source_note = models.TextField(blank=True, help_text="Brief description of what contributed (siege battle, mission, etc.).")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["beat", "character_sheet"]),
            models.Index(fields=["beat", "-recorded_at"]),
        ]
```

Add a convenience manager method:
```python
class AggregateBeatContributionManager(models.Manager):
    def total_for_beat(self, beat) -> int:
        return self.filter(beat=beat).aggregate(total=models.Sum("points"))["total"] or 0
```

Tests cover: round-trip, per-character totaling, era stamping.

Commit: `feat(stories): add AggregateBeatContribution ledger`

---

### Task 4.2: `AGGREGATE_THRESHOLD` predicate type

**Files:**
- Modify: `src/world/stories/models.py` (Beat — add `required_points` field)
- Modify: `src/world/stories/services/beats.py` (evaluator)
- Tests

**Model addition on Beat:**
```python
required_points = models.PositiveIntegerField(
    null=True,
    blank=True,
    help_text="For AGGREGATE_THRESHOLD predicates — total contribution points required.",
)
```

Update `_REQUIRED_CONFIG`:
```python
BeatPredicateType.AGGREGATE_THRESHOLD: ("required_points",),
```

**Evaluator:**
```python
if beat.predicate_type == BeatPredicateType.AGGREGATE_THRESHOLD:
    total = AggregateBeatContribution.objects.total_for_beat(beat)
    return BeatOutcome.SUCCESS if total >= beat.required_points else BeatOutcome.UNSATISFIED
```

Add a service function to record contributions:
```python
def record_aggregate_contribution(
    *,
    beat: Beat,
    character_sheet: CharacterSheet,
    points: int,
    source_note: str = "",
) -> AggregateBeatContribution:
    """Record a contribution toward an AGGREGATE_THRESHOLD beat."""
    if beat.predicate_type != BeatPredicateType.AGGREGATE_THRESHOLD:
        raise BeatNotResolvableError("Only AGGREGATE_THRESHOLD beats accept contributions.")
    contrib = AggregateBeatContribution.objects.create(
        beat=beat,
        character_sheet=character_sheet,
        roster_entry=_current_roster_entry(character_sheet),
        era=Era.objects.get_active(),
        points=points,
        source_note=source_note,
    )
    # Re-evaluate: if threshold crossed, flip outcome and record BeatCompletion.
    # Reuse the evaluate_auto_beats logic path — but scoped to just this beat.
    # ...
    return contrib
```

Tests cover:
- Record a single contribution below threshold → UNSATISFIED
- Record contributions reaching threshold → SUCCESS + BeatCompletion created
- Rejecting contributions for non-AGGREGATE_THRESHOLD beats

Commit: `feat(stories): add AGGREGATE_THRESHOLD beat predicate type with contribution recording`

---

## Wave 5 — Deadline expiry

### Task 5.1: `expire_overdue_beats` service + tests

**Files:**
- Modify: `src/world/stories/services/beats.py`
- Modify: `src/world/stories/tests/test_services_beats.py`

**Service:**
```python
def expire_overdue_beats(now: datetime | None = None) -> int:
    """Flip outcome to EXPIRED for any UNSATISFIED beat whose deadline has passed.

    Returns count of beats expired. Idempotent — safe to call repeatedly.
    Records a BeatCompletion per expired beat, with outcome=EXPIRED.

    Called lazily at the start of get_eligible_transitions for a specific
    episode's beats, AND available as a bulk sweep service for a cron hook.
    """
    now = now or timezone.now()
    overdue = Beat.objects.filter(
        outcome=BeatOutcome.UNSATISFIED,
        deadline__lt=now,
    )
    count = 0
    with transaction.atomic():
        for beat in overdue:
            beat.outcome = BeatOutcome.EXPIRED
            beat.save(update_fields=["outcome", "updated_at"])
            # Record a BeatCompletion for every progress record that could
            # have been progressing this beat — but for CHARACTER scope,
            # that's the story's sole character. For GROUP/GLOBAL, it's the
            # group/global progress. Strategy: attach a completion per
            # active progress record.
            for progress in _progress_records_for_beat(beat):
                BeatCompletion.objects.create(
                    beat=beat,
                    character_sheet=getattr(progress, "character_sheet", None)
                        or _resolve_character_sheet_from_group_progress(progress),
                    roster_entry=None,  # expiry isn't attributable to a tenure
                    outcome=BeatOutcome.EXPIRED,
                    era=Era.objects.get_active(),
                )
            count += 1
    return count
```

(Adjust once you're in the code — `_progress_records_for_beat` and `_resolve_character_sheet_from_group_progress` are helpers to figure out who was "on" this beat; for GLOBAL scope, character_sheet is nullable on the completion — may need to make it so.)

**Alternative simpler design (if BeatCompletion per-progress feels overly complicated):** just flip the outcome and don't record a completion. EXPIRED outcome is inherently "system-caused." Tests and caller code just need to check `beat.outcome == EXPIRED` to route.

Pick the simpler design if it works — check whether the existing BeatCompletion FK on character_sheet can be nullable for system-caused expirations. If not, keep it simple: no BeatCompletion for expiry.

Tests:
- Beat with deadline in past and no current outcome → flipped to EXPIRED
- Beat with deadline in future → unchanged
- Beat already SUCCESS or FAILURE → unchanged
- Idempotent on repeated calls

Commit: `feat(stories): add expire_overdue_beats service for deadline lifecycle`

---

### Task 5.2: Lazy invocation from `get_eligible_transitions`

**Files:**
- Modify: `src/world/stories/services/transitions.py`

Before evaluating eligibility, sweep any overdue beats tied to the current episode. This catches expiry at read time in case no cron has fired yet:
```python
def get_eligible_transitions(progress) -> list[Transition]:
    if progress.current_episode is None:
        return []
    # Lazy expiry — any beat tied to this episode with a past deadline
    # gets flipped to EXPIRED before we evaluate.
    _expire_overdue_beats_for_episode(progress.current_episode)
    ...
```

Commit: `feat(stories): lazy deadline expiry on eligibility check`

---

## Wave 6 — Assistant GM claim flow

### Task 6.1: `AssistantGMClaim` model

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_assistant_gm_claim.py`

**Model:**
```python
class AssistantGMClaim(SharedMemoryModel):
    """An Assistant GM's claim on a specific beat session.

    Flow: AGM submits (status=REQUESTED) → Lead GM or Staff approves or
    rejects → AGM runs the session → Lead GM marks COMPLETED.
    """

    beat = models.ForeignKey(Beat, on_delete=models.CASCADE, related_name="assistant_claims")
    assistant_gm = models.ForeignKey("gm.GMProfile", on_delete=models.CASCADE, related_name="assistant_claims_made")
    status = models.CharField(max_length=20, choices=AssistantClaimStatus.choices, default=AssistantClaimStatus.REQUESTED)
    approved_by = models.ForeignKey("gm.GMProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="assistant_claims_approved")
    rejection_note = models.TextField(blank=True)
    framing_note = models.TextField(blank=True, help_text="Lead GM's one-paragraph framing for the AGM session.")
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["beat", "assistant_gm"],
                condition=models.Q(status__in=[AssistantClaimStatus.REQUESTED, AssistantClaimStatus.APPROVED]),
                name="unique_active_claim_per_beat_per_agm",
            )
        ]
        indexes = [models.Index(fields=["status", "requested_at"])]
```

Tests cover: creation, unique-active constraint (TransactionTestCase), status transitions via service functions (see next task).

Commit: `feat(stories): add AssistantGMClaim model for beat-scoped AGM claims`

---

### Task 6.2: AssistantGMClaim service + exceptions

**Files:**
- Create: `src/world/stories/services/assistant_gm.py`
- Modify: `src/world/stories/exceptions.py` (add `AssistantClaimError`, `AssistantClaimNotApprovableError`, `BeatNotAGMEligibleError`)
- Create: `src/world/stories/tests/test_services_assistant_gm.py`

Service functions:
```python
def request_claim(*, beat: Beat, assistant_gm: GMProfile) -> AssistantGMClaim:
    """AGM requests to run this beat. Beat must be flagged AGM-eligible."""
    # Validate: beat.predicate_type == GM_MARKED (other predicates don't need AGM)
    # Validate: beat has an "agm_eligible" flag (add to Beat — see model addition below)
    # Create AssistantGMClaim with status=REQUESTED.

def approve_claim(*, claim: AssistantGMClaim, approver: GMProfile) -> AssistantGMClaim:
    """Lead GM or staff approves the claim."""
    # Validate: status == REQUESTED.
    # Validate: approver is Lead GM on the story OR has staff permission.

def reject_claim(*, claim: AssistantGMClaim, approver: GMProfile, note: str = "") -> AssistantGMClaim:
    """Reject the claim."""

def cancel_claim(*, claim: AssistantGMClaim) -> AssistantGMClaim:
    """AGM cancels their own claim before approval."""

def complete_claim(*, claim: AssistantGMClaim) -> AssistantGMClaim:
    """Mark claim COMPLETED after session runs."""
```

**Beat model addition:** add `agm_eligible = models.BooleanField(default=False, help_text="Lead GM may flag this beat to be claimable by Assistant GMs.")` — include in the migration for this task.

Tests cover: each service function, each exception raised in the right circumstance, state transitions.

Commit: `feat(stories): add AssistantGMClaim service with typed exceptions`

---

## Wave 7 — SessionRequest + Events integration

### Task 7.1: `SessionRequest` model

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_session_request.py`

**Model:**
```python
class SessionRequest(SharedMemoryModel):
    """A scheduling request generated when an episode becomes ready-to-run.

    Flow: Episode becomes eligible → SessionRequest(status=OPEN) is created
    → Lead GM / player (per scope) creates an Event via Events system →
    SessionRequest.status = SCHEDULED, event set → session runs → episode
    resolved → SessionRequest.status = RESOLVED.

    For CHARACTER-scope personal stories, the player is the primary actor
    (they can mark "ready to schedule" or "first-available"). For GROUP,
    the Lead GM coordinates. For GLOBAL, staff creates open events.
    """

    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name="session_requests")
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="session_requests")
    status = models.CharField(max_length=20, choices=SessionRequestStatus.choices, default=SessionRequestStatus.OPEN)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="session_requests")
    open_to_any_gm = models.BooleanField(default=False, help_text="Player opted for first-available GM (CHARACTER scope only).")
    assigned_gm = models.ForeignKey("gm.GMProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_session_requests")
    initiated_by_account = models.ForeignKey("accounts.AccountDB", null=True, blank=True, on_delete=models.SET_NULL, related_name="initiated_session_requests")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["story", "status"]),
        ]
```

Tests cover creation, status transitions, Event-linking.

Commit: `feat(stories): add SessionRequest model for episode scheduling`

---

### Task 7.2: Auto-create SessionRequest when an episode becomes ready-to-run

**Files:**
- Modify: `src/world/stories/services/transitions.py` (or a new hook module)
- Modify: `src/world/stories/tests/test_services_transitions.py`

When `get_eligible_transitions` first finds a non-empty eligible set AND the target episode requires GM involvement (has GM_MARKED beats OR is a GM_CHOICE transition), check if a SessionRequest exists for that episode and create one if not.

**Decision to clarify during implementation:** do we create SessionRequest on eligibility check (read path, could be expensive if there are many readers), or on a write-time signal (e.g., when a beat is GM-marked SUCCESS or when `record_aggregate_contribution` crosses a threshold)?

Recommendation: write-time signal. Have `record_gm_marked_outcome` and `record_aggregate_contribution` (and `evaluate_auto_beats`) call a helper `_maybe_create_session_request(progress)` that checks eligibility and opens a SessionRequest if needed. This avoids doing expensive work on every read.

Tests cover: beat completion that makes an episode ready-to-run creates a SessionRequest; subsequent calls don't duplicate.

Commit: `feat(stories): auto-create SessionRequest when episode becomes ready-to-run`

---

### Task 7.3: `create_event_from_session_request` service

**Files:**
- Modify: `src/world/stories/services/episodes.py` (or a new `services/scheduling.py`)
- Modify: `src/world/stories/tests/` (relevant test module)

Service to turn a SessionRequest into an Event:
```python
def create_event_from_session_request(
    *,
    session_request: SessionRequest,
    scheduled_time: datetime,
    location: Room | None = None,  # investigate Events.Event to find what fields it takes
    initiated_by: AccountDB,
) -> Event:
    """Creates an Event tied to this SessionRequest and transitions the
    SessionRequest to SCHEDULED."""
    # Delegate to events.services (if there's a creation helper) or
    # Event.objects.create directly.
    event = ...  # create the Event
    session_request.event = event
    session_request.status = SessionRequestStatus.SCHEDULED
    session_request.save(update_fields=["event", "status", "updated_at"])
    return event
```

Investigate existing `events.services.py` for the proper creation helper. If there isn't a clean service, call `Event.objects.create` with the fields the Event model needs (host, time, room, invitations).

Tests cover: successful creation, SessionRequest status transition, rejection of already-scheduled requests.

Commit: `feat(stories): create_event_from_session_request service bridges stories and events`

---

## Wave 8 — API ViewSets (base CRUD)

> **Note:** Wave 8 is a large batch of similar tasks. The pattern is identical per ViewSet — follow the project conventions (FilterSet, permission classes, serializers in `serializers.py`, ViewSet in `views.py`). Phase 1 already has `StoryViewSet`, `ChapterViewSet`, etc.; this wave ADDS ViewSets for the new models and EXPANDS existing ViewSets with new serializer fields for the new model shape.

### Task 8.1: ViewSets for new progress models

**Files:**
- Modify: `src/world/stories/serializers.py` — add `GroupStoryProgressSerializer`, `GlobalStoryProgressSerializer`
- Modify: `src/world/stories/views.py` — add `GroupStoryProgressViewSet`, `GlobalStoryProgressViewSet`
- Modify: `src/world/stories/filters.py` — filter classes
- Modify: `src/world/stories/permissions.py` — permissions
- Modify: `src/world/stories/urls.py` — register the ViewSets
- Create: appropriate test modules

Read-only for players. Lead GMs on the story can see all. Staff sees all.

Commit: `feat(stories-api): add ViewSets for GroupStoryProgress and GlobalStoryProgress`

---

### Task 8.2: ViewSets for new predicate-related data

**Files:** same shape as 8.1.

Add ViewSets for `AggregateBeatContribution`, `AssistantGMClaim`, `SessionRequest`. Proper permission + filter + serializer layering.

Commit: `feat(stories-api): add ViewSets for aggregate contributions, AGM claims, session requests`

---

### Task 8.3: Expand Beat serializer with new predicate config fields

**Files:** `src/world/stories/serializers.py` — update `BeatSerializer` (or whatever it's called) to include `required_achievement`, `required_condition_template`, `required_codex_entry`, `referenced_story`, `referenced_milestone_type`, `referenced_chapter`, `referenced_episode`, `required_points`, `deadline`, `agm_eligible`. Use nested serializer (light-weight) for FK references where it helps the consumer, or just ID refs.

Add a serializer-level `validate()` that enforces the predicate-type invariants (same check as Beat.clean, but surfaced as 400 errors instead of 500).

Tests cover each predicate type through serializer validation.

Commit: `feat(stories-api): expand Beat serializer with Phase 2 predicate fields`

---

## Wave 9 — Story log visibility-filtered serializer

### Task 9.1: Visibility rules in serializer

**Files:**
- Modify: `src/world/stories/serializers.py` — add `StoryLogSerializer` or similar
- Modify: `src/world/stories/permissions.py` — helper to classify requester role
- Create: `src/world/stories/tests/test_serializers_story_log.py`

The story log is a chronological stream of `BeatCompletion` + `EpisodeResolution` rows for a given story + participant. Apply visibility filtering:
- **Player (not Lead GM, not staff, participates in the story):**
  - See their own `BeatCompletion` entries where beat visibility != SECRET, OR beat visibility == SECRET and the beat has a `player_resolution_text` (show vague text)
  - Hidden entries collapse or are omitted entirely
  - See `EpisodeResolution` entries — the episode title and the Transition's `connection_summary`/`connection_type` (if transition is set)
- **Lead GM:** see everything
- **Staff:** see everything + internal_description of each beat

**Design for extensibility:** a `serialize_story_log(story, *, progress, requester_role)` helper returns a list of typed entries (use a dataclass in `types.py`).

Tests cover:
- Player sees hinted beats' resolution text, secret beats as vague entries
- Lead GM sees all internal descriptions
- Staff sees internal_description even on secret beats

Commit: `feat(stories-api): story log serializer with visibility filtering`

---

## Wave 10 — Dashboard endpoints

### Task 10.1: Player active-stories endpoint

**Files:**
- Modify: `src/world/stories/views.py` — add `MyActiveStoriesView`
- Modify: `src/world/stories/urls.py`
- Create: `src/world/stories/tests/test_views_my_active.py`

Returns all active stories across all scopes the requester participates in:
- CHARACTER scope — their own `StoryProgress` records where is_active=True
- GROUP scope — `GroupStoryProgress` records for every `GMTable` the requester is a member of
- GLOBAL scope — `GlobalStoryProgress` for stories the character has `StoryParticipation` on

Response shape:
```python
{
    "character_stories": [
        {"story_id": ..., "story_title": ..., "status_line": "Ch1 Ep2 — waiting on you", "scope": "character"},
        ...
    ],
    "group_stories": [...],
    "global_stories": [...],
}
```

Status line is computed in the serializer or view:
- "Ch1 Ep3 — ready to schedule" (progression requirements met + eligible transitions)
- "Ch1 Ep2 — waiting on you" (beats still unmet)
- "Ch2 Ep1 — scheduled for ..." (SessionRequest.status=SCHEDULED with linked Event)
- "Ch2 Ep4 — on hold" (current_episode is None and no eligible transitions — frontier)

Tests cover each state produces the right status line.

Commit: `feat(stories-api): player active-stories dashboard`

---

### Task 10.2: Lead GM queue endpoint

**Files:**
- Modify: `src/world/stories/views.py` — add `GMQueueView`
- Tests

Returns:
- Episodes ready to run (progress with eligible transition, target is GM-run) across all stories the requester is Lead GM on
- AGM claims pending approval on those stories
- SessionRequests assigned to this GM (open + scheduled)

Permissions: must have a `GMProfile` — investigate what the "Lead GM" relationship is. Likely via `Story.primary_table` + the GM's `GMTableMembership`. Use a permission class `IsGMOrStaff` or similar (already exists from Phase 1).

Commit: `feat(stories-api): Lead GM queue dashboard`

---

### Task 10.3: Staff workload dashboard endpoint

**Files:**
- Modify: `src/world/stories/views.py` — add `StaffWorkloadView`
- Tests

Staff-only aggregate view:
- Per-GM queue depth (count of episodes ready to run)
- Stories stale for N days (no progress advancement)
- Stories at frontier (current_episode is null and transitions pending authoring)
- Pending AGM claims across all stories
- Open SessionRequests across all stories
- Counts by scope (CHARACTER / GROUP / GLOBAL)

Commit: `feat(stories-api): staff workload dashboard`

---

## Wave 11 — Action endpoints

Each endpoint wraps the corresponding service. Follow DRF's `@action(detail=True)` pattern. All serializers validate input; services raise typed exceptions; views map `exc.user_message` → 400 response.

### Task 11.1: `POST /api/episodes/{id}/resolve/`

Wraps `resolve_episode`. Input: optional `chosen_transition_id`, optional `gm_notes`. Permission: Lead GM on the story, or Staff.

Commit: `feat(stories-api): episode resolve action`

---

### Task 11.2: `POST /api/beats/{id}/mark/`

Wraps `record_gm_marked_outcome`. Input: `outcome`, `gm_notes`. Permission: Lead GM, assigned AGM (if claim approved), or Staff.

Commit: `feat(stories-api): beat mark action`

---

### Task 11.3: `POST /api/beats/{id}/contribute/`

Wraps `record_aggregate_contribution`. Input: `points`, `source_note`. Permission: the character's owning Account.

Commit: `feat(stories-api): aggregate contribution action`

---

### Task 11.4: AGM claim actions

Wraps `request_claim`, `approve_claim`, `reject_claim`, `cancel_claim`, `complete_claim`.

- `POST /api/assistant-claims/` — `request_claim`, permission: any GMProfile
- `POST /api/assistant-claims/{id}/approve/` — `approve_claim`, permission: Lead GM or Staff
- `POST /api/assistant-claims/{id}/reject/` — `reject_claim`, same permission
- `POST /api/assistant-claims/{id}/cancel/` — `cancel_claim`, permission: the requesting AGM
- `POST /api/assistant-claims/{id}/complete/` — `complete_claim`, permission: Lead GM or Staff

Commit: `feat(stories-api): AGM claim action endpoints`

---

### Task 11.5: SessionRequest action endpoints

- `POST /api/session-requests/{id}/create-event/` — `create_event_from_session_request`
- `POST /api/session-requests/{id}/cancel/` — cancel the request
- `POST /api/session-requests/{id}/resolve/` — mark session complete (after the session runs)

Permissions: Lead GM on the story, requesting player (CHARACTER scope), or Staff.

Commit: `feat(stories-api): SessionRequest action endpoints`

---

### Task 11.6: Staff expire-overdue-beats trigger

`POST /api/stories/expire-overdue-beats/` — staff-only trigger wrapping `expire_overdue_beats`. Mostly for manual operation; a cron can also hit it periodically.

Commit: `feat(stories-api): staff expire-overdue-beats action`

---

## Wave 12 — Integration test + docs

### Task 12.1: Phase 2 end-to-end integration test

**File:** `src/world/stories/tests/test_integration_phase2.py`

Write a scenario covering the expanded flow:
- A GROUP-scope story with a GMTable
- Two characters on the GMTable contribute to an AGGREGATE_THRESHOLD beat (together they cross the threshold)
- An ACHIEVEMENT_HELD beat auto-satisfies when one character earns the achievement
- A CONDITION_HELD beat is unsatisfied until the character acquires the condition, then flips to SUCCESS
- A CODEX_ENTRY_UNLOCKED beat satisfies when the referenced codex entry is discovered
- A STORY_AT_MILESTONE beat references another story at CHAPTER_REACHED; it satisfies when the referenced story's progress advances past that chapter
- GM marks a GM_MARKED beat; transition with routing predicate fires
- Episode becomes ready-to-run; SessionRequest auto-created
- Lead GM creates an Event from the SessionRequest
- AGM requests a claim on a different beat; Lead GM approves; AGM marks the beat
- Deadline sweep expires an overdue beat; transition routes to bad-outcome episode

This is the keystone. If this passes, Phase 2 is structurally sound.

Commit: `test(stories): Phase 2 end-to-end integration test`

---

### Task 12.2: Docs updates + MODEL_MAP regen

**Files:**
- Modify: `docs/roadmap/stories-gm.md` — mark Phase 2 complete; document remaining Phase 3+
- Modify: `docs/systems/stories.md` — rewrite to reflect the expanded model inventory + API surface
- Regenerate `docs/systems/MODEL_MAP.md` via `uv run python tools/introspect_models.py` (note: needs to be called via `write_model_map()`, not `__main__`)

Run full `echo "yes" | uv run arx test` (fresh DB, all apps) and confirm all pass.

Commit: `docs(stories): Phase 2 complete — update roadmap, systems index, model map`

---

## Execution Notes

- **Order dependencies:**
  - Wave 1 before everything else (exception wiring and legacy cleanup are foundational)
  - Wave 3 depends on Wave 2 only if a predicate type uses GROUP/GLOBAL progress (STORY_AT_MILESTONE for example — depends on being able to look up the referenced story's active progress across all scopes)
  - Wave 4 (aggregate ledger) before Wave 3's AGGREGATE_THRESHOLD predicate (same wave — just do in order 4 → 3.5)
  - Wave 6 (AGM) before Wave 8's AGM ViewSet + Wave 11.4's actions
  - Wave 7 (SessionRequest + Events) before Wave 10's dashboards reference SessionRequest status
  - Wave 12 last

- **Testing cadence:**
  - Per task: `uv run arx test world.stories.tests.test_<module> --keepdb`
  - Per wave: `uv run arx test world.stories --keepdb`
  - Before push: `echo "yes" | uv run arx test world.stories world.character_creation world.gm world.roster world.societies world.events world.achievements world.conditions world.codex` (fresh DB)

- **Migration cadence:** each model task generates its own migration. At the end of Phase 2 there should be 10-15 new stories migrations on top of Phase 1's `0012`.

- **Pre-commit hooks:** if a hook fails, fix and re-stage. Never `--no-verify`.

- **When blocked:** if a task needs a cross-app helper that doesn't exist (e.g., a per-character codex-entry discovery check), investigate whether the helper exists. If it doesn't, either (a) add it to the relevant app following the same cached_property pattern Phase 1 established, or (b) pause and ask — do not stub.

- **Scope discipline:** the user has explicitly said scope creep into other apps is fine while the project is in dev. If implementing a Phase 2 task requires a small refinement in `achievements`, `conditions`, `codex`, or `events`, do it inline. Document it in the commit message.
