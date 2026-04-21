# Stories System Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the backend foundation for the task-gated stories system — models, evaluation services, and end-to-end test coverage — enough to prove the core design works. No UI or API yet.

**Architecture:** Extend the existing `src/world/stories/` app. Add `Era`, restructure `Chapter`/`Episode`, introduce `Beat`, `Transition`, `BeatCompletion`, `EpisodeResolution`, `StoryProgress`. Use the existing `DiscriminatorMixin` pattern for beat predicate variants. Episode-level branching only — beats never chain within an episode. CHARACTER scope only; GROUP/GLOBAL deferred.

**Tech Stack:** Django 4.x, PostgreSQL, SharedMemoryModel, FactoryBoy, Evennia test runner (`arx test`).

**Design Reference:** `docs/plans/2026-04-20-stories-system-design.md`

---

## Phase Scope

**In Phase 1:**
- `Era` model (temporal tag; admin-managed)
- Extend `Story` with `scope`, `character_sheet`, `created_in_era`
- Restructure `Chapter` (keep) and `Episode` (remove `connection_to_next`/`connection_summary`; those move to `Transition`)
- `Beat` model with discriminator for predicate types. Two concrete predicate types: `CHARACTER_LEVEL_AT_LEAST` (auto) and `GM_MARKED` (manual).
- `Transition` model with routing predicate (via `TransitionRequiredOutcome`) and mode (AUTO/GM_CHOICE)
- `EpisodeProgressionRequirement` model (beats that must succeed before any outbound transition fires)
- `BeatCompletion` audit ledger (per character / roster entry / era)
- `EpisodeResolution` audit ledger
- `StoryProgress` model (per CharacterSheet pointer to current episode)
- `StoryError` typed exception hierarchy
- Services: beat evaluation, transition eligibility, episode resolution, progress management
- Full test coverage: unit + integration

**Deferred to Phase 2 (noted and next up):**
- Basic REST API + player dashboard + Lead GM dashboard
- Story log query with visibility filtering
- Scheduling CTAs on the dashboard

**Deferred to Phase 3+:**
- GROUP scope (covenant/group-owned progress) and GLOBAL scope (metaplot)
- Additional predicate types: `MISSION_COMPLETE`, `ACHIEVEMENT_HELD`, `AGGREGATE_THRESHOLD`, `STORY_AT_MILESTONE`, `CODEX_ENTRY_UNLOCKED`, `CONDITION_HELD`
- Aggregate contribution ledger
- Deadlines (field scaffolded in Phase 1; expiry handling deferred)
- Secret/hinted visibility UI rules
- Assistant GM queue + claim approvals
- Events system integration (SessionRequest creation)
- Staff cross-story workload dashboard
- Era-stamping on all time-relevant events (scaffolded, wired incrementally)
- Beat authoring UX (non-admin)

---

## Existing State Audit

**Must preserve (used by other apps):**
- `world.stories.models.Story` — imported by `character_creation.services.finalize_gm_character`, `gm.services.surrender_character_story`, `societies.services` (extend, don't replace)
- `world.stories.models.StoryParticipation` — imported by `character_creation`, `gm.tests`, `roster.tests` (leave intact)
- `world.stories.factories.StoryFactory` — imported by `gm.tests`, `roster.tests` (update in place)
- `world.stories.pagination.StandardResultsSetPagination` — imported by many apps (untouched)
- Trust system (`TrustCategory`, `PlayerTrust`, `PlayerTrustLevel`, `StoryTrustRequirement`, `StoryFeedback`, `TrustCategoryFeedbackRating`) — orthogonal, untouched

**Free to restructure (nothing outside stories imports):**
- `Chapter`, `Episode`, `EpisodeScene`

**Test files to update:**
- `src/world/stories/tests/test_models.py` — update for new shape
- `src/world/stories/tests/test_view_actions_permissions.py` — update if it touches Chapter/Episode
- `src/world/character_creation/services.py:1261` — check that extended Story still works with the `Story.objects.create(...)` call (likely needs new fields with sensible defaults)
- `src/world/gm/tests/test_services.py`, `test_invite_views.py`, `test_queue_views.py`, `roster/tests/test_managers.py` — check StoryFactory usage remains valid

---

## Conventions for this plan

- **Pre-commit hooks run on commit.** If they fail, fix and re-stage — don't `--no-verify`.
- **`arx test world.stories --keepdb`** for fast inner loop. Run **without** `--keepdb` before the final task commit (matches CI).
- **Per CLAUDE.md:** SharedMemoryModel for all concrete models; absolute imports only; no Django signals; no JSON fields; TextChoices in `constants.py`; `ty` annotations required (stories is in the typed apps list — verify via `pyproject.toml`).
- **Per MEMORY.md:** use `evennia_extensions` factories in tests (never `create_object()` directly); use `Prefetch(..., to_attr=...)` for prefetch; avoid denormalization; use typed exceptions with `user_message`.
- **Service functions:** accept model instances or pks, never slugs. No validation in services for user-facing checks; raise typed exceptions for programmer errors only.
- **Types in `types.py`:** all dataclasses, TypedDicts, and enum-style constants that need to be imported across modules.
- **Every task ends with a commit.** Small, focused commits.
- **When adding new apps to the typed list:** no new apps here — `world.stories` is already typed.

---

## Task 1: Add `Era` model + constants + factory + admin + tests

**Files:**
- Create: `src/world/stories/constants.py` (if missing; holds `EraStatus`, `StoryScope`, `BeatPredicateType`, `BeatOutcome`, `BeatVisibility`, `TransitionMode` text/integer choices)
- Modify: `src/world/stories/models.py` — add `Era`
- Modify: `src/world/stories/factories.py` — add `EraFactory`
- Modify: `src/world/stories/admin.py` — register `Era`
- Modify: `src/world/stories/tests/test_models.py` — add Era tests
- Run: `arx manage makemigrations stories` then `arx manage migrate`

**Step 1: Write `constants.py`**

```python
# src/world/stories/constants.py
from django.db import models


class EraStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    ACTIVE = "active", "Active"
    CONCLUDED = "concluded", "Concluded"


class StoryScope(models.TextChoices):
    CHARACTER = "character", "Character"
    GROUP = "group", "Group"
    GLOBAL = "global", "Global"


class BeatPredicateType(models.TextChoices):
    GM_MARKED = "gm_marked", "GM-marked"
    CHARACTER_LEVEL_AT_LEAST = "character_level_at_least", "Character level at least"


class BeatOutcome(models.TextChoices):
    UNSATISFIED = "unsatisfied", "Unsatisfied"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    EXPIRED = "expired", "Expired"
    PENDING_GM_REVIEW = "pending_gm_review", "Pending GM review"


class BeatVisibility(models.TextChoices):
    HINTED = "hinted", "Hinted"
    SECRET = "secret", "Secret"
    VISIBLE = "visible", "Visible"


class TransitionMode(models.TextChoices):
    AUTO = "auto", "Auto"
    GM_CHOICE = "gm_choice", "GM Choice"
```

**Step 2: Write failing test**

```python
# src/world/stories/tests/test_era.py
from django.test import TestCase

from world.stories.constants import EraStatus
from world.stories.factories import EraFactory


class EraModelTests(TestCase):
    def test_era_default_status_is_upcoming(self):
        era = EraFactory(status=EraStatus.UPCOMING)
        self.assertEqual(era.status, EraStatus.UPCOMING)

    def test_era_str_uses_display_name(self):
        era = EraFactory(
            name="season_1",
            display_name="Shadows and Light",
            season_number=1,
        )
        self.assertIn("Shadows and Light", str(era))
        self.assertIn("1", str(era))

    def test_only_one_active_era_allowed(self):
        EraFactory(status=EraStatus.ACTIVE, name="era_a")
        with self.assertRaises(Exception):  # IntegrityError via unique constraint
            EraFactory(status=EraStatus.ACTIVE, name="era_b")
```

**Step 3: Run tests, confirm failure**

Run: `arx test world.stories.tests.test_era`
Expected: FAIL — `EraFactory` does not exist.

**Step 4: Implement `Era` model**

```python
# Add to src/world/stories/models.py
from world.stories.constants import EraStatus


class Era(SharedMemoryModel):
    """Staff-activated metaplot era ('Season' in player-facing UI)."""

    name = models.SlugField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    season_number = models.PositiveIntegerField(
        help_text="Player-facing 'Season N' number."
    )
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=EraStatus.choices,
        default=EraStatus.UPCOMING,
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    concluded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status=EraStatus.ACTIVE),
                name="only_one_active_era",
            )
        ]

    def __str__(self) -> str:
        return f"Season {self.season_number}: {self.display_name}"
```

**Step 5: Add `EraFactory`**

```python
# Add to src/world/stories/factories.py
import factory
from factory.django import DjangoModelFactory

from world.stories.constants import EraStatus
from world.stories.models import Era


class EraFactory(DjangoModelFactory):
    class Meta:
        model = Era
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"era_{n}")
    display_name = factory.Sequence(lambda n: f"Era {n}")
    season_number = factory.Sequence(lambda n: n + 1)
    status = EraStatus.UPCOMING
```

**Step 6: Register admin**

```python
# Add to src/world/stories/admin.py
from world.stories.models import Era

@admin.register(Era)
class EraAdmin(admin.ModelAdmin):
    list_display = ("season_number", "display_name", "status", "activated_at")
    list_filter = ("status",)
    search_fields = ("name", "display_name")
    ordering = ("-season_number",)
```

**Step 7: Generate + apply migration**

Run: `arx manage makemigrations stories`
Run: `arx manage migrate`

**Step 8: Run tests, confirm pass**

Run: `arx test world.stories.tests.test_era --keepdb`
Expected: PASS.

**Step 9: Commit**

```bash
git add src/world/stories/
git commit -m "feat(stories): add Era model for metaplot era tracking"
```

---

## Task 2: Extend `Story` model with `scope`, `character_sheet`, `created_in_era`

**Files:**
- Modify: `src/world/stories/models.py` (Story class)
- Modify: `src/world/stories/factories.py` (StoryFactory)
- Modify: `src/world/stories/tests/test_models.py`
- Verify: `src/world/character_creation/services.py:1261` still works (pass `scope=StoryScope.CHARACTER` explicitly when CG creates stories)

**Step 1: Write failing test**

```python
# src/world/stories/tests/test_story_extensions.py
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import StoryScope
from world.stories.factories import EraFactory, StoryFactory


class StoryExtensionTests(TestCase):
    def test_story_defaults_to_character_scope(self):
        story = StoryFactory()
        self.assertEqual(story.scope, StoryScope.CHARACTER)

    def test_character_scope_requires_character_sheet(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        self.assertEqual(story.character_sheet, sheet)

    def test_story_records_era_of_creation(self):
        era = EraFactory()
        story = StoryFactory(created_in_era=era)
        self.assertEqual(story.created_in_era, era)
```

**Step 2: Confirm failure**

Run: `arx test world.stories.tests.test_story_extensions --keepdb`
Expected: FAIL — fields do not exist.

**Step 3: Add fields to `Story`**

```python
# Add to Story in src/world/stories/models.py
from world.stories.constants import StoryScope

# Inside Story class, alongside existing fields:
scope = models.CharField(
    max_length=20,
    choices=StoryScope.choices,
    default=StoryScope.CHARACTER,
)
character_sheet = models.ForeignKey(
    "character_sheets.CharacterSheet",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="owned_stories",
    help_text="For CHARACTER-scope stories: the character whose story this is.",
)
created_in_era = models.ForeignKey(
    Era,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="stories_created_in_era",
)

def clean(self) -> None:
    super().clean()
    if self.scope == StoryScope.CHARACTER and self.character_sheet is None:
        # Allow null on create, enforce before advancing progress in services.
        pass
```

**Step 4: Update `StoryFactory`**

```python
# In src/world/stories/factories.py — update StoryFactory
from world.stories.constants import StoryScope

# Inside StoryFactory class:
scope = StoryScope.CHARACTER
character_sheet = None  # Tests that need character-scoped stories set this explicitly.
created_in_era = None
```

**Step 5: Make + apply migration**

Run: `arx manage makemigrations stories` → should produce one migration adding three fields.
Run: `arx manage migrate`

**Step 6: Run tests, confirm pass**

Run: `arx test world.stories.tests.test_story_extensions --keepdb`
Expected: PASS.

**Step 7: Verify upstream callers still work**

Run: `arx test world.character_creation world.gm world.roster world.societies --keepdb`
Expected: all PASS. If any fail because `Story.objects.create(...)` needs updating, fix the caller to pass `scope=StoryScope.CHARACTER` explicitly (do not add defaulting logic to hide this — make it explicit at call sites).

**Step 8: Commit**

```bash
git add src/world/
git commit -m "feat(stories): extend Story with scope, character_sheet, created_in_era"
```

---

## Task 3: Restructure `Episode` — remove `connection_to_next`, `connection_summary`

**Files:**
- Modify: `src/world/stories/models.py` (Episode)
- Modify: `src/world/stories/tests/test_models.py` (drop tests referencing removed fields)
- Modify: `src/world/stories/serializers.py` and `admin.py` if they reference the fields

**Rationale:** Transitions now carry connection flavor and summary. Keeping the legacy fields causes confusion.

**Step 1: Grep for usages**

Run:
```bash
/c/Program\ Files/Git/usr/bin/grep -rn "connection_to_next\|connection_summary" src/
```
Enumerate all usage sites; remove references.

**Step 2: Write a simple test that Episode still exists and still links to Chapter**

```python
# src/world/stories/tests/test_episode.py
from django.test import TestCase
from world.stories.factories import EpisodeFactory


class EpisodeTests(TestCase):
    def test_episode_belongs_to_chapter(self):
        episode = EpisodeFactory()
        self.assertIsNotNone(episode.chapter)

    def test_episode_has_no_connection_fields(self):
        # Regression: those fields moved to Transition in Phase 1.
        episode = EpisodeFactory()
        self.assertFalse(hasattr(episode, "connection_to_next"))
        self.assertFalse(hasattr(episode, "connection_summary"))
```

**Step 3: Remove fields from `Episode`**

Also remove `connection_type` and `connection_summary` from `EpisodeScene` if present — those belong on Transition.

**Step 4: Update serializers + admin to drop references**

**Step 5: Migration**

Run: `arx manage makemigrations stories` → RemoveField migration.
Run: `arx manage migrate`

**Step 6: Run stories app tests**

Run: `arx test world.stories --keepdb`
Expected: PASS (no references to removed fields remain).

**Step 7: Commit**

```bash
git add src/world/stories/
git commit -m "refactor(stories): remove Episode connection fields (moved to Transition)"
```

---

## Task 4: Add `Transition` model

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_transition.py`

**Step 1: Failing test**

```python
from django.test import TestCase

from world.stories.constants import TransitionMode
from world.stories.factories import EpisodeFactory, TransitionFactory


class TransitionTests(TestCase):
    def test_transition_connects_two_episodes(self):
        source = EpisodeFactory()
        target = EpisodeFactory(chapter=source.chapter)
        transition = TransitionFactory(source_episode=source, target_episode=target)
        self.assertEqual(transition.source_episode, source)
        self.assertEqual(transition.target_episode, target)

    def test_transition_can_have_null_target_for_unauthored_frontier(self):
        transition = TransitionFactory(target_episode=None)
        self.assertIsNone(transition.target_episode)

    def test_transition_default_mode_is_auto(self):
        transition = TransitionFactory()
        self.assertEqual(transition.mode, TransitionMode.AUTO)
```

**Step 2: Confirm failure**

Run: `arx test world.stories.tests.test_transition --keepdb` → FAIL.

**Step 3: Implement `Transition`**

```python
# Add to src/world/stories/models.py
from world.stories.constants import TransitionMode


class Transition(SharedMemoryModel):
    """A guarded edge from one Episode to another."""

    source_episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="outbound_transitions",
    )
    target_episode = models.ForeignKey(
        "stories.Episode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_transitions",
        help_text="May be null when next episode is unauthored (frontier pause).",
    )
    mode = models.CharField(
        max_length=20,
        choices=TransitionMode.choices,
        default=TransitionMode.AUTO,
    )
    connection_type = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        blank=True,
        default="",
        help_text="Narrative flavor: THEREFORE / BUT.",
    )
    connection_summary = models.TextField(
        blank=True,
        help_text="Short narrative description of why this transition fires.",
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_episode", "order"]
        indexes = [
            models.Index(fields=["source_episode"]),
        ]

    def __str__(self) -> str:
        target_name = self.target_episode.title if self.target_episode else "(unauthored)"
        return f"{self.source_episode.title} -> {target_name}"
```

Note: `ConnectionType` already exists in `types.py`; if not, move/create it there.

**Step 4: Factory**

```python
# src/world/stories/factories.py
class TransitionFactory(DjangoModelFactory):
    class Meta:
        model = Transition

    source_episode = factory.SubFactory(EpisodeFactory)
    target_episode = factory.LazyAttribute(
        lambda obj: EpisodeFactory(chapter=obj.source_episode.chapter)
    )
    mode = TransitionMode.AUTO
    order = 0
```

**Step 5: Admin registration + migration + tests + commit**

Run: `arx manage makemigrations stories && arx manage migrate`
Run: `arx test world.stories.tests.test_transition --keepdb` → PASS.

```bash
git add src/world/stories/
git commit -m "feat(stories): add Transition model for episode branching"
```

---

## Task 5: Add `EpisodeProgressionRequirement` and `TransitionRequiredOutcome`

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py` (inline under Transition/Episode)
- Create: `src/world/stories/tests/test_requirements.py`

**Step 1: Failing tests**

```python
from django.test import TestCase

from world.stories.constants import BeatOutcome
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)


class RequirementTests(TestCase):
    def test_progression_requirement_links_episode_to_beat(self):
        episode = EpisodeFactory()
        beat = BeatFactory(episode=episode)
        req = EpisodeProgressionRequirementFactory(
            episode=episode,
            beat=beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        self.assertEqual(req.episode, episode)
        self.assertEqual(req.beat, beat)

    def test_transition_required_outcome_links_to_beat(self):
        transition = TransitionFactory()
        beat = BeatFactory(episode=transition.source_episode)
        req = TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
        )
        self.assertEqual(req.required_outcome, BeatOutcome.FAILURE)
```

(Note: `BeatFactory` doesn't exist yet — this test will fail on import until Task 6. Pre-write it; proceed to Task 6 to satisfy.)

**Step 2: Implement models**

```python
# Add to src/world/stories/models.py
class EpisodeProgressionRequirement(SharedMemoryModel):
    """A beat that must reach `required_outcome` before any transition fires."""

    episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="progression_requirements",
    )
    beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.CASCADE,
        related_name="gating_for_episodes",
    )
    required_outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
        default=BeatOutcome.SUCCESS,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["episode", "beat"],
                name="unique_progression_req_per_episode_beat",
            )
        ]


class TransitionRequiredOutcome(SharedMemoryModel):
    """A beat outcome that must be satisfied for this transition to be eligible."""

    transition = models.ForeignKey(
        "stories.Transition",
        on_delete=models.CASCADE,
        related_name="required_outcomes",
    )
    beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.CASCADE,
        related_name="routing_for_transitions",
    )
    required_outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transition", "beat"],
                name="unique_routing_req_per_transition_beat",
            )
        ]
```

**Step 3–6: Factories, admin inlines, migration, commit**

Run tests after Task 6 (since Beat is required).

```bash
# After Task 6 passes these tests:
git commit -m "feat(stories): add progression and routing requirement models"
```

---

## Task 6: Add `Beat` model with discriminator + both predicate types

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_beat.py`

**Step 1: Failing tests**

```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from world.stories.constants import BeatOutcome, BeatPredicateType, BeatVisibility
from world.stories.factories import BeatFactory, EpisodeFactory


class BeatTests(TestCase):
    def test_default_beat_is_gm_marked(self):
        beat = BeatFactory()
        self.assertEqual(beat.predicate_type, BeatPredicateType.GM_MARKED)
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertEqual(beat.visibility, BeatVisibility.HINTED)

    def test_character_level_beat_requires_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_level=5,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_beat_text_layers(self):
        beat = BeatFactory(
            internal_description="Real predicate: research project X",
            player_hint="Something about the night...",
            player_resolution_text="You learned the truth.",
        )
        self.assertIn("X", beat.internal_description)
        self.assertIn("night", beat.player_hint)
        self.assertIn("truth", beat.player_resolution_text)
```

**Step 2: Confirm failure**

Run: `arx test world.stories.tests.test_beat --keepdb` → FAIL.

**Step 3: Implement `Beat`**

```python
# Add to src/world/stories/models.py
from world.stories.constants import BeatOutcome, BeatPredicateType, BeatVisibility


class Beat(SharedMemoryModel):
    """
    A boolean predicate attached to an episode, with rich outcome state.

    Predicate-type-specific config is stored as nullable columns on this model.
    ``clean()`` enforces that exactly the right columns are populated for the
    chosen predicate_type.
    """

    episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.CASCADE,
        related_name="beats",
    )
    predicate_type = models.CharField(
        max_length=40,
        choices=BeatPredicateType.choices,
        default=BeatPredicateType.GM_MARKED,
    )
    outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
        default=BeatOutcome.UNSATISFIED,
        help_text=(
            "Current outcome for this beat in the story's current play session. "
            "Historical outcomes live in BeatCompletion."
        ),
    )
    visibility = models.CharField(
        max_length=20,
        choices=BeatVisibility.choices,
        default=BeatVisibility.HINTED,
    )

    # Text layers
    internal_description = models.TextField(
        help_text="Author/Lead GM/staff view: real predicate + meaning.",
    )
    player_hint = models.TextField(
        blank=True,
        help_text="Shown while active (if visibility=HINTED or VISIBLE).",
    )
    player_resolution_text = models.TextField(
        blank=True,
        help_text="Shown in story log after beat completes.",
    )

    # Predicate-type-specific config (nullable; populated based on predicate_type)
    required_level = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For CHARACTER_LEVEL_AT_LEAST predicates.",
    )

    # Scaffolding for future phases (not wired yet):
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional wall-clock deadline. Expiry handling deferred to Phase 3+.",
    )

    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["episode", "order"]
        indexes = [
            models.Index(fields=["episode", "outcome"]),
        ]

    # Invariant mapping: predicate_type -> required config field names
    _REQUIRED_CONFIG: dict[str, tuple[str, ...]] = {
        BeatPredicateType.GM_MARKED: (),
        BeatPredicateType.CHARACTER_LEVEL_AT_LEAST: ("required_level",),
    }

    def clean(self) -> None:
        super().clean()
        required = self._REQUIRED_CONFIG.get(self.predicate_type, ())
        errors: dict[str, str] = {}
        for field_name in required:
            if getattr(self, field_name) in (None, ""):
                errors[field_name] = (
                    f"Required when predicate_type is {self.predicate_type}."
                )
        # All non-required config fields must be null for this predicate_type.
        all_config_fields = {"required_level"}
        for field_name in all_config_fields - set(required):
            if getattr(self, field_name) is not None:
                errors[field_name] = (
                    f"Must be null when predicate_type is {self.predicate_type}."
                )
        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Beat({self.predicate_type}) on {self.episode.title}"
```

**Step 4: `BeatFactory`**

```python
class BeatFactory(DjangoModelFactory):
    class Meta:
        model = Beat

    episode = factory.SubFactory(EpisodeFactory)
    predicate_type = BeatPredicateType.GM_MARKED
    outcome = BeatOutcome.UNSATISFIED
    visibility = BeatVisibility.HINTED
    internal_description = factory.Faker("sentence")
    player_hint = factory.Faker("sentence")
    player_resolution_text = factory.Faker("sentence")
    required_level = None
```

**Step 5: Admin, migration, tests, commit**

Run: `arx manage makemigrations stories && arx manage migrate`
Run: `arx test world.stories.tests.test_beat world.stories.tests.test_requirements --keepdb` → PASS.

```bash
git add src/world/stories/
git commit -m "feat(stories): add Beat model with predicate discriminator"
```

---

## Task 7: Add `BeatCompletion` audit ledger

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_beat_completion.py`

**Step 1: Failing tests**

```python
from django.test import TestCase
from django.utils import timezone

from world.stories.constants import BeatOutcome
from world.stories.factories import BeatCompletionFactory, BeatFactory


class BeatCompletionTests(TestCase):
    def test_completion_records_outcome_and_character(self):
        beat = BeatFactory()
        completion = BeatCompletionFactory(beat=beat, outcome=BeatOutcome.SUCCESS)
        self.assertEqual(completion.beat, beat)
        self.assertEqual(completion.outcome, BeatOutcome.SUCCESS)
        self.assertIsNotNone(completion.character_sheet)
        self.assertLessEqual(completion.recorded_at, timezone.now())

    def test_completion_captures_era(self):
        from world.stories.factories import EraFactory
        era = EraFactory()
        completion = BeatCompletionFactory(era=era)
        self.assertEqual(completion.era, era)
```

**Step 2: Implement**

```python
class BeatCompletion(SharedMemoryModel):
    """Audit ledger row for each beat outcome applied to a character's progress."""

    beat = models.ForeignKey(
        Beat,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="beat_completions",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=(
            "Which roster tenure (which player) was active when this beat "
            "completed. For audit only."
        ),
    )
    outcome = models.CharField(
        max_length=20,
        choices=BeatOutcome.choices,
    )
    era = models.ForeignKey(
        Era,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="beat_completions",
    )
    gm_notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["beat", "character_sheet"]),
            models.Index(fields=["character_sheet", "-recorded_at"]),
        ]
```

**Step 3: Factory, admin, migration, tests, commit**

```bash
git add src/world/stories/
git commit -m "feat(stories): add BeatCompletion audit ledger"
```

---

## Task 8: Add `EpisodeResolution` audit ledger

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_episode_resolution.py`

**Step 1: Failing test**

```python
from django.test import TestCase

from world.stories.factories import (
    EpisodeFactory,
    EpisodeResolutionFactory,
    TransitionFactory,
)


class EpisodeResolutionTests(TestCase):
    def test_resolution_records_transition_and_episode(self):
        source = EpisodeFactory()
        transition = TransitionFactory(source_episode=source)
        resolution = EpisodeResolutionFactory(
            episode=source,
            chosen_transition=transition,
        )
        self.assertEqual(resolution.episode, source)
        self.assertEqual(resolution.chosen_transition, transition)

    def test_resolution_allows_null_transition(self):
        # When an episode ends with no transition fired (e.g., frontier pause).
        resolution = EpisodeResolutionFactory(chosen_transition=None)
        self.assertIsNone(resolution.chosen_transition)
```

**Step 2: Implement**

```python
class EpisodeResolution(SharedMemoryModel):
    """Audit record when an episode is resolved and (optionally) a transition fires."""

    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name="resolutions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="episode_resolutions",
    )
    chosen_transition = models.ForeignKey(
        Transition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolutions_using",
    )
    resolved_by = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="episode_resolutions",
    )
    era = models.ForeignKey(
        Era,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    gm_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["episode", "-resolved_at"]),
            models.Index(fields=["character_sheet", "-resolved_at"]),
        ]
```

**Step 3: Factory, admin, migration, tests, commit**

```bash
git commit -m "feat(stories): add EpisodeResolution audit ledger"
```

---

## Task 9: Add `StoryProgress` model

**Files:**
- Modify: `src/world/stories/models.py`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_story_progress.py`

**Step 1: Failing tests**

```python
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.factories import EpisodeFactory, StoryFactory, StoryProgressFactory


class StoryProgressTests(TestCase):
    def test_progress_links_story_to_character_sheet(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(character_sheet=sheet)
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        self.assertEqual(progress.story, story)
        self.assertEqual(progress.character_sheet, sheet)

    def test_progress_tracks_current_episode(self):
        episode = EpisodeFactory()
        progress = StoryProgressFactory(current_episode=episode)
        self.assertEqual(progress.current_episode, episode)

    def test_one_progress_per_story_per_character(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(character_sheet=sheet)
        StoryProgressFactory(story=story, character_sheet=sheet)
        with self.assertRaises(Exception):  # IntegrityError
            StoryProgressFactory(story=story, character_sheet=sheet)
```

**Step 2: Implement**

```python
class StoryProgress(SharedMemoryModel):
    """Per-character pointer into a CHARACTER-scope story's current state."""

    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="story_progress",
    )
    current_episode = models.ForeignKey(
        Episode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_progress_records",
        help_text="Null while the story is at the frontier (unauthored) or before start.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_advanced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "character_sheet"],
                name="unique_progress_per_story_per_character",
            )
        ]
        indexes = [
            models.Index(fields=["character_sheet", "is_active"]),
        ]
```

**Step 3: Factory, admin, migration, tests, commit**

```bash
git commit -m "feat(stories): add StoryProgress per-character progress pointer"
```

---

## Task 10: Typed exception hierarchy

**Files:**
- Create: `src/world/stories/exceptions.py`
- Create: `src/world/stories/tests/test_exceptions.py`

**Pattern:** Follow `EventError` / `JournalError` / `ProgressionError` — typed exceptions with a `user_message` property and an allowlist of safe messages.

**Step 1: Failing test**

```python
from django.test import TestCase

from world.stories.exceptions import (
    StoryError,
    BeatNotResolvableError,
    NoEligibleTransitionError,
    AmbiguousTransitionError,
    ProgressionRequirementNotMetError,
)


class StoryExceptionTests(TestCase):
    def test_beat_not_resolvable_safe_message(self):
        exc = BeatNotResolvableError("internal: weird state")
        self.assertEqual(
            exc.user_message,
            "This beat cannot be resolved in its current state.",
        )

    def test_no_eligible_transition_safe_message(self):
        exc = NoEligibleTransitionError()
        self.assertIn("no transition", exc.user_message.lower())
```

**Step 2: Implement**

```python
# src/world/stories/exceptions.py
class StoryError(Exception):
    """Base class for stories-app user-facing errors."""

    _SAFE_MESSAGE = "A story system error occurred."

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGE


class BeatNotResolvableError(StoryError):
    _SAFE_MESSAGE = "This beat cannot be resolved in its current state."


class NoEligibleTransitionError(StoryError):
    _SAFE_MESSAGE = "There is no transition available to advance this episode."


class AmbiguousTransitionError(StoryError):
    _SAFE_MESSAGE = "Multiple transitions are eligible — please pick one."


class ProgressionRequirementNotMetError(StoryError):
    _SAFE_MESSAGE = "Progression requirements for this episode are not yet met."
```

**Step 3: Run, commit**

```bash
git add src/world/stories/
git commit -m "feat(stories): add typed exception hierarchy"
```

---

## Task 11: Beat evaluation service

**Files:**
- Create: `src/world/stories/services/__init__.py`
- Create: `src/world/stories/services/beats.py`
- Create: `src/world/stories/tests/test_services_beats.py`

**Step 1: Failing test**

```python
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.factories import BeatFactory, EpisodeFactory, StoryProgressFactory
from world.stories.services.beats import (
    evaluate_auto_beats,
    record_gm_marked_outcome,
)


class EvaluateAutoBeatsTests(TestCase):
    def test_character_level_beat_satisfied_when_level_meets_requirement(self):
        sheet = CharacterSheetFactory()
        # Assume there's a helper in progression to set level; if not, stub/mock here.
        _set_character_level(sheet, 5)

        episode = EpisodeFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=episode
        )

        evaluate_auto_beats(progress)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_character_level_beat_unsatisfied_when_below(self):
        sheet = CharacterSheetFactory()
        _set_character_level(sheet, 1)
        episode = EpisodeFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=episode
        )
        evaluate_auto_beats(progress)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_gm_marked_beats_untouched_by_auto_eval(self):
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=episode
        )
        evaluate_auto_beats(progress)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class RecordGmMarkedOutcomeTests(TestCase):
    def test_sets_outcome_and_creates_completion(self):
        sheet = CharacterSheetFactory()
        episode = EpisodeFactory()
        beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.GM_MARKED)
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=episode
        )
        record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Player convinced the Herald.",
        )
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(beat.completions.count(), 1)
        completion = beat.completions.first()
        self.assertEqual(completion.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(completion.character_sheet, sheet)
```

`_set_character_level` is a helper the test writes — use the real progression helper if one exists (check `world.progression`), or compose via `ClassLevel`/trait-based level helpers. If the level cannot be set via existing public API, this test may need to use a monkey-patched computed level on CharacterSheet; flag this to the reviewer.

**Step 2: Implement**

```python
# src/world/stories/services/beats.py
from django.db import transaction
from django.utils import timezone

from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.exceptions import BeatNotResolvableError
from world.stories.models import Beat, BeatCompletion, Era, StoryProgress


def evaluate_auto_beats(progress: StoryProgress) -> None:
    """Re-evaluate all auto-detected beats in the progress's current episode.

    Updates beat.outcome in-place and records BeatCompletion rows for any
    beats that transitioned to a resolved outcome.
    """
    if progress.current_episode is None:
        return
    active_era = _get_active_era()
    current_tenure = _current_roster_entry(progress.character_sheet)

    beats = list(
        progress.current_episode.beats.select_related().filter(
            predicate_type__in=_AUTO_PREDICATE_TYPES,
        )
    )
    with transaction.atomic():
        for beat in beats:
            new_outcome = _evaluate_predicate(beat, progress)
            if new_outcome != beat.outcome and new_outcome != BeatOutcome.UNSATISFIED:
                beat.outcome = new_outcome
                beat.save(update_fields=["outcome", "updated_at"])
                BeatCompletion.objects.create(
                    beat=beat,
                    character_sheet=progress.character_sheet,
                    roster_entry=current_tenure,
                    outcome=new_outcome,
                    era=active_era,
                )


def record_gm_marked_outcome(
    *,
    progress: StoryProgress,
    beat: Beat,
    outcome: BeatOutcome,
    gm_notes: str = "",
) -> BeatCompletion:
    """Record a GM's decision on a GM_MARKED beat."""
    if beat.predicate_type != BeatPredicateType.GM_MARKED:
        raise BeatNotResolvableError("Beat is not GM-marked.")
    if outcome not in _GM_MARKED_VALID_OUTCOMES:
        raise BeatNotResolvableError(f"Invalid outcome for GM-marked beat: {outcome}")

    with transaction.atomic():
        beat.outcome = outcome
        beat.save(update_fields=["outcome", "updated_at"])
        completion = BeatCompletion.objects.create(
            beat=beat,
            character_sheet=progress.character_sheet,
            roster_entry=_current_roster_entry(progress.character_sheet),
            outcome=outcome,
            era=_get_active_era(),
            gm_notes=gm_notes,
        )
    return completion


_AUTO_PREDICATE_TYPES = frozenset({BeatPredicateType.CHARACTER_LEVEL_AT_LEAST})
_GM_MARKED_VALID_OUTCOMES = frozenset({
    BeatOutcome.SUCCESS,
    BeatOutcome.FAILURE,
})


def _evaluate_predicate(beat: Beat, progress: StoryProgress) -> BeatOutcome:
    if beat.predicate_type == BeatPredicateType.CHARACTER_LEVEL_AT_LEAST:
        level = _character_level(progress.character_sheet)
        return BeatOutcome.SUCCESS if level >= beat.required_level else BeatOutcome.UNSATISFIED
    return BeatOutcome.UNSATISFIED


def _character_level(character_sheet) -> int:
    # Delegate to the progression helper. Use the existing public API in
    # world.progression — consult docs/systems/progression.md.
    ...


def _get_active_era() -> Era | None:
    from world.stories.constants import EraStatus
    return Era.objects.filter(status=EraStatus.ACTIVE).first()


def _current_roster_entry(character_sheet):
    # CharacterSheet -> primary persona -> character object -> current tenure's RosterEntry.
    # Use RosterEntry.objects.for_character_sheet(...) if that manager exists;
    # otherwise use RosterEntry.objects.filter(character_sheet=...).active().first()
    ...
```

**Step 3: Run, commit**

Run: `arx test world.stories.tests.test_services_beats --keepdb`
Expected: PASS.

```bash
git add src/world/stories/services/ src/world/stories/tests/
git commit -m "feat(stories): add beat evaluation service"
```

---

## Task 12: Transition eligibility service

**Files:**
- Create: `src/world/stories/services/transitions.py`
- Create: `src/world/stories/tests/test_services_transitions.py`

**Step 1: Failing test**

```python
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatOutcome
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.services.transitions import get_eligible_transitions


class GetEligibleTransitionsTests(TestCase):
    def test_no_transitions_eligible_when_progression_requirement_unmet(self):
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        gating_beat = BeatFactory(episode=source)
        EpisodeProgressionRequirementFactory(
            episode=source, beat=gating_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=source)
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )
        self.assertEqual(list(get_eligible_transitions(progress)), [])

    def test_transition_eligible_when_requirements_met(self):
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        routing_beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)
        transition = TransitionFactory(source_episode=source)
        TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=routing_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )
        eligible = list(get_eligible_transitions(progress))
        self.assertEqual(eligible, [transition])

    def test_branching_on_beat_outcome(self):
        """Failure routes to 2B, success routes to 2A."""
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        mission_beat = BeatFactory(episode=source, outcome=BeatOutcome.FAILURE)
        trans_2a = TransitionFactory(source_episode=source)
        trans_2b = TransitionFactory(source_episode=source)
        TransitionRequiredOutcomeFactory(
            transition=trans_2a, beat=mission_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionRequiredOutcomeFactory(
            transition=trans_2b, beat=mission_beat, required_outcome=BeatOutcome.FAILURE
        )
        progress = StoryProgressFactory(character_sheet=sheet, current_episode=source)
        self.assertEqual(list(get_eligible_transitions(progress)), [trans_2b])
```

**Step 2: Implement**

```python
# src/world/stories/services/transitions.py
from typing import Iterable

from world.stories.constants import BeatOutcome
from world.stories.models import StoryProgress, Transition


def get_eligible_transitions(progress: StoryProgress) -> Iterable[Transition]:
    """Return transitions from the current episode whose predicates are met."""
    episode = progress.current_episode
    if episode is None:
        return []

    # Check progression requirements — all must be satisfied.
    progression_reqs = list(
        episode.progression_requirements.select_related("beat").all()
    )
    for req in progression_reqs:
        if req.beat.outcome != req.required_outcome:
            return []

    # Evaluate each outbound transition's routing requirements.
    eligible: list[Transition] = []
    transitions = (
        episode.outbound_transitions
        .prefetch_related("required_outcomes__beat")
        .order_by("order")
    )
    for transition in transitions:
        required = list(transition.required_outcomes.all())
        if all(req.beat.outcome == req.required_outcome for req in required):
            eligible.append(transition)
    return eligible
```

**Step 3: Commit**

Run tests, commit.

```bash
git commit -m "feat(stories): add transition eligibility service"
```

---

## Task 13: Episode resolution service

**Files:**
- Create: `src/world/stories/services/episodes.py`
- Create: `src/world/stories/tests/test_services_episodes.py`

**Step 1: Failing test — full happy path + edge cases**

```python
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatOutcome, TransitionMode
from world.stories.exceptions import (
    AmbiguousTransitionError,
    NoEligibleTransitionError,
)
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.services.episodes import resolve_episode


class ResolveEpisodeTests(TestCase):
    def test_auto_transition_fires_and_advances_progress(self):
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        target = EpisodeFactory(chapter=source.chapter)
        routing_beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)
        transition = TransitionFactory(
            source_episode=source, target_episode=target, mode=TransitionMode.AUTO
        )
        TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=routing_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )
        resolution = resolve_episode(progress=progress)
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, transition)

    def test_gm_choice_required_when_multiple_eligible(self):
        # Two eligible transitions — neither fires without explicit choice.
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        target_a = EpisodeFactory(chapter=source.chapter)
        target_b = EpisodeFactory(chapter=source.chapter)
        beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)
        t_a = TransitionFactory(
            source_episode=source, target_episode=target_a, mode=TransitionMode.GM_CHOICE
        )
        t_b = TransitionFactory(
            source_episode=source, target_episode=target_b, mode=TransitionMode.GM_CHOICE
        )
        for t in (t_a, t_b):
            TransitionRequiredOutcomeFactory(
                transition=t, beat=beat, required_outcome=BeatOutcome.SUCCESS
            )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )

        with self.assertRaises(AmbiguousTransitionError):
            resolve_episode(progress=progress)

        # But with chosen_transition, resolves cleanly.
        resolution = resolve_episode(progress=progress, chosen_transition=t_a)
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target_a)
        self.assertEqual(resolution.chosen_transition, t_a)

    def test_no_eligible_transition_raises(self):
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )
        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

    def test_null_target_parks_progress_at_frontier(self):
        sheet = CharacterSheetFactory()
        source = EpisodeFactory()
        beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)
        transition = TransitionFactory(
            source_episode=source, target_episode=None, mode=TransitionMode.AUTO
        )
        TransitionRequiredOutcomeFactory(
            transition=transition, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )
        progress = StoryProgressFactory(
            character_sheet=sheet, current_episode=source
        )
        resolution = resolve_episode(progress=progress)
        progress.refresh_from_db()
        self.assertIsNone(progress.current_episode)
        self.assertEqual(resolution.chosen_transition, transition)
```

**Step 2: Implement**

```python
# src/world/stories/services/episodes.py
from django.db import transaction

from world.stories.constants import TransitionMode
from world.stories.exceptions import (
    AmbiguousTransitionError,
    NoEligibleTransitionError,
)
from world.stories.models import EpisodeResolution, StoryProgress, Transition
from world.stories.services.transitions import get_eligible_transitions


def resolve_episode(
    *,
    progress: StoryProgress,
    chosen_transition: Transition | None = None,
    gm_notes: str = "",
    resolved_by=None,
) -> EpisodeResolution:
    """Finalize the current episode and advance progress to the transition target.

    If multiple transitions are eligible and GM_CHOICE applies, the caller must
    pass chosen_transition explicitly. If a single AUTO transition is eligible,
    it fires. If none are eligible, raises NoEligibleTransitionError.
    """
    eligible = list(get_eligible_transitions(progress))
    if not eligible:
        raise NoEligibleTransitionError()

    transition = _select_transition(eligible, chosen_transition)

    with transaction.atomic():
        resolution = EpisodeResolution.objects.create(
            episode=progress.current_episode,
            character_sheet=progress.character_sheet,
            chosen_transition=transition,
            resolved_by=resolved_by,
            gm_notes=gm_notes,
            era=_get_active_era(),
        )
        progress.current_episode = transition.target_episode  # may be None (frontier)
        progress.save(update_fields=["current_episode", "last_advanced_at"])
    return resolution


def _select_transition(
    eligible: list[Transition],
    chosen: Transition | None,
) -> Transition:
    if chosen is not None:
        if chosen not in eligible:
            raise NoEligibleTransitionError()
        return chosen
    # No explicit choice: only valid if exactly one AUTO transition is eligible.
    auto_transitions = [t for t in eligible if t.mode == TransitionMode.AUTO]
    if len(eligible) == 1 and eligible[0].mode == TransitionMode.AUTO:
        return eligible[0]
    if len(auto_transitions) == 1 and all(
        t.mode == TransitionMode.AUTO for t in eligible
    ):
        # Exactly one AUTO among only AUTOs but >1 total: still ambiguous.
        raise AmbiguousTransitionError()
    raise AmbiguousTransitionError()


def _get_active_era():
    from world.stories.constants import EraStatus
    from world.stories.models import Era
    return Era.objects.filter(status=EraStatus.ACTIVE).first()
```

**Step 3: Commit**

```bash
git commit -m "feat(stories): add episode resolution service with transition selection"
```

---

## Task 14: Integration test — full flow

**File:** `src/world/stories/tests/test_integration_phase1.py`

**Goal:** A single test that walks through the whole Phase 1 loop:
1. Staff creates Era
2. Author creates Story (CHARACTER scope), Chapter, Episodes, Beats, Transitions
3. Author wires progression requirements and routing requirements
4. Player's character starts progressing — level-up auto-satisfies a beat
5. GM marks the GM_MARKED beat
6. `resolve_episode` fires, progress advances to next episode
7. Story log audit trail is populated: BeatCompletion + EpisodeResolution rows with correct character_sheet, roster_entry, era

**Step 1: Write the scenario test**

```python
class FullLoopPhase1IntegrationTest(TestCase):
    def test_crucible_who_am_i_episode_1_to_2(self):
        # Arrange: Era, roster character, story, chapter, episodes, beats, transitions
        era = EraFactory(status=EraStatus.ACTIVE, season_number=1)
        sheet = CharacterSheetFactory(name="Crucible Mundi")
        tenure = RosterTenureFactory(character_sheet=sheet)  # or however it's done
        story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            created_in_era=era,
        )
        chapter = ChapterFactory(story=story)
        ep_1 = EpisodeFactory(chapter=chapter, title="Intro: The Mysterious Past")
        ep_2a = EpisodeFactory(chapter=chapter, title="Ch1 Ep2A: The Revelation")
        ep_2b = EpisodeFactory(chapter=chapter, title="Ch1 Ep2B: The Doubt")

        gating_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=2,
            internal_description="Reach level 2",
            player_hint="Continue growing before the next revelation.",
        )
        meeting_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.GM_MARKED,
            internal_description="Meeting with the Herald NPC",
            player_hint="A stranger watches you from the edge of the market.",
        )

        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=gating_beat, required_outcome=BeatOutcome.SUCCESS
        )
        t_to_2a = TransitionFactory(
            source_episode=ep_1, target_episode=ep_2a, mode=TransitionMode.AUTO,
            connection_type=ConnectionType.THEREFORE,
        )
        t_to_2b = TransitionFactory(
            source_episode=ep_1, target_episode=ep_2b, mode=TransitionMode.AUTO,
            connection_type=ConnectionType.BUT,
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2a, beat=meeting_beat, required_outcome=BeatOutcome.SUCCESS,
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2b, beat=meeting_beat, required_outcome=BeatOutcome.FAILURE,
        )

        progress = StoryProgressFactory(
            story=story, character_sheet=sheet, current_episode=ep_1
        )

        # Act 1: Before level-up, auto eval does nothing.
        _set_character_level(sheet, 1)
        evaluate_auto_beats(progress)
        gating_beat.refresh_from_db()
        self.assertEqual(gating_beat.outcome, BeatOutcome.UNSATISFIED)

        # Act 2: Level up — auto beat satisfies.
        _set_character_level(sheet, 2)
        evaluate_auto_beats(progress)
        gating_beat.refresh_from_db()
        self.assertEqual(gating_beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(
            BeatCompletion.objects.filter(
                beat=gating_beat, character_sheet=sheet, era=era
            ).exists()
        )

        # Act 3: Still not eligible — routing requires meeting_beat outcome.
        self.assertEqual(list(get_eligible_transitions(progress)), [])

        # Act 4: GM marks the meeting beat as SUCCESS.
        record_gm_marked_outcome(
            progress=progress,
            beat=meeting_beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Crucible handled the Herald with grace.",
        )

        # Act 5: Transition to 2A is now eligible (not 2B).
        eligible = list(get_eligible_transitions(progress))
        self.assertEqual(eligible, [t_to_2a])

        # Act 6: Resolve the episode.
        resolution = resolve_episode(progress=progress)

        # Assert: Progress advanced, audit trail intact.
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, ep_2a)
        self.assertEqual(resolution.chosen_transition, t_to_2a)
        self.assertEqual(resolution.era, era)
        self.assertEqual(resolution.character_sheet, sheet)

        # Audit: 2 BeatCompletion rows (gating + meeting), 1 EpisodeResolution.
        self.assertEqual(
            BeatCompletion.objects.filter(character_sheet=sheet).count(), 2
        )
        self.assertEqual(
            EpisodeResolution.objects.filter(character_sheet=sheet).count(), 1
        )
```

**Step 2: Run + fix until green**

Run: `arx test world.stories.tests.test_integration_phase1 --keepdb`
Expected: PASS.

**Step 3: Run full regression**

Run: `arx test world.stories world.character_creation world.gm world.roster world.societies --keepdb`
Expected: all PASS. Fix any regression in callers that use Story.

**Step 4: Run once WITHOUT --keepdb**

Run: `echo "yes" | uv run arx test world.stories`
Expected: PASS. This matches CI's fresh-DB behavior.

**Step 5: Commit**

```bash
git add src/world/stories/tests/test_integration_phase1.py
git commit -m "test(stories): add Phase 1 end-to-end integration test"
```

---

## Task 15: Update roadmap + Phase 2 preview + final commit

**Files:**
- Modify: `docs/roadmap/stories-gm.md` — mark Phase 1 foundation complete, add Phase 2 preview
- Modify: `docs/systems/stories.md` — update to reflect new models (or mark as needs-regen)
- Run: `uv run python tools/introspect_models.py` to regenerate `docs/systems/MODEL_MAP.md`

**Step 1: Update `docs/roadmap/stories-gm.md`**

Add under "What Exists":
- Phase 1 backend foundation: Era, extended Story (CHARACTER scope), Chapter/Episode restructure, Beat with discriminator predicate types, Transition with routing requirements, StoryProgress per-character progress, BeatCompletion + EpisodeResolution audit ledgers, services for beat evaluation / transition eligibility / episode resolution, end-to-end integration test.

Add under "What's Needed for MVP" (rephrase as Phase 2 and onward):
- **Phase 2 (next):** Basic REST API and player dashboard — viewsets for Story, StoryProgress, Beat, Transition (read-only for players, CRUD for Lead GMs); story log query with visibility filtering; Lead GM "episodes ready to run" dashboard view; player "active stories" list.
- **Phase 3+:** GROUP and GLOBAL scopes; additional beat predicate types (mission, achievement, aggregate, cross-story reference, codex); deadlines and expiry; AGM queue; Events system scheduling integration; staff workload dashboard; authoring UX.

**Step 2: Regenerate model map**

Run: `uv run python tools/introspect_models.py`
This updates `docs/systems/MODEL_MAP.md`.

**Step 3: Update `docs/systems/stories.md`**

Rewrite to reflect the Phase 1 model inventory. Include:
- Era, Story (with new fields), Chapter, Episode, Beat, Transition, TransitionRequiredOutcome, EpisodeProgressionRequirement, BeatCompletion, EpisodeResolution, StoryProgress
- Service layer: beats.py, transitions.py, episodes.py
- Exception hierarchy
- What's still in place from pre-Phase-1: trust system, StoryParticipation, feedback models (orthogonal; unchanged)

**Step 4: Final regression**

Run: `echo "yes" | uv run arx test` (full suite, no --keepdb)
Expected: PASS.

**Step 5: Commit + open PR**

```bash
git add docs/roadmap/stories-gm.md docs/systems/stories.md docs/systems/MODEL_MAP.md
git commit -m "docs(stories): update roadmap and systems index for Phase 1"
```

Then push and open PR via GitHub web (no `gh` CLI per CLAUDE.md).

---

## Execution Notes

- **Order dependencies:**
  - Tasks 5 and 6 are interlocked (Task 5 tests need Task 6's BeatFactory). Implement Task 6 first, then Task 5's tests can pass — or run Task 5's test file after Task 6 is done.
  - Tasks 11–13 build on all model tasks — don't start them until 1–10 are green.
  - Task 14 is the keystone — if it fails, something earlier is wrong.
- **Commit cadence:** commit after every task. Don't batch.
- **Test cadence:** run targeted tests per task (`arx test world.stories.tests.test_X --keepdb`). Run broader regression before Task 14, and a full fresh-DB run before Task 15.
- **Pre-commit hooks:** if a hook fails, fix and re-stage — do not use `--no-verify`.
- **Migration order:** accumulate migrations across tasks. Each task's `makemigrations` should produce one migration file. At the end of the phase, there should be ~8-10 new migration files in `src/world/stories/migrations/` on top of the existing `0002`.
- **If a helper is missing (e.g., `_set_character_level`):** stop and ask before stubbing or mocking. Progression's public API must be used correctly.
