# RP Interactions & Privacy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Interaction model, privacy architecture, and scene modifications that
enable automatic RP recording with four-tier privacy, so players can reference interactions
for relationship updates.

**Architecture:** Interactions are atomic RP records (one writer, one audience, one content)
that exist independently of Scenes. Scenes are explicit containers with a privacy mode.
Privacy is enforced via two fields: `Scene.privacy_mode` (public/private/ephemeral) and
`Interaction.visibility` (default/very_private). The audience M2M is the visibility ceiling.
RelationshipUpdate gains interaction/scene reference fields.

**Tech Stack:** Django + DRF, SharedMemoryModel, FactoryBoy, PostgreSQL (partitioning
deferred to a later task when volume warrants it — schema is partition-ready but we won't
add DDL complexity until needed).

**Design doc:** `docs/plans/2026-03-19-rp-interactions-privacy-design.md`

**Key conventions (from CLAUDE.md):**
- All models use `SharedMemoryModel` (import from `evennia.utils.idmapper.models`)
- All functions require type annotations (scenes is in typed apps list)
- TextChoices go in `constants.py`
- Absolute imports only
- No JSON fields, no signals, no relative imports
- Tests use FactoryBoy + `setUpTestData` where possible
- Run tests: `echo "yes" | arx test scenes` (pipes "yes" for DB creation prompt)
- Run lint: `ruff check <file>`

---

## Task 1: Add New Constants

**Files:**
- Modify: `src/world/scenes/constants.py`

**Step 1: Add InteractionMode, InteractionVisibility, ScenePrivacyMode, SummaryAction constants**

Add to `src/world/scenes/constants.py`:

```python
class InteractionMode(models.TextChoices):
    """The type of IC interaction."""

    POSE = "pose", "Pose"
    EMIT = "emit", "Emit"
    SAY = "say", "Say"
    WHISPER = "whisper", "Whisper"
    SHOUT = "shout", "Shout"
    ACTION = "action", "Action"


class InteractionVisibility(models.TextChoices):
    """Per-interaction privacy override. Can only escalate, never reduce."""

    DEFAULT = "default", "Default"
    VERY_PRIVATE = "very_private", "Very Private"


class ScenePrivacyMode(models.TextChoices):
    """Scene-level privacy floor. Ephemeral is immutable after creation."""

    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
    EPHEMERAL = "ephemeral", "Ephemeral"


class SummaryAction(models.TextChoices):
    """Actions in the collaborative ephemeral scene summary flow."""

    SUBMIT = "submit", "Submit"
    EDIT = "edit", "Edit"
    AGREE = "agree", "Agree"


class SummaryStatus(models.TextChoices):
    """Status of an ephemeral scene's collaborative summary."""

    DRAFT = "draft", "Draft"
    PENDING_REVIEW = "pending_review", "Pending Review"
    AGREED = "agreed", "Agreed"
```

**Step 2: Run lint**

Run: `ruff check src/world/scenes/constants.py`
Expected: PASS (no errors)

**Step 3: Commit**

```bash
git add src/world/scenes/constants.py
git commit -m "feat(scenes): add interaction and privacy constants"
```

---

## Task 2: Add Interaction Model

**Files:**
- Modify: `src/world/scenes/models.py`
- Test: `src/world/scenes/tests/test_models.py` (create new)

**Step 1: Write failing test for Interaction creation**

Create `src/world/scenes/tests/test_models.py`:

```python
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.models import Interaction


class InteractionModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_create_interaction(self) -> None:
        """An interaction can be created with required fields."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="tests her blade against the training dummy.",
            mode=InteractionMode.POSE,
        )
        assert interaction.pk is not None
        assert interaction.visibility == InteractionVisibility.DEFAULT
        assert interaction.scene is None
        assert interaction.persona is None
        assert interaction.sequence_number is not None

    def test_interaction_sequence_auto_increments(self) -> None:
        """Sequence numbers auto-increment per location."""
        i1 = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="First pose.",
            mode=InteractionMode.POSE,
        )
        i2 = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="Second pose.",
            mode=InteractionMode.POSE,
        )
        assert i2.sequence_number > i1.sequence_number
```

**Step 2: Run test to verify it fails**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: FAIL — `Interaction` model does not exist

**Step 3: Implement Interaction model**

Add to `src/world/scenes/models.py` (after the existing imports, add the new constant imports;
add the model after SceneMessageReaction):

```python
from world.scenes.constants import InteractionMode, InteractionVisibility

class Interaction(SharedMemoryModel):
    """An atomic IC interaction — one writer, one piece of content, one audience.

    Created automatically whenever a character poses, emits, says, whispers,
    shouts, or takes a mechanical action. The universal building block of RP
    recording. Scenes are optional containers; interactions exist independently.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="interactions_written",
        help_text="The IC identity who wrote this interaction",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="interactions_written",
        help_text="The specific player — privacy binds to roster entry, not character",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions_written",
        help_text="Disguise/alt identity if active during this interaction",
    )
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="interactions_at",
        help_text="Where this interaction happened",
    )
    scene = models.ForeignKey(
        Scene,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Scene container if one was active",
    )
    target_personas = models.ManyToManyField(
        Persona,
        blank=True,
        related_name="interactions_targeted",
        help_text="Explicit IC targets for thread derivation",
    )
    content = models.TextField(
        help_text="The actual written text of the interaction",
    )
    mode = models.CharField(
        max_length=20,
        choices=InteractionMode.choices,
        default=InteractionMode.POSE,
        help_text="The type of IC interaction",
    )
    visibility = models.CharField(
        max_length=20,
        choices=InteractionVisibility.choices,
        default=InteractionVisibility.DEFAULT,
        help_text="Privacy override — can only escalate, never reduce",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    sequence_number = models.PositiveIntegerField(
        help_text="Ordering within a location for chronological display",
    )

    class Meta:
        ordering = ["timestamp", "sequence_number"]
        indexes = [
            models.Index(fields=["character", "timestamp"]),
            models.Index(fields=["location", "timestamp"]),
            models.Index(fields=["scene", "sequence_number"]),
        ]

    def __str__(self) -> str:
        content_preview = str(self.content)[:50]
        return f"{self.character}: {content_preview}..."

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.sequence_number:
            max_seq = Interaction.objects.filter(location=self.location).aggregate(
                max_seq=Max("sequence_number"),
            )["max_seq"]
            self.sequence_number = (max_seq + 1) if max_seq else 1
        super().save(*args, **kwargs)
```

**Step 4: Run test to verify it passes**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: PASS

**Step 5: Run lint**

Run: `ruff check src/world/scenes/models.py`
Expected: PASS

**Step 6: Commit**

```bash
git add src/world/scenes/models.py src/world/scenes/tests/test_models.py
git commit -m "feat(scenes): add Interaction model with auto-sequencing"
```

---

## Task 3: Add InteractionAudience Model

**Files:**
- Modify: `src/world/scenes/models.py`
- Modify: `src/world/scenes/tests/test_models.py`

**Step 1: Write failing test**

Add to `test_models.py`:

```python
from world.scenes.models import Interaction, InteractionAudience


class InteractionAudienceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character=cls.other_character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_audience_records_who_saw_interaction(self) -> None:
        """InteractionAudience captures exactly who could see an interaction."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="waves to the room.",
            mode=InteractionMode.POSE,
        )
        audience = InteractionAudience.objects.create(
            interaction=interaction,
            roster_entry=self.other_roster_entry,
        )
        assert audience.pk is not None
        assert interaction.audience.count() == 1

    def test_audience_unique_per_interaction(self) -> None:
        """Same roster entry cannot be in audience twice for one interaction."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="waves again.",
            mode=InteractionMode.POSE,
        )
        InteractionAudience.objects.create(
            interaction=interaction,
            roster_entry=self.other_roster_entry,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            InteractionAudience.objects.create(
                interaction=interaction,
                roster_entry=self.other_roster_entry,
            )
```

**Step 2: Run test to verify it fails**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: FAIL — `InteractionAudience` does not exist

**Step 3: Implement InteractionAudience model**

Add to `src/world/scenes/models.py` after Interaction:

```python
class InteractionAudience(SharedMemoryModel):
    """Captures exactly who could see an interaction at creation time.

    This is the visibility ceiling — it can only shrink, never expand.
    All player-facing surfaces display the persona, never the roster entry.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="audience",
        help_text="The interaction this audience record belongs to",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="interactions_witnessed",
        help_text="The specific player who saw this interaction",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions_witnessed",
        help_text="The IC identity they were presenting as when they saw it",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "roster_entry"],
                name="unique_audience_per_interaction",
            ),
        ]
        indexes = [
            models.Index(fields=["roster_entry", "interaction"]),
        ]

    def __str__(self) -> str:
        name = self.persona.name if self.persona else str(self.roster_entry)
        return f"{name} witnessed interaction {self.interaction_id}"
```

Also add `audience_entries` M2M on Interaction (through InteractionAudience) — actually, the
`audience` related_name on InteractionAudience already gives us `interaction.audience.all()`,
which is cleaner than a through M2M. No additional field needed on Interaction.

**Step 4: Run test to verify it passes**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: PASS

**Step 5: Commit**

```bash
git add src/world/scenes/models.py src/world/scenes/tests/test_models.py
git commit -m "feat(scenes): add InteractionAudience model"
```

---

## Task 4: Add InteractionFavorite Model

**Files:**
- Modify: `src/world/scenes/models.py`
- Modify: `src/world/scenes/tests/test_models.py`

**Step 1: Write failing test**

Add to `test_models.py`:

```python
from world.scenes.models import InteractionFavorite


class InteractionFavoriteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_favorite_interaction(self) -> None:
        """A player can bookmark an interaction as a favorite."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="says something memorable.",
            mode=InteractionMode.SAY,
        )
        fav = InteractionFavorite.objects.create(
            interaction=interaction,
            roster_entry=self.roster_entry,
        )
        assert fav.pk is not None
        assert interaction.favorites.count() == 1

    def test_favorite_unique_per_player(self) -> None:
        """Same player cannot favorite the same interaction twice."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="another memorable moment.",
            mode=InteractionMode.SAY,
        )
        InteractionFavorite.objects.create(
            interaction=interaction,
            roster_entry=self.roster_entry,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            InteractionFavorite.objects.create(
                interaction=interaction,
                roster_entry=self.roster_entry,
            )
```

**Step 2: Run test to verify it fails**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: FAIL

**Step 3: Implement InteractionFavorite model**

Add to `src/world/scenes/models.py`:

```python
class InteractionFavorite(SharedMemoryModel):
    """Private bookmark for a cherished RP moment.

    Purely private — no other player sees what you bookmarked. Social feedback
    (kudos, pose voting, reactions) is handled by separate systems.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="favorites",
        help_text="The bookmarked interaction",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="favorited_interactions",
        help_text="The player who bookmarked this",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "roster_entry"],
                name="unique_favorite_per_interaction",
            ),
        ]

    def __str__(self) -> str:
        return f"Favorite: interaction {self.interaction_id} by {self.roster_entry}"
```

**Step 4: Run tests, lint, commit**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: PASS

```bash
git add src/world/scenes/models.py src/world/scenes/tests/test_models.py
git commit -m "feat(scenes): add InteractionFavorite model"
```

---

## Task 5: Modify Scene Model — Privacy Mode & Summary

**Files:**
- Modify: `src/world/scenes/models.py`
- Modify: `src/world/scenes/factories.py`
- Modify: `src/world/scenes/tests/test_models.py`

**Step 1: Write failing test**

Add to `test_models.py`:

```python
from world.scenes.constants import ScenePrivacyMode, SummaryStatus
from world.scenes.models import Scene


class ScenePrivacyTestCase(TestCase):
    def test_scene_default_privacy_is_public(self) -> None:
        """New scenes default to public privacy mode."""
        scene = SceneFactory()
        assert scene.privacy_mode == ScenePrivacyMode.PUBLIC

    def test_ephemeral_scene_has_summary_fields(self) -> None:
        """Ephemeral scenes can have a summary with status tracking."""
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        scene.summary = "We discussed the rebellion plans."
        scene.summary_status = SummaryStatus.DRAFT
        scene.save()
        scene.refresh_from_db()
        assert scene.summary == "We discussed the rebellion plans."
        assert scene.summary_status == SummaryStatus.DRAFT
```

**Step 2: Run test to verify it fails**

Run: `echo "yes" | arx test scenes.tests.test_models`
Expected: FAIL — `privacy_mode` field does not exist

**Step 3: Modify Scene model**

In `src/world/scenes/models.py`, modify the Scene class:

1. Add imports for `ScenePrivacyMode` and `SummaryStatus`
2. Remove `is_public` field
3. Add `privacy_mode`, `summary`, `summary_status` fields:

```python
# Replace is_public with:
privacy_mode = models.CharField(
    max_length=20,
    choices=ScenePrivacyMode.choices,
    default=ScenePrivacyMode.PUBLIC,
    help_text="Privacy floor for all interactions in this scene",
)
summary = models.TextField(
    blank=True,
    help_text="Scene summary — required for ephemeral scenes, optional for others",
)
summary_status = models.CharField(
    max_length=20,
    choices=SummaryStatus.choices,
    default=SummaryStatus.DRAFT,
    blank=True,
    help_text="Status of collaborative summary (mainly for ephemeral scenes)",
)
```

4. Add convenience property:

```python
@property
def is_public(self) -> bool:
    """Backwards-compatible check — scene is public if privacy mode is PUBLIC."""
    return self.privacy_mode == ScenePrivacyMode.PUBLIC

@property
def is_ephemeral(self) -> bool:
    """Whether this scene is ephemeral (content never stored)."""
    return self.privacy_mode == ScenePrivacyMode.EPHEMERAL
```

**Step 4: Update SceneFactory**

In `src/world/scenes/factories.py`, replace `is_public = True` with:

```python
privacy_mode = ScenePrivacyMode.PUBLIC
```

Add import: `from world.scenes.constants import ..., ScenePrivacyMode`

**Step 5: Fix existing tests that reference `is_public`**

Search for `is_public` in scene tests and update:
- Filter tests using `is_public=True` → `privacy_mode=ScenePrivacyMode.PUBLIC`
- Filter tests using `is_public=False` → `privacy_mode=ScenePrivacyMode.PRIVATE`
- Any serializer assertions checking for `is_public` field

Check: `src/world/scenes/tests/test_views.py`, `src/world/scenes/filters.py`,
`src/world/scenes/serializers.py`, `src/world/scenes/views.py`

**Step 6: Update SceneFilter**

In `src/world/scenes/filters.py`, replace `is_public` BooleanFilter with
`privacy_mode` CharFilter:

```python
privacy_mode = django_filters.CharFilter(field_name="privacy_mode")
```

**Step 7: Update serializers**

Replace `is_public` with `privacy_mode` in serializer fields lists.

**Step 8: Update views**

In `src/world/scenes/views.py`, update `get_queryset` to filter on `privacy_mode`
instead of `is_public`.

**Step 9: Run all scene tests**

Run: `echo "yes" | arx test scenes`
Expected: PASS (all existing tests updated)

**Step 10: Run lint on all changed files**

Run: `ruff check src/world/scenes/`
Expected: PASS

**Step 11: Commit**

```bash
git add src/world/scenes/
git commit -m "feat(scenes): replace is_public with privacy_mode, add summary fields"
```

---

## Task 6: Add SceneSummaryRevision Model

**Files:**
- Modify: `src/world/scenes/models.py`
- Modify: `src/world/scenes/tests/test_models.py`

**Step 1: Write failing test**

```python
from world.scenes.constants import SummaryAction
from world.scenes.models import SceneSummaryRevision


class SceneSummaryRevisionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        cls.participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.account
        )
        cls.persona = PersonaFactory(
            participation=cls.participation,
            character=CharacterFactory(),
        )

    def test_create_summary_revision(self) -> None:
        """A persona can submit a summary revision for an ephemeral scene."""
        revision = SceneSummaryRevision.objects.create(
            scene=self.scene,
            persona=self.persona,
            content="We plotted the overthrow of the tyrant.",
            action=SummaryAction.SUBMIT,
        )
        assert revision.pk is not None
        assert revision.scene == self.scene
        assert self.scene.summary_revisions.count() == 1

    def test_revision_shows_persona_not_account(self) -> None:
        """Revision str uses persona name, not account."""
        revision = SceneSummaryRevision.objects.create(
            scene=self.scene,
            persona=self.persona,
            content="Summary text.",
            action=SummaryAction.SUBMIT,
        )
        assert self.persona.name in str(revision)
```

**Step 2: Run test to verify it fails**

**Step 3: Implement SceneSummaryRevision**

Add to `src/world/scenes/models.py`:

```python
class SceneSummaryRevision(SharedMemoryModel):
    """A revision in the collaborative summary editing flow for ephemeral scenes.

    All author references use Persona (IC identity), never Account. Players
    editing a summary see 'Revised by The Masked Baron', not 'Revised by steve_2847'.
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="summary_revisions",
        help_text="The ephemeral scene this revision belongs to",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="summary_revisions",
        help_text="Who submitted this revision (IC identity, never account)",
    )
    content = models.TextField(
        help_text="The summary text for this revision",
    )
    action = models.CharField(
        max_length=20,
        choices=SummaryAction.choices,
        help_text="Whether this is a submission, edit, or agreement",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"{self.persona.name} {self.action} summary for {self.scene.name}"
```

**Step 4: Run tests, lint, commit**

```bash
git add src/world/scenes/models.py src/world/scenes/tests/test_models.py
git commit -m "feat(scenes): add SceneSummaryRevision model"
```

---

## Task 7: Generate Migration

**Important:** Since this is development and there's no production data, generate a single
migration covering all model changes from Tasks 2-6.

**Step 1: Generate migration**

Run: `arx manage makemigrations scenes`

**Step 2: Verify migration looks correct**

Read the generated migration file and confirm it includes:
- CreateModel for Interaction, InteractionAudience, InteractionFavorite, SceneSummaryRevision
- RemoveField is_public from Scene
- AddField privacy_mode, summary, summary_status to Scene

**Step 3: Apply migration**

Run: `arx manage migrate scenes`

**Step 4: Run all scene tests to verify**

Run: `echo "yes" | arx test scenes`
Expected: PASS

**Step 5: Commit**

```bash
git add src/world/scenes/migrations/
git commit -m "feat(scenes): add migration for interaction models and scene privacy"
```

---

## Task 8: Add Interaction Factories

**Files:**
- Modify: `src/world/scenes/factories.py`

**Step 1: Add factories**

```python
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    SceneSummaryRevision,
)


class InteractionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Interaction

    character = factory.SubFactory(CharacterFactory)
    roster_entry = factory.LazyAttribute(
        lambda o: RosterEntryFactory(character=o.character)
    )
    location = factory.SubFactory(
        ObjectDBFactory,
        db_key=factory.Sequence(lambda n: f"room-{n}"),
        db_typeclass_path="typeclasses.rooms.Room",
    )
    content = factory.Faker("text", max_nb_chars=500)
    mode = InteractionMode.POSE
    visibility = InteractionVisibility.DEFAULT
    timestamp = factory.LazyFunction(timezone.now)


class InteractionAudienceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionAudience


class InteractionFavoriteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionFavorite
```

Add needed imports: `from world.roster.factories import RosterEntryFactory` and
`from evennia_extensions.factories import ..., ObjectDBFactory`.

**Step 2: Verify factory works in a test**

Add to `test_models.py`:

```python
from world.scenes.factories import InteractionFactory


class InteractionFactoryTestCase(TestCase):
    def test_factory_creates_valid_interaction(self) -> None:
        """InteractionFactory creates a valid interaction with all required relations."""
        interaction = InteractionFactory()
        assert interaction.pk is not None
        assert interaction.character is not None
        assert interaction.roster_entry is not None
        assert interaction.location is not None
```

**Step 3: Run tests, lint, commit**

```bash
git add src/world/scenes/factories.py src/world/scenes/tests/test_models.py
git commit -m "feat(scenes): add Interaction factories"
```

---

## Task 9: Interaction Creation Service

**Files:**
- Create: `src/world/scenes/services/interaction_service.py` (or add to existing services.py)
- Create: `src/world/scenes/tests/test_interaction_service.py`

**Decision:** Create a `services/` package since the existing `services.py` is scene-broadcast
specific. Move it to `services/scene_service.py` and add `services/interaction_service.py`.

Actually — to minimize churn, keep existing `services.py` as-is and create
`src/world/scenes/interaction_services.py` alongside it.

**Step 1: Write failing test for create_interaction**

Create `src/world/scenes/tests/test_interaction_service.py`:

```python
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory, PersonaFactory
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, InteractionAudience


class CreateInteractionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character=cls.other_character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_create_interaction_basic(self) -> None:
        """create_interaction creates an Interaction with audience records."""
        interaction = create_interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="draws her sword dramatically.",
            mode=InteractionMode.POSE,
            audience_roster_entries=[self.other_roster_entry],
        )
        assert interaction.pk is not None
        assert interaction.mode == InteractionMode.POSE
        assert interaction.visibility == InteractionVisibility.DEFAULT
        assert InteractionAudience.objects.filter(interaction=interaction).count() == 1

    def test_create_interaction_with_scene(self) -> None:
        """Interaction auto-links to active scene at location."""
        scene = SceneFactory(location=self.location)
        interaction = create_interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="poses in the scene.",
            mode=InteractionMode.POSE,
            audience_roster_entries=[self.other_roster_entry],
            scene=scene,
        )
        assert interaction.scene == scene

    def test_create_interaction_ephemeral_scene_not_stored(self) -> None:
        """Interactions in ephemeral scenes are not persisted to the database."""
        scene = SceneFactory(
            location=self.location,
            privacy_mode=ScenePrivacyMode.EPHEMERAL,
        )
        interaction = create_interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="secret discussion.",
            mode=InteractionMode.POSE,
            audience_roster_entries=[self.other_roster_entry],
            scene=scene,
        )
        # For ephemeral scenes, create_interaction returns None
        assert interaction is None
        assert Interaction.objects.count() == 0

    def test_create_interaction_with_persona(self) -> None:
        """Interaction records the persona when one is active."""
        scene = SceneFactory(location=self.location)
        participation = SceneParticipationFactory(
            scene=scene, account=self.character.account,
        )
        persona = PersonaFactory(
            participation=participation, character=self.character,
        )
        interaction = create_interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="acts mysteriously.",
            mode=InteractionMode.POSE,
            audience_roster_entries=[self.other_roster_entry],
            scene=scene,
            persona=persona,
        )
        assert interaction.persona == persona

    def test_create_interaction_with_targets(self) -> None:
        """Interaction records explicit targets for thread derivation."""
        scene = SceneFactory(location=self.location)
        participation = SceneParticipationFactory(
            scene=scene, account=self.other_character.account,
        )
        target_persona = PersonaFactory(
            participation=participation, character=self.other_character,
        )
        interaction = create_interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="whispers to the stranger.",
            mode=InteractionMode.WHISPER,
            audience_roster_entries=[self.other_roster_entry],
            target_personas=[target_persona],
        )
        assert list(interaction.target_personas.all()) == [target_persona]
```

**Step 2: Run test to verify it fails**

Run: `echo "yes" | arx test scenes.tests.test_interaction_service`
Expected: FAIL — `interaction_services` module does not exist

**Step 3: Implement create_interaction**

Create `src/world/scenes/interaction_services.py`:

```python
from __future__ import annotations

from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    Persona,
    Scene,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB
    from world.roster.models import RosterEntry


def create_interaction(
    *,
    character: ObjectDB,
    roster_entry: RosterEntry,
    location: ObjectDB,
    content: str,
    mode: str,
    audience_roster_entries: list[RosterEntry],
    scene: Scene | None = None,
    persona: Persona | None = None,
    target_personas: list[Persona] | None = None,
    audience_personas: dict[int, Persona] | None = None,
) -> Interaction | None:
    """Create an atomic RP interaction with audience records.

    For ephemeral scenes, returns None without persisting anything —
    the interaction is delivered in real-time but never stored.

    Args:
        character: The IC identity who wrote this interaction.
        roster_entry: The specific player (privacy binds here).
        location: Where this interaction happened.
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, etc.).
        audience_roster_entries: Roster entries who can see this interaction.
        scene: Scene container if one was active.
        persona: Disguise/alt identity if active.
        target_personas: Explicit IC targets for thread derivation.
        audience_personas: Map of roster_entry PK → Persona for audience members.

    Returns:
        The created Interaction, or None for ephemeral scenes.
    """
    # Ephemeral scenes: never store content
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        return None

    interaction = Interaction.objects.create(
        character=character,
        roster_entry=roster_entry,
        location=location,
        content=content,
        mode=mode,
        scene=scene,
        persona=persona,
    )

    # Record audience
    audience_persona_map = audience_personas or {}
    audience_records = [
        InteractionAudience(
            interaction=interaction,
            roster_entry=re,
            persona=audience_persona_map.get(re.pk),
        )
        for re in audience_roster_entries
    ]
    InteractionAudience.objects.bulk_create(audience_records)

    # Record targets
    if target_personas:
        interaction.target_personas.set(target_personas)

    return interaction
```

Add `from __future__ import annotations` and `from typing import TYPE_CHECKING` at top.

**Step 4: Run tests**

Run: `echo "yes" | arx test scenes.tests.test_interaction_service`
Expected: PASS

**Step 5: Lint and commit**

```bash
git add src/world/scenes/interaction_services.py src/world/scenes/tests/test_interaction_service.py
git commit -m "feat(scenes): add create_interaction service function"
```

---

## Task 10: Interaction Visibility & Deletion Services

**Files:**
- Modify: `src/world/scenes/interaction_services.py`
- Create: `src/world/scenes/tests/test_visibility_service.py`

**Step 1: Write failing tests for visibility checks**

Create `src/world/scenes/tests/test_visibility_service.py`:

```python
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.interaction_services import (
    can_view_interaction,
    delete_interaction,
    mark_very_private,
)
from world.scenes.models import Interaction, InteractionAudience


class CanViewInteractionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_character = CharacterFactory()
        cls.writer_re = RosterEntryFactory(character=cls.writer_character)
        cls.audience_character = CharacterFactory()
        cls.audience_re = RosterEntryFactory(character=cls.audience_character)
        cls.outsider_character = CharacterFactory()
        cls.outsider_re = RosterEntryFactory(character=cls.outsider_character)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def _create_interaction_with_audience(
        self, visibility=InteractionVisibility.DEFAULT, scene=None,
    ):
        interaction = Interaction.objects.create(
            character=self.writer_character,
            roster_entry=self.writer_re,
            location=self.location,
            content="test content",
            mode=InteractionMode.POSE,
            visibility=visibility,
            scene=scene,
        )
        InteractionAudience.objects.create(
            interaction=interaction,
            roster_entry=self.audience_re,
        )
        return interaction

    def test_audience_can_view_default(self) -> None:
        """Audience members can view default visibility interactions."""
        interaction = self._create_interaction_with_audience()
        assert can_view_interaction(interaction, self.audience_re) is True

    def test_outsider_cannot_view_private_scene(self) -> None:
        """Non-audience members cannot view interactions in private scenes."""
        scene = SceneFactory(
            location=self.location,
            privacy_mode=ScenePrivacyMode.PRIVATE,
        )
        interaction = self._create_interaction_with_audience(scene=scene)
        assert can_view_interaction(interaction, self.outsider_re) is False

    def test_staff_can_view_private_scene(self) -> None:
        """Staff can view interactions in private scenes."""
        scene = SceneFactory(
            location=self.location,
            privacy_mode=ScenePrivacyMode.PRIVATE,
        )
        interaction = self._create_interaction_with_audience(scene=scene)
        assert can_view_interaction(
            interaction, self.outsider_re, is_staff=True,
        ) is True

    def test_staff_cannot_view_very_private(self) -> None:
        """Staff CANNOT view very_private interactions — hard trust guarantee."""
        interaction = self._create_interaction_with_audience(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(
            interaction, self.outsider_re, is_staff=True,
        ) is False

    def test_audience_can_view_very_private(self) -> None:
        """Original audience members CAN view very_private interactions."""
        interaction = self._create_interaction_with_audience(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.audience_re) is True


class MarkVeryPrivateTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_mark_very_private(self) -> None:
        """An audience member can mark an interaction as very_private."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="intimate moment.",
            mode=InteractionMode.POSE,
        )
        InteractionAudience.objects.create(
            interaction=interaction,
            roster_entry=self.roster_entry,
        )
        mark_very_private(interaction, self.roster_entry)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE


class DeleteInteractionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_delete_own_recent_interaction(self) -> None:
        """Writer can delete their own interaction within 30 days."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="oops wrong room.",
            mode=InteractionMode.POSE,
        )
        result = delete_interaction(interaction, self.roster_entry)
        assert result is True
        assert Interaction.objects.filter(pk=interaction.pk).count() == 0

    def test_cannot_delete_other_persons_interaction(self) -> None:
        """Cannot delete an interaction you didn't write."""
        other_re = RosterEntryFactory(character=CharacterFactory())
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="someone else wrote this.",
            mode=InteractionMode.POSE,
        )
        result = delete_interaction(interaction, other_re)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()

    def test_cannot_delete_old_interaction(self) -> None:
        """Cannot delete an interaction older than 30 days."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="ancient history.",
            mode=InteractionMode.POSE,
        )
        # Manually backdate the timestamp
        old_time = timezone.now() - timedelta(days=31)
        Interaction.objects.filter(pk=interaction.pk).update(timestamp=old_time)
        interaction.refresh_from_db()
        result = delete_interaction(interaction, self.roster_entry)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()
```

**Step 2: Run tests to verify they fail**

**Step 3: Implement visibility and deletion functions**

Add to `src/world/scenes/interaction_services.py`:

```python
from datetime import timedelta

from django.utils import timezone

from world.scenes.constants import InteractionVisibility, ScenePrivacyMode

# Deletion window in days
DELETION_WINDOW_DAYS = 30


def can_view_interaction(
    interaction: Interaction,
    roster_entry: RosterEntry,
    *,
    is_staff: bool = False,
) -> bool:
    """Check if a roster entry can view an interaction.

    Visibility cascade:
    1. very_private → only original audience roster entries (not staff)
    2. Private scene → audience + staff
    3. Default → audience for audience-scoped, public for public scenes

    Args:
        interaction: The interaction to check visibility for.
        roster_entry: The roster entry requesting access.
        is_staff: Whether the requesting user is staff.

    Returns:
        True if the roster entry can view the interaction content.
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction, roster_entry=roster_entry,
    ).exists()
    is_writer = interaction.roster_entry_id == roster_entry.pk

    # Very private: only original audience and writer, never staff
    if interaction.visibility == InteractionVisibility.VERY_PRIVATE:
        return is_audience or is_writer

    # Staff can see everything except very_private
    if is_staff:
        return True

    # Private scene: audience + staff only
    scene = interaction.scene
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        return is_audience or is_writer

    # Default in public scene or no scene: check audience scope
    # If there's an audience at all, you must be in it
    if InteractionAudience.objects.filter(interaction=interaction).exists():
        # Public scene interactions are globally viewable
        if scene is not None and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
            return True
        # No scene = organic grid RP, audience-scoped for non-public modes
        if interaction.mode in (InteractionMode.WHISPER, InteractionMode.SAY):
            return is_audience or is_writer
        # Default pose/emit without a scene = public
        return True

    # No audience records at all (edge case) — writer can always see their own
    return is_writer


def mark_very_private(
    interaction: Interaction,
    roster_entry: RosterEntry,
) -> None:
    """Mark an interaction as very_private.

    Any audience member can escalate. This is a one-way operation —
    cannot be reverted to default.

    Args:
        interaction: The interaction to mark.
        roster_entry: The roster entry requesting the change (must be in audience).
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction, roster_entry=roster_entry,
    ).exists()
    is_writer = interaction.roster_entry_id == roster_entry.pk

    if not (is_audience or is_writer):
        return

    interaction.visibility = InteractionVisibility.VERY_PRIVATE
    interaction.save(update_fields=["visibility"])


def delete_interaction(
    interaction: Interaction,
    roster_entry: RosterEntry,
) -> bool:
    """Hard-delete an interaction if the requester is the writer and within the window.

    Args:
        interaction: The interaction to delete.
        roster_entry: The roster entry requesting deletion (must be writer).

    Returns:
        True if deleted, False if not allowed.
    """
    # Must be the writer
    if interaction.roster_entry_id != roster_entry.pk:
        return False

    # Check time window
    age = timezone.now() - interaction.timestamp
    if age > timedelta(days=DELETION_WINDOW_DAYS):
        return False

    interaction.delete()
    return True
```

**Step 4: Run tests, lint, commit**

```bash
git add src/world/scenes/interaction_services.py src/world/scenes/tests/test_visibility_service.py
git commit -m "feat(scenes): add visibility checks and deletion for interactions"
```

---

## Task 11: Interaction Serializers

**Files:**
- Create: `src/world/scenes/interaction_serializers.py`
- Test via API in Task 13

**Step 1: Create serializers**

Create `src/world/scenes/interaction_serializers.py`:

```python
from __future__ import annotations

from rest_framework import serializers

from world.scenes.models import Interaction, InteractionAudience, InteractionFavorite


class InteractionAudienceSerializer(serializers.ModelSerializer):
    """Audience member — shows persona name, never account/roster entry."""

    persona_name = serializers.CharField(source="persona.name", default=None)
    persona_id = serializers.IntegerField(source="persona.id", default=None)

    class Meta:
        model = InteractionAudience
        fields = ["id", "persona_name", "persona_id"]


class InteractionListSerializer(serializers.ModelSerializer):
    """Lightweight interaction for list views and feeds."""

    persona_name = serializers.CharField(source="persona.name", default=None)
    character_name = serializers.CharField(source="character.db_key", read_only=True)
    target_persona_names = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "character_name",
            "persona_name",
            "location",
            "scene",
            "content",
            "mode",
            "visibility",
            "timestamp",
            "sequence_number",
            "target_persona_names",
            "is_favorited",
        ]

    def get_target_persona_names(self, obj: Interaction) -> list[str]:
        try:
            return [p.name for p in obj.cached_target_personas]
        except AttributeError:
            return [p.name for p in obj.target_personas.all()]

    def get_is_favorited(self, obj: Interaction) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        roster_entry = getattr(request.user, "roster_entry", None)
        if roster_entry is None:
            return False
        try:
            return any(
                f.roster_entry_id == roster_entry.pk for f in obj.cached_favorites
            )
        except AttributeError:
            return InteractionFavorite.objects.filter(
                interaction=obj, roster_entry=roster_entry,
            ).exists()


class InteractionDetailSerializer(InteractionListSerializer):
    """Full interaction with audience details."""

    audience = InteractionAudienceSerializer(many=True, read_only=True)

    class Meta(InteractionListSerializer.Meta):
        fields = [*InteractionListSerializer.Meta.fields, "audience"]


class InteractionFavoriteSerializer(serializers.ModelSerializer):
    """Toggle favorite on an interaction."""

    class Meta:
        model = InteractionFavorite
        fields = ["id", "interaction", "created_at"]
        read_only_fields = ["created_at"]
```

Note: Add `cached_target_personas` and `cached_favorites` cached properties to the
Interaction model to support `Prefetch(to_attr=)`:

```python
# In Interaction model
@property
def cached_target_personas(self) -> list[Persona]:
    try:
        return self._cached_target_personas
    except AttributeError:
        return list(self.target_personas.all())

@cached_target_personas.setter
def cached_target_personas(self, value: list[Persona]) -> None:
    self._cached_target_personas = value

@property
def cached_favorites(self) -> list[InteractionFavorite]:
    try:
        return self._cached_favorites
    except AttributeError:
        return list(self.favorites.all())

@cached_favorites.setter
def cached_favorites(self, value: list[InteractionFavorite]) -> None:
    self._cached_favorites = value
```

**Step 2: Lint and commit**

```bash
git add src/world/scenes/interaction_serializers.py src/world/scenes/models.py
git commit -m "feat(scenes): add interaction serializers and cached properties"
```

---

## Task 12: Interaction Permissions & Filters

**Files:**
- Create: `src/world/scenes/interaction_permissions.py`
- Create: `src/world/scenes/interaction_filters.py`

**Step 1: Create permissions**

Create `src/world/scenes/interaction_permissions.py`:

```python
from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from world.scenes.interaction_services import can_view_interaction


class CanViewInteraction(BasePermission):
    """Check if the requesting user can view the interaction content."""

    def has_object_permission(self, request: Request, view, obj) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        character = getattr(user, "character", None)
        if character is None:
            return False
        roster_entry = getattr(character, "roster_entry", None)
        if roster_entry is None:
            return False
        return can_view_interaction(obj, roster_entry, is_staff=user.is_staff)


class IsInteractionWriter(BasePermission):
    """Only the writer of an interaction can modify/delete it."""

    def has_object_permission(self, request: Request, view, obj) -> bool:
        user = request.user
        if user.is_staff:
            return True
        character = getattr(user, "character", None)
        if character is None:
            return False
        roster_entry = getattr(character, "roster_entry", None)
        if roster_entry is None:
            return False
        return obj.roster_entry_id == roster_entry.pk
```

**Step 2: Create filters**

Create `src/world/scenes/interaction_filters.py`:

```python
from __future__ import annotations

import django_filters

from world.scenes.models import Interaction


class InteractionFilter(django_filters.FilterSet):
    """Filter interactions by character, location, scene, mode, and time range."""

    character = django_filters.NumberFilter(field_name="character_id")
    location = django_filters.NumberFilter(field_name="location_id")
    scene = django_filters.NumberFilter(field_name="scene_id")
    mode = django_filters.CharFilter(field_name="mode")
    visibility = django_filters.CharFilter(field_name="visibility")
    since = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")
    target_persona = django_filters.NumberFilter(
        field_name="target_personas", lookup_expr="exact",
    )

    class Meta:
        model = Interaction
        fields = ["character", "location", "scene", "mode", "visibility"]
```

**Step 3: Lint and commit**

```bash
git add src/world/scenes/interaction_permissions.py src/world/scenes/interaction_filters.py
git commit -m "feat(scenes): add interaction permissions and filters"
```

---

## Task 13: Interaction ViewSet & URL Registration

**Files:**
- Create: `src/world/scenes/interaction_views.py`
- Modify: `src/world/scenes/urls.py`
- Create: `src/world/scenes/tests/test_interaction_views.py`

**Step 1: Write failing test**

Create `src/world/scenes/tests/test_interaction_views.py`:

```python
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import InteractionFactory
from world.scenes.models import Interaction, InteractionAudience, InteractionFavorite


class InteractionViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory(account=cls.account)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.location = ObjectDBFactory(
            db_key="tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # Create some interactions
        cls.interaction = Interaction.objects.create(
            character=cls.character,
            roster_entry=cls.roster_entry,
            location=cls.location,
            content="draws her sword.",
            mode=InteractionMode.POSE,
        )
        InteractionAudience.objects.create(
            interaction=cls.interaction,
            roster_entry=cls.roster_entry,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_list_interactions(self) -> None:
        """Authenticated user can list interactions they're audience to."""
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_filter_by_character(self) -> None:
        """Can filter interactions by character."""
        url = reverse("interaction-list")
        response = self.client.get(url, {"character": self.character.pk})
        assert response.status_code == status.HTTP_200_OK

    def test_favorite_interaction(self) -> None:
        """Can toggle favorite on an interaction."""
        url = reverse("interactionfavorite-list")
        response = self.client.post(
            url,
            {"interaction": self.interaction.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert InteractionFavorite.objects.filter(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        ).exists()

    def test_delete_own_interaction(self) -> None:
        """Writer can delete their own recent interaction."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="oops.",
            mode=InteractionMode.POSE,
        )
        url = reverse("interaction-detail", args=[interaction.pk])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Interaction.objects.filter(pk=interaction.pk).exists()

    @suppress_permission_errors
    def test_cannot_delete_others_interaction(self) -> None:
        """Cannot delete someone else's interaction."""
        other_character = CharacterFactory()
        other_re = RosterEntryFactory(character=other_character)
        interaction = Interaction.objects.create(
            character=other_character,
            roster_entry=other_re,
            location=self.location,
            content="not yours.",
            mode=InteractionMode.POSE,
        )
        url = reverse("interaction-detail", args=[interaction.pk])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_mark_very_private(self) -> None:
        """Audience member can mark interaction as very_private."""
        url = reverse("interaction-mark-private", args=[self.interaction.pk])
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        self.interaction.refresh_from_db()
        assert self.interaction.visibility == InteractionVisibility.VERY_PRIVATE
```

**Step 2: Run test to verify it fails**

**Step 3: Implement InteractionViewSet**

Create `src/world/scenes/interaction_views.py`:

```python
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.interaction_filters import InteractionFilter
from world.scenes.interaction_permissions import CanViewInteraction, IsInteractionWriter
from world.scenes.interaction_serializers import (
    InteractionDetailSerializer,
    InteractionFavoriteSerializer,
    InteractionListSerializer,
)
from world.scenes.interaction_services import delete_interaction, mark_very_private
from world.scenes.models import Interaction, InteractionAudience, InteractionFavorite, Persona
from django.db.models import Prefetch


class InteractionCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-timestamp"


class InteractionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for browsing interactions.

    Interactions are created by the game flow (pose/emit/say commands), not
    via API POST. This viewset provides browsing, filtering, deletion, and
    privacy marking.
    """

    filterset_class = InteractionFilter
    pagination_class = InteractionCursorPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Interaction.objects.select_related(
                "character", "roster_entry", "persona", "location", "scene",
            )
            .prefetch_related(
                Prefetch("audience", to_attr="cached_audience"),
                Prefetch("target_personas", to_attr="cached_target_personas"),
                Prefetch("favorites", to_attr="cached_favorites"),
            )
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return InteractionDetailSerializer
        return InteractionListSerializer

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAuthenticated(), IsInteractionWriter()]
        if self.action == "retrieve":
            return [IsAuthenticated(), CanViewInteraction()]
        return super().get_permissions()

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Hard-delete an interaction (writer only, within 30 days)."""
        interaction = self.get_object()
        roster_entry = request.user.character.roster_entry
        if not delete_interaction(interaction, roster_entry):
            return Response(
                {"detail": "Cannot delete: interaction is older than 30 days."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_name="mark-private")
    def mark_private(self, request: Request, pk=None) -> Response:
        """Mark an interaction as very_private."""
        interaction = self.get_object()
        roster_entry = request.user.character.roster_entry
        mark_very_private(interaction, roster_entry)
        return Response({"status": "marked as very private"})


class InteractionFavoriteViewSet(viewsets.ModelViewSet):
    """Toggle favorites on interactions."""

    serializer_class = InteractionFavoriteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "delete", "get"]

    def get_queryset(self):
        user = self.request.user
        character = getattr(user, "character", None)
        if character is None:
            return InteractionFavorite.objects.none()
        roster_entry = getattr(character, "roster_entry", None)
        if roster_entry is None:
            return InteractionFavorite.objects.none()
        return InteractionFavorite.objects.filter(roster_entry=roster_entry)

    def perform_create(self, serializer) -> None:
        roster_entry = self.request.user.character.roster_entry
        serializer.save(roster_entry=roster_entry)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Toggle: create if not exists, delete if exists."""
        roster_entry = request.user.character.roster_entry
        interaction_id = request.data.get("interaction")
        existing = InteractionFavorite.objects.filter(
            interaction_id=interaction_id,
            roster_entry=roster_entry,
        ).first()
        if existing:
            existing.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return super().create(request, *args, **kwargs)
```

**Step 4: Register URLs**

Add to `src/world/scenes/urls.py`:

```python
from world.scenes.interaction_views import InteractionFavoriteViewSet, InteractionViewSet

router.register(r"interactions", InteractionViewSet, basename="interaction")
router.register(r"interaction-favorites", InteractionFavoriteViewSet, basename="interactionfavorite")
```

**Step 5: Run tests**

Run: `echo "yes" | arx test scenes.tests.test_interaction_views`
Expected: PASS

**Step 6: Run all scene tests to check for regressions**

Run: `echo "yes" | arx test scenes`
Expected: PASS

**Step 7: Commit**

```bash
git add src/world/scenes/interaction_views.py src/world/scenes/urls.py src/world/scenes/tests/test_interaction_views.py
git commit -m "feat(scenes): add interaction viewset, favorites, and URL registration"
```

---

## Task 14: Scene Summary Revision API

**Files:**
- Modify: `src/world/scenes/serializers.py` (or create new serializer file)
- Modify: `src/world/scenes/views.py`
- Modify: `src/world/scenes/urls.py`
- Create: `src/world/scenes/tests/test_summary_views.py`

**Step 1: Write failing test**

Create `src/world/scenes/tests/test_summary_views.py`:

```python
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.scenes.constants import ScenePrivacyMode, SummaryAction, SummaryStatus
from world.scenes.factories import (
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import SceneSummaryRevision


class SceneSummaryRevisionTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory(account=cls.account)
        cls.scene = SceneFactory(
            privacy_mode=ScenePrivacyMode.EPHEMERAL,
            is_active=False,
        )
        cls.participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.account,
        )
        cls.persona = PersonaFactory(
            participation=cls.participation,
            character=cls.character,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_submit_summary(self) -> None:
        """Participant can submit a summary for an ephemeral scene."""
        url = reverse("scenesummaryrevision-list")
        response = self.client.post(url, {
            "scene": self.scene.pk,
            "persona": self.persona.pk,
            "content": "We discussed the alliance terms.",
            "action": SummaryAction.SUBMIT,
        }, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert SceneSummaryRevision.objects.count() == 1

    def test_agree_to_summary(self) -> None:
        """Participant can agree to a summary."""
        SceneSummaryRevision.objects.create(
            scene=self.scene,
            persona=self.persona,
            content="Initial summary.",
            action=SummaryAction.SUBMIT,
        )
        # Another participant agrees
        other_account = AccountFactory()
        other_character = CharacterFactory(account=other_account)
        other_part = SceneParticipationFactory(
            scene=self.scene, account=other_account,
        )
        other_persona = PersonaFactory(
            participation=other_part, character=other_character,
        )
        self.client.force_authenticate(user=other_account)
        url = reverse("scenesummaryrevision-list")
        response = self.client.post(url, {
            "scene": self.scene.pk,
            "persona": other_persona.pk,
            "content": "Initial summary.",
            "action": SummaryAction.AGREE,
        }, format="json")
        assert response.status_code == status.HTTP_201_CREATED
```

**Step 2: Implement summary serializer and viewset**

Add `SceneSummaryRevisionSerializer` and `SceneSummaryRevisionViewSet`, register in URLs.
The serializer validates that the persona belongs to a participant of the scene and that the
scene is ephemeral.

**Step 3: Run tests, lint, commit**

```bash
git add src/world/scenes/
git commit -m "feat(scenes): add scene summary revision API for ephemeral scenes"
```

---

## Task 15: Relationship Update — Add Interaction Reference Fields

**Files:**
- Modify: `src/world/relationships/constants.py`
- Modify: `src/world/relationships/models.py`
- Generate migration: `arx manage makemigrations relationships`
- Modify: `src/world/relationships/tests/` (add test for new fields)

**Step 1: Add ReferenceMode constant**

Add to `src/world/relationships/constants.py`:

```python
class ReferenceMode(models.TextChoices):
    """How a relationship update references RP."""

    ALL_WEEKLY = "all_weekly", "All Interactions This Week"
    SPECIFIC_INTERACTION = "specific_interaction", "Specific Interaction"
    SPECIFIC_SCENE = "specific_scene", "Specific Scene"
```

**Step 2: Add fields to RelationshipUpdate**

In `src/world/relationships/models.py`, add to RelationshipUpdate:

```python
linked_interaction = models.ForeignKey(
    "scenes.Interaction",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    help_text="Specific interaction this update references",
)
reference_mode = models.CharField(
    max_length=30,
    choices=ReferenceMode.choices,
    default=ReferenceMode.ALL_WEEKLY,
    help_text="How this update references RP",
)
```

Add import: `from world.relationships.constants import ..., ReferenceMode`

**Step 3: Generate and apply migration**

Run: `arx manage makemigrations relationships`
Run: `arx manage migrate relationships`

**Step 4: Write test**

```python
def test_relationship_update_with_interaction_reference(self) -> None:
    """A relationship update can reference a specific interaction."""
    update = RelationshipUpdate.objects.create(
        relationship=self.relationship,
        author=self.source_sheet,
        title="That moment in the tavern",
        writeup="When she drew her sword, everything changed.",
        track=self.trust_track,
        points_earned=5,
        reference_mode=ReferenceMode.SPECIFIC_INTERACTION,
        linked_interaction=self.interaction,
    )
    assert update.linked_interaction == self.interaction
    assert update.reference_mode == ReferenceMode.SPECIFIC_INTERACTION
```

**Step 5: Run tests, lint, commit**

```bash
git add src/world/relationships/
git commit -m "feat(relationships): add interaction reference fields to RelationshipUpdate"
```

---

## Task 16: Admin Registration

**Files:**
- Modify: `src/world/scenes/admin.py`

**Step 1: Register new models in admin**

Add admin registrations for Interaction, InteractionAudience, InteractionFavorite,
and SceneSummaryRevision. Include InteractionAudience as an inline on InteractionAdmin.

```python
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    SceneSummaryRevision,
)


class InteractionAudienceInline(admin.TabularInline):
    model = InteractionAudience
    extra = 0


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ["character", "mode", "visibility", "location", "timestamp"]
    list_filter = ["mode", "visibility"]
    search_fields = ["content"]
    inlines = [InteractionAudienceInline]


@admin.register(InteractionFavorite)
class InteractionFavoriteAdmin(admin.ModelAdmin):
    list_display = ["interaction", "roster_entry", "created_at"]


@admin.register(SceneSummaryRevision)
class SceneSummaryRevisionAdmin(admin.ModelAdmin):
    list_display = ["scene", "persona", "action", "timestamp"]
    list_filter = ["action"]
```

Also update SceneAdmin to show `privacy_mode` instead of `is_public`.

**Step 2: Lint and commit**

```bash
git add src/world/scenes/admin.py
git commit -m "feat(scenes): register interaction models in admin"
```

---

## Task 17: Final Integration — Run All Tests

**Step 1: Run full scene test suite**

Run: `echo "yes" | arx test scenes`
Expected: PASS — all new and existing tests pass

**Step 2: Run relationship tests**

Run: `echo "yes" | arx test relationships`
Expected: PASS

**Step 3: Run lint on all changed files**

Run: `ruff check src/world/scenes/ src/world/relationships/`
Expected: PASS

**Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix(scenes): test and lint fixes for interaction system"
```

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | Constants | `scenes/constants.py` |
| 2 | Interaction model | `scenes/models.py` |
| 3 | InteractionAudience model | `scenes/models.py` |
| 4 | InteractionFavorite model | `scenes/models.py` |
| 5 | Scene privacy_mode changes | `scenes/models.py`, factories, views, filters, serializers |
| 6 | SceneSummaryRevision model | `scenes/models.py` |
| 7 | Migration | `scenes/migrations/` |
| 8 | Factories | `scenes/factories.py` |
| 9 | create_interaction service | `scenes/interaction_services.py` |
| 10 | Visibility & deletion services | `scenes/interaction_services.py` |
| 11 | Serializers | `scenes/interaction_serializers.py` |
| 12 | Permissions & filters | `scenes/interaction_permissions.py`, `interaction_filters.py` |
| 13 | ViewSet & URLs | `scenes/interaction_views.py`, `scenes/urls.py` |
| 14 | Summary revision API | `scenes/views.py` or new file |
| 15 | RelationshipUpdate fields | `relationships/constants.py`, `relationships/models.py` |
| 16 | Admin registration | `scenes/admin.py` |
| 17 | Integration test pass | All tests green |

### Not in this plan (deferred)

- **PostgreSQL partitioning** — Schema is partition-ready (timestamp indexed, sequence numbers).
  Add partition DDL when volume warrants it, not at model creation time.
- **Communication flow integration** — Wiring `message_location()` to call `create_interaction()`
  instead of/alongside SceneMessage creation. This requires careful coordination with the
  existing Evennia action system and should be its own task.
- **SceneMessage deprecation** — Once Interactions are the universal record, SceneMessage becomes
  redundant. Migration plan needed when communication flow is updated.
- **Frontend components** — All frontend work for interaction feeds, threading UI, favorites,
  privacy controls, and relationship reference browsing.
- **Ephemeral real-time delivery** — WebSocket/Evennia msg() integration for delivering
  interactions that are never persisted.
