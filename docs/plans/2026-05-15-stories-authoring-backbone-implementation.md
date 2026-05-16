# Stories Authoring Backbone — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make "author a story and walk a player to its frontier" real and testable — the runnable backbone from `docs/plans/2026-05-15-stories-authoring-framework-design.md` §3–§9, with every richer beat resolving via the existing GM-mark path until its dedicated engine lands.

**Architecture:** Extend the existing `world.stories` app *in place*. Add metadata fields (`Beat.kind/advances/risk`, per-node `maturity`, `Episode.resting_conclusion/is_ending`, `Progress.status`), one `StoryNote` model, a risk trust-gate in the existing `BeatSerializer.validate()`, a new `services/frontier.py` that sets `Progress.status` to `WAITING_FOR_GM`/`RESTING`, and a scope-assignment guard. No existing machinery (`BeatCompletion`, `Transition`, `EpisodeProgressionRequirement`, reactivity, narrative) is reshaped. Resolution of Situation/Encounter/Task beats continues to flow through the existing predicate path (default `GM_MARKED` → `record_gm_marked_outcome`).

**Tech Stack:** Django + Evennia (`SharedMemoryModel`), DRF, factory_boy, Postgres. Tests via `arx test`. App is type-checked — **every new function needs full type annotations**.

---

## Conventions for the executing engineer

- **Never work on `main`.** This plan is executed on branch `feature/stories-authoring-framework-design` (already created; the design + this plan are committed there).
- **No `cd &&` compounds** (Windows permission mitigation). Use `git -C C:/Users/apost/PycharmProjects/arxii <cmd>`.
- **Run tests via `just`/`arx`.** Targeted dev run: `just test world.stories.tests.test_x -k name --keepdb`. Fresh-DB run (matches CI, required before completion): `echo "yes" | uv run arx test world.stories` (no `--keepdb`).
- **Migrations:** `uv run arx manage makemigrations stories` then `uv run arx manage migrate`. Task 2 batches *all* schema changes into **one** migration — do not run `makemigrations` until every model edit in Task 2 is in place.
- **Lint after editing Python:** `ruff check <file>` and `ruff format <file>`.
- **TextChoices live in `constants.py`** (project rule). `StoryStatus`/`StoryPrivacy` already live in `types.py` — leave them; add *new* choices to `constants.py`.
- **No `Meta.ordering`** on `StoryNote` — order in the viewset queryset instead.
- Commit after every task with the message shown in that task's final step.

Relevant skills: @superpowers:test-driven-development, @superpowers:verification-before-completion.

---

## Task 1: Add the new enums

**Files:**
- Modify: `src/world/stories/constants.py`
- Test: `src/world/stories/tests/test_constants_backbone.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_constants_backbone.py
from django.test import SimpleTestCase

from world.stories.constants import BeatKind, ProgressStatus, StoryMaturity, StoryScope


class BackboneConstantsTests(SimpleTestCase):
    def test_story_scope_has_unassigned(self):
        self.assertEqual(StoryScope.UNASSIGNED, "unassigned")
        self.assertIn(StoryScope.UNASSIGNED, StoryScope.values)

    def test_story_maturity_members(self):
        self.assertEqual(
            set(StoryMaturity.values), {"pitch", "outline", "plot"}
        )

    def test_beat_kind_members(self):
        self.assertEqual(
            set(BeatKind.values),
            {"situation", "encounter", "task", "requirement"},
        )

    def test_progress_status_members(self):
        self.assertEqual(
            set(ProgressStatus.values),
            {"active", "waiting_for_gm", "resting", "completed"},
        )
```

**Step 2: Run test to verify it fails**

Run: `just test world.stories.tests.test_constants_backbone --keepdb`
Expected: FAIL — `ImportError: cannot import name 'BeatKind'`.

**Step 3: Implement**

In `src/world/stories/constants.py`, add `UNASSIGNED` to the existing `StoryScope` and append three new classes. `StoryScope` currently reads:

```python
class StoryScope(models.TextChoices):
    CHARACTER = "character", "Character"
    GROUP = "group", "Group"
    GLOBAL = "global", "Global"
```

Change it to:

```python
class StoryScope(models.TextChoices):
    UNASSIGNED = "unassigned", "Unassigned"
    CHARACTER = "character", "Personal"
    GROUP = "group", "Group"
    GLOBAL = "global", "Global"
```

Then append (anywhere after the imports, with the other choice classes):

```python
class StoryMaturity(models.TextChoices):
    """Authoring-completeness of a Story / Chapter / Episode node.

    Orthogonal to runtime StoryStatus. Per-node and fully independent — no
    cross-node ordering, parent/child, or DAG-reachability constraint.
    """

    PITCH = "pitch", "Pitch"
    OUTLINE = "outline", "Outline"
    PLOT = "plot", "Plot"


class BeatKind(models.TextChoices):
    """What a beat *is*. Resolution still flows through predicate_type."""

    SITUATION = "situation", "Situation"
    ENCOUNTER = "encounter", "Encounter"
    TASK = "task", "Task"
    REQUIREMENT = "requirement", "Requirement"


class ProgressStatus(models.TextChoices):
    """Finer-grained pointer state. is_active stays True for ACTIVE /
    WAITING_FOR_GM / RESTING; only COMPLETED sets is_active False."""

    ACTIVE = "active", "Active"
    WAITING_FOR_GM = "waiting_for_gm", "Waiting for GM"
    RESTING = "resting", "Resting"
    COMPLETED = "completed", "Completed"
```

**Step 4: Run test to verify it passes**

Run: `just test world.stories.tests.test_constants_backbone --keepdb`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/constants.py src/world/stories/tests/test_constants_backbone.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): add StoryScope.UNASSIGNED, StoryMaturity, BeatKind, ProgressStatus enums"
```

---

## Task 2: Model fields + StoryNote + one migration

All schema changes happen here so a single `makemigrations` produces one migration.

**Files:**
- Modify: `src/world/stories/models.py`
- Create: `src/world/stories/migrations/0028_*.py` (generated)
- Test: `src/world/stories/tests/test_backbone_models.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_backbone_models.py
from django.test import TestCase

from world.stories.constants import (
    BeatKind,
    ProgressStatus,
    StoryMaturity,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import Story, StoryNote


class BackboneModelDefaultsTests(TestCase):
    def test_new_story_defaults_unassigned_and_pitch(self):
        story = Story.objects.create(title="t", description="d")
        self.assertEqual(story.scope, StoryScope.UNASSIGNED)
        self.assertEqual(story.maturity, StoryMaturity.PITCH)

    def test_chapter_and_episode_default_pitch(self):
        episode = EpisodeFactory()
        self.assertEqual(episode.maturity, StoryMaturity.PITCH)
        self.assertEqual(episode.chapter.maturity, StoryMaturity.PITCH)
        self.assertEqual(episode.resting_conclusion, "")
        self.assertFalse(episode.is_ending)

    def test_beat_backbone_field_defaults(self):
        beat = BeatFactory()
        self.assertEqual(beat.kind, BeatKind.TASK)
        self.assertTrue(beat.advances)
        self.assertEqual(beat.risk, 0)

    def test_progress_status_defaults_active(self):
        progress = StoryProgressFactory()
        self.assertEqual(progress.status, ProgressStatus.ACTIVE)
        self.assertTrue(progress.is_active)

    def test_story_note_is_append_record(self):
        story = StoryFactory()
        note = StoryNote.objects.create(story=story, body="future idea")
        self.assertEqual(note.story, story)
        self.assertIsNotNone(note.created_at)
        self.assertIsNone(note.author_account)
```

**Step 2: Run test to verify it fails**

Run: `just test world.stories.tests.test_backbone_models --keepdb`
Expected: FAIL — `cannot import name 'StoryNote'` / attribute errors.

**Step 3: Implement model changes**

In `src/world/stories/models.py`:

1. Extend the constants import block to include the new enums:

```python
from world.stories.constants import (
    AssistantClaimStatus,
    BeatKind,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    EraStatus,
    ProgressStatus,
    SessionRequestStatus,
    StoryGMOfferStatus,
    StoryMaturity,
    StoryMilestoneType,
    StoryScope,
    TransitionMode,
)
```

2. **`Story`** — change the `scope` default and add `maturity`. Find the `scope = models.CharField(...)` line and replace its default; add `maturity` next to it:

```python
    scope = models.CharField(
        max_length=20,
        choices=StoryScope.choices,
        default=StoryScope.UNASSIGNED,
    )
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
    )
```

3. **`Chapter`** — add after `is_active`:

```python
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
    )
```

4. **`Episode`** — add after `is_active`:

```python
    maturity = models.CharField(
        max_length=10,
        choices=StoryMaturity.choices,
        default=StoryMaturity.PITCH,
    )
    resting_conclusion = models.TextField(
        blank=True,
        help_text=(
            "Player-facing text shown when progress RESTS at this episode "
            "(no chosen transition). Required before PLOT promotion."
        ),
    )
    is_ending = models.BooleanField(
        default=False,
        help_text="Explicit 'this is an ending' marker; satisfies PLOT "
        "promotion when there is no outbound transition.",
    )
```

5. **`Beat`** — add after `order`:

```python
    kind = models.CharField(
        max_length=12,
        choices=BeatKind.choices,
        default=BeatKind.TASK,
    )
    advances = models.BooleanField(
        default=True,
        help_text="False = Tangent: recorded for history, never gates a "
        "transition.",
    )
    risk = models.PositiveSmallIntegerField(
        default=0,
        help_text="Plain risk number. Meaning/names assigned later with the "
        "consequence work. Authoring trust-gated in the serializer.",
    )
```

Do **not** add `kind`/`advances`/`risk` invariants to `Beat.clean()` — the backbone keeps `kind` orthogonal to `predicate_type`. Leave `clean()` untouched.

6. **`StoryProgress`, `GroupStoryProgress`, `GlobalStoryProgress`** — add to each (next to `is_active`):

```python
    status = models.CharField(
        max_length=16,
        choices=ProgressStatus.choices,
        default=ProgressStatus.ACTIVE,
    )
```

7. **New `StoryNote` model.** Add near `StoryProgress` (after the progress models is fine). `SharedMemoryModel`, no `Meta.ordering`:

```python
class StoryNote(SharedMemoryModel):
    """Append-only OOC authorial memory attached to a Story.

    General story notes + future-idea seeds. Distinct from per-node pitch
    text. Never player-visible. Not promotable — purely informational for
    the next author. No edit/delete in the API.
    """

    story = models.ForeignKey(
        Story, on_delete=models.CASCADE, related_name="notes"
    )
    author_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"StoryNote(story={self.story_id}, at={self.created_at})"
```

**Step 4: Generate and apply the migration**

Run:
```
uv run arx manage makemigrations stories
uv run arx manage migrate
```
Expected: one new migration `0028_...` adding `Story.maturity`, altering `Story.scope` default, adding `Chapter.maturity`, `Episode.maturity/resting_conclusion/is_ending`, `Beat.kind/advances/risk`, `status` on three progress models, and creating `StoryNote`. `migrate` applies cleanly.

**Step 5: Run test to verify it passes**

Run: `just test world.stories.tests.test_backbone_models --keepdb`
Expected: PASS (5 tests).

**Step 6: Guard against regressions from the scope-default change**

Run: `just test world.stories --keepdb`
Expected: PASS. If any test fails because it created a `Story` without an explicit `scope` and relied on the old `CHARACTER` default, fix that test to pass `scope=StoryScope.CHARACTER` explicitly (the new default is intentionally `UNASSIGNED`). Note each fixed test in the commit body.

**Step 7: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/models.py src/world/stories/migrations/0028_*.py src/world/stories/tests/test_backbone_models.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): backbone model fields (maturity, beat kind/advances/risk, progress status) + StoryNote"
```

---

## Task 3: Factories for the new surface

**Files:**
- Modify: `src/world/stories/factories.py`
- Test: covered by Task 2's test (factories already produce defaults); add a `StoryNoteFactory` smoke test in `test_backbone_models.py`.

**Step 1: Write the failing test** — append to `test_backbone_models.py`:

```python
    def test_story_note_factory(self):
        from world.stories.factories import StoryNoteFactory

        note = StoryNoteFactory()
        self.assertTrue(note.body)
        self.assertIsNotNone(note.story_id)
```

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_backbone_models -k story_note_factory --keepdb`
Expected: FAIL — `cannot import name 'StoryNoteFactory'`.

**Step 3: Implement** — in `src/world/stories/factories.py`, add (model is imported at top of that file alongside the others; add `StoryNote` to the existing `from world.stories.models import (...)` block):

```python
class StoryNoteFactory(factory_django.DjangoModelFactory):
    """Factory for StoryNote append records."""

    class Meta:
        model = StoryNote

    story = factory.SubFactory(StoryFactory)
    author_account = None
    body = factory.Faker("paragraph", nb_sentences=2)
```

Leave `BeatFactory`/`EpisodeFactory`/`StoryFactory` as-is — the new model fields have benign defaults, so existing factories stay valid. (`StoryFactory` still sets `scope=StoryScope.CHARACTER` explicitly, so it is unaffected by the default change.)

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_backbone_models -k story_note_factory --keepdb`
Expected: PASS.

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/factories.py src/world/stories/tests/test_backbone_models.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "test(stories): add StoryNoteFactory"
```

---

## Task 4: Beat serializer — expose new fields + risk trust gate

The risk gate: **staff → any risk; non-staff → `risk` must be 0** (PoC rule from design §8). Enforced in the existing `BeatSerializer.validate()`.

**Files:**
- Modify: `src/world/stories/serializers.py` (`BeatSerializer`, lines ~793–909)
- Test: `src/world/stories/tests/test_serializers_beat_risk.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_serializers_beat_risk.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.constants import BeatKind, BeatPredicateType
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory


class BeatRiskGateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.staff, cls.player])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _payload(self, risk):
        return {
            "episode": self.episode.pk,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "kind": BeatKind.SITUATION,
            "advances": True,
            "risk": risk,
            "internal_description": "x",
        }

    def test_non_staff_cannot_author_risk_above_zero(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("beat-list"), self._payload(2), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_non_staff_may_author_risk_zero(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("beat-list"), self._payload(0), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["kind"], BeatKind.SITUATION)

    def test_staff_may_author_any_risk(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("beat-list"), self._payload(5), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["risk"], 5)
```

> If `beat-list` POST is not permitted for a non-staff owner by the existing
> `BeatViewSet` permission classes, the first two tests will fail on
> permission (403) rather than validation (400/201). **Step 2.5** handles this.

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_serializers_beat_risk --keepdb`
Expected: FAIL — `kind`/`risk` not accepted; or 403.

**Step 2.5: Read the BeatViewSet permission classes**

Read `src/world/stories/views.py` (the `BeatViewSet`) and `src/world/stories/permissions.py`. Confirm whether a non-staff **story owner** can POST a beat. The design's authoring model is GM/owner-driven; for the PoC a story *owner* (GM) authoring beats is correct. If the existing write permission is staff-only, the non-staff test should instead assert that a **GM owner** is gated by *risk* (not blanket-denied). Adjust the test fixture so `cls.player` is a legitimate beat author per existing permissions (e.g., add them to `active_gms`/`owners` as the permission class requires) — do not loosen permissions. The goal is to test the *risk* gate, layered on top of existing auth, not to change auth.

**Step 3: Implement**

In `src/world/stories/serializers.py`, add the three fields to `BeatSerializer.Meta.fields` (after `"order"`):

```python
            "kind", "advances", "risk",
```

Extend the `existing` field-snapshot list inside `validate()` to include them (so PATCH merges keep them):

```python
                "required_points", "kind", "advances", "risk",
```

Then, at the **end** of `validate()` (after the `temp.clean()` block, before `return attrs`), add the risk gate:

```python
        request = self.context.get("request")
        merged_risk = merged.get("risk", 0) or 0
        user = getattr(request, "user", None)
        is_staff = bool(getattr(user, "is_staff", False))
        if merged_risk > 0 and not is_staff:
            raise serializers.ValidationError(
                {
                    "risk": (
                        "Only staff may author beats above risk 0. "
                        "Higher risk tiers unlock with GM trust level."
                    )
                }
            )
        return attrs
```

(The full trust→risk ladder replaces this single check when GM leveling lands — no schema change. Keep the message generic.)

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_serializers_beat_risk --keepdb`
Expected: PASS (3 tests). Also run `just test world.stories.tests.test_serializers_beat --keepdb` — existing serializer tests must still PASS.

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/serializers.py src/world/stories/tests/test_serializers_beat_risk.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): expose beat kind/advances/risk; staff-only risk>0 authoring gate"
```

---

## Task 5: Scope-assignment guard

An `UNASSIGNED` story cannot be run — no progress record may be created against it.

**Files:**
- Modify: `src/world/stories/exceptions.py` (add `StoryNotAssignedError`)
- Modify: `src/world/stories/services/progress.py` (`create_character_progress`, `create_group_progress`, and add a `create_global_progress` guard if that function exists; verify by reading the file)
- Test: `src/world/stories/tests/test_services_progress_scope_guard.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_services_progress_scope_guard.py
from django.test import TestCase

from world.stories.constants import StoryScope
from world.stories.exceptions import StoryNotAssignedError
from world.stories.factories import StoryFactory
from world.stories.services.progress import create_character_progress
from world.character_sheets.tests.factories import CharacterSheetFactory


class ScopeGuardTests(TestCase):
    def test_unassigned_story_rejects_character_progress(self):
        story = StoryFactory(scope=StoryScope.UNASSIGNED, character_sheet=None)
        sheet = CharacterSheetFactory()
        with self.assertRaises(StoryNotAssignedError):
            create_character_progress(story=story, character_sheet=sheet)
```

> Confirm the correct `CharacterSheet` factory import path by reading
> `src/world/stories/factories.py` (it imports a `CharacterSheetFactory`).
> Use that same import.

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_services_progress_scope_guard --keepdb`
Expected: FAIL — `cannot import name 'StoryNotAssignedError'`.

**Step 3: Implement**

Read `src/world/stories/exceptions.py` to match the `StoryError` base pattern (it has a `user_message` property). Add:

```python
class StoryNotAssignedError(StoryError):
    """Raised when creating progress against an UNASSIGNED-scope story."""

    user_message = (
        "This story has no scope assigned yet and cannot be run. "
        "Assign it to a character, group, or global scope first."
    )
```

(Match whatever `user_message` mechanism the base class actually uses — read it first; some `StoryError` subclasses set a class attribute, others a property.)

In `src/world/stories/services/progress.py`, at the top of `create_character_progress` and `create_group_progress` (and `create_global_progress` if present), before the `.objects.create(...)` call:

```python
    from world.stories.constants import StoryScope
    from world.stories.exceptions import StoryNotAssignedError

    if story.scope == StoryScope.UNASSIGNED:
        raise StoryNotAssignedError
```

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_services_progress_scope_guard --keepdb`
Expected: PASS. Run `just test world.stories.tests.test_services_progress --keepdb` — existing progress-service tests still PASS (they use scoped factories, not UNASSIGNED).

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/exceptions.py src/world/stories/services/progress.py src/world/stories/tests/test_services_progress_scope_guard.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): block progress creation on UNASSIGNED-scope stories"
```

---

## Task 6: Maturity-promotion validation service

Episode → PLOT requires `resting_conclusion` non-empty **and** (≥1 outbound transition **or** `is_ending`). Story/Chapter → PLOT have no extra content rule (design §5). Maturity is forward-leaning but not locked — staff/owner may demote freely (no validation on demotion).

**Files:**
- Create: `src/world/stories/services/maturity.py`
- Modify: `src/world/stories/exceptions.py` (add `MaturityPromotionError`)
- Test: `src/world/stories/tests/test_services_maturity.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_services_maturity.py
from django.test import TestCase

from world.stories.constants import StoryMaturity
from world.stories.exceptions import MaturityPromotionError
from world.stories.factories import EpisodeFactory, TransitionFactory
from world.stories.services.maturity import promote_episode_maturity


class EpisodeMaturityPromotionTests(TestCase):
    def test_plot_requires_resting_conclusion(self):
        ep = EpisodeFactory(resting_conclusion="", is_ending=True)
        with self.assertRaises(MaturityPromotionError):
            promote_episode_maturity(ep, StoryMaturity.PLOT)

    def test_plot_requires_transition_or_ending(self):
        ep = EpisodeFactory(resting_conclusion="It ends.", is_ending=False)
        with self.assertRaises(MaturityPromotionError):
            promote_episode_maturity(ep, StoryMaturity.PLOT)

    def test_plot_ok_with_conclusion_and_ending(self):
        ep = EpisodeFactory(resting_conclusion="It ends.", is_ending=True)
        promote_episode_maturity(ep, StoryMaturity.PLOT)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.PLOT)

    def test_plot_ok_with_conclusion_and_outbound_transition(self):
        ep = EpisodeFactory(resting_conclusion="More to come.")
        TransitionFactory(source_episode=ep)
        promote_episode_maturity(ep, StoryMaturity.PLOT)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.PLOT)

    def test_demotion_is_unvalidated(self):
        ep = EpisodeFactory(maturity=StoryMaturity.PLOT, resting_conclusion="")
        promote_episode_maturity(ep, StoryMaturity.OUTLINE)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.OUTLINE)
```

> Confirm `TransitionFactory`'s field name for the source episode by reading
> `src/world/stories/factories.py` (`TransitionFactory`) — it is
> `source_episode` per the model. Adjust if the factory uses a SubFactory
> default that conflicts.

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_services_maturity --keepdb`
Expected: FAIL — module/exception missing.

**Step 3: Implement**

Add to `exceptions.py` (match base pattern):

```python
class MaturityPromotionError(StoryError):
    """Raised when a node fails its maturity-promotion validation."""

    user_message = (
        "This episode is not ready to be promoted to Plot. It needs a "
        "resting conclusion and either an outbound transition or an "
        "explicit ending."
    )
```

Create `src/world/stories/services/maturity.py`:

```python
"""Maturity-promotion validation. Forward promotion is gated by minimal
per-node content rules; demotion is always allowed (non-linear sketchpad)."""

from world.stories.constants import StoryMaturity
from world.stories.exceptions import MaturityPromotionError
from world.stories.models import Episode

_RANK = {
    StoryMaturity.PITCH: 0,
    StoryMaturity.OUTLINE: 1,
    StoryMaturity.PLOT: 2,
}


def promote_episode_maturity(
    episode: Episode, target: StoryMaturity
) -> Episode:
    """Set episode.maturity to ``target``.

    Promotion to PLOT requires a non-empty resting_conclusion AND either an
    outbound transition or is_ending. Lateral moves and demotions are not
    validated. Returns the saved episode.
    """
    is_promotion = _RANK[target] > _RANK[StoryMaturity(episode.maturity)]
    if target == StoryMaturity.PLOT and is_promotion:
        if not episode.resting_conclusion.strip():
            raise MaturityPromotionError
        has_outbound = episode.outbound_transitions.exists()
        if not has_outbound and not episode.is_ending:
            raise MaturityPromotionError
    episode.maturity = target
    episode.save(update_fields=["maturity", "updated_at"])
    return episode
```

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_services_maturity --keepdb`
Expected: PASS (5 tests).

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/services/maturity.py src/world/stories/exceptions.py src/world/stories/tests/test_services_maturity.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): episode maturity-promotion validation (PLOT gate)"
```

---

## Task 7: Frontier service — WAITING_FOR_GM vs RESTING

When a player can't advance, decide the pointer state. Heuristic for the backbone: if there is **any** Episode in the story at PITCH/OUTLINE maturity (authored-but-unfinished content remaining) → `WAITING_FOR_GM`; otherwise → `RESTING`. (Per-DAG-reachability "ahead" detection is a noted follow-up; the design's intent is "more is intended → wait; nothing remains → ambiguous rest.")

**Files:**
- Create: `src/world/stories/services/frontier.py`
- Test: `src/world/stories/tests/test_services_frontier.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_services_frontier.py
from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryMaturity, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.frontier import resolve_frontier, set_progress_status


class FrontierTests(TestCase):
    def _story_with_episode(self, ep_maturity):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story)
        ep = EpisodeFactory(chapter=chapter, maturity=ep_maturity)
        progress = StoryProgressFactory(story=story, current_episode=ep)
        return story, ep, progress

    def test_resting_when_nothing_immature_remains(self):
        story, ep, progress = self._story_with_episode(StoryMaturity.PLOT)
        # Only a fully-plotted terminal episode, no transitions, no immature nodes.
        resolve_frontier(progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.RESTING)

    def test_waiting_for_gm_when_immature_content_remains(self):
        story, ep, progress = self._story_with_episode(StoryMaturity.PLOT)
        # A second, still-pitched episode exists somewhere in the story.
        ChapterFactory(story=story)  # immature chapter
        EpisodeFactory(
            chapter=story.chapters.first(), maturity=StoryMaturity.PITCH
        )
        resolve_frontier(progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.WAITING_FOR_GM)

    def test_set_progress_status_helper(self):
        _, _, progress = self._story_with_episode(StoryMaturity.PLOT)
        set_progress_status(progress, ProgressStatus.COMPLETED)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.COMPLETED)
        self.assertFalse(progress.is_active)
```

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_services_frontier --keepdb`
Expected: FAIL — module missing.

**Step 3: Implement**

Create `src/world/stories/services/frontier.py`:

```python
"""Frontier resolution: when a player can't advance, decide whether the
story is WAITING_FOR_GM (immature content remains) or RESTING (nothing
authored remains — deliberately ambiguous, never COMPLETED)."""

from world.stories.constants import ProgressStatus, StoryMaturity
from world.stories.models import Episode
from world.stories.types import AnyStoryProgress


def set_progress_status(
    progress: AnyStoryProgress, status: ProgressStatus
) -> None:
    """Set status on any progress type. COMPLETED also clears is_active;
    every other status keeps is_active True (the story is still live, just
    paused)."""
    progress.status = status
    progress.is_active = status != ProgressStatus.COMPLETED
    progress.save(update_fields=["status", "is_active", "last_advanced_at"])


def _story_has_immature_content(story_id: int) -> bool:
    """True if any Episode in the story is still PITCH/OUTLINE — i.e. the
    author intends more. Story-wide heuristic; per-DAG-reachability
    refinement is a documented follow-up."""
    return (
        Episode.objects.filter(chapter__story_id=story_id)
        .exclude(maturity=StoryMaturity.PLOT)
        .exists()
    )


def resolve_frontier(progress: AnyStoryProgress) -> None:
    """Set WAITING_FOR_GM or RESTING on a progress that has no way forward.

    Caller is responsible for only invoking this when the player genuinely
    cannot advance (no eligible transition / target below PLOT). Never sets
    COMPLETED — only an explicit staff/owner action does that.
    """
    story_id = progress.story_id
    if _story_has_immature_content(story_id):
        set_progress_status(progress, ProgressStatus.WAITING_FOR_GM)
    else:
        set_progress_status(progress, ProgressStatus.RESTING)
```

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_services_frontier --keepdb`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/services/frontier.py src/world/stories/tests/test_services_frontier.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): frontier resolution (WAITING_FOR_GM vs RESTING)"
```

---

## Task 8: Wire frontier + maturity into the runtime advance path

When an episode is resolved and there is no eligible onward transition, or the chosen/eligible target episode is below PLOT, the progress should land in `WAITING_FOR_GM`/`RESTING` via `resolve_frontier`.

**Files:**
- Read first: `src/world/stories/services/episodes.py` (`resolve_episode`), `src/world/stories/services/transitions.py` (`get_eligible_transitions`)
- Modify: `src/world/stories/services/episodes.py`
- Test: `src/world/stories/tests/test_frontier_wiring.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_frontier_wiring.py
from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryMaturity, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.episodes import resolve_episode


class FrontierWiringTests(TestCase):
    def test_resolving_terminal_plot_episode_rests(self):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story, maturity=StoryMaturity.PLOT)
        ep = EpisodeFactory(
            chapter=chapter,
            maturity=StoryMaturity.PLOT,
            resting_conclusion="It ends here.",
            is_ending=True,
        )
        progress = StoryProgressFactory(story=story, current_episode=ep)
        resolve_episode(progress=progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.RESTING)
```

> **Read `resolve_episode` first.** Its current signature is
> `resolve_episode(*, progress, chosen_transition=None, gm_notes="", resolved_by=None) -> EpisodeResolution`
> and it raises `NoEligibleTransitionError` / `AmbiguousTransitionError`.
> The terminal case (no outbound transitions, no progression requirements)
> is the "frontier pause" path in `get_eligible_transitions` (returns `[]`).
> Adjust the test's expectations to match how `resolve_episode` currently
> signals "nothing to advance to" — the wiring goal is: **on that
> terminal/frontier outcome, call `resolve_frontier(progress)` instead of
> leaving status ACTIVE.**

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_frontier_wiring --keepdb`
Expected: FAIL — status stays `ACTIVE` (no wiring yet) or an exception is raised that the test must handle.

**Step 3: Implement**

In `src/world/stories/services/episodes.py`, at the point where `resolve_episode` determines there is **no onward transition** (the frontier-pause branch — identify it from reading the function; it currently advances `current_episode` to `None` or leaves it), add, after the `EpisodeResolution` row is committed and progress is advanced:

```python
    from world.stories.services.frontier import resolve_frontier
    from world.stories.services.transitions import get_eligible_transitions

    # If there is no way forward (frontier pause), classify the pointer
    # state instead of leaving it ACTIVE.
    try:
        onward = get_eligible_transitions(progress)
    except Exception:  # ProgressionRequirementNotMetError → still ACTIVE/blocked
        onward = None
    if not onward:
        resolve_frontier(progress)
```

Place this so it runs on the terminal/frontier outcome **and not** when a real transition was chosen and the story is moving on. If `resolve_episode` raises on the terminal case rather than returning, wrap the wiring at the call sites that catch that exception instead — decide based on the actual control flow you read in Step 1, and document the chosen integration point in the commit body.

Also: when `resolve_episode` *does* move to a next episode whose `maturity` is below PLOT, call `resolve_frontier(progress)` as well (target not runnable yet). Add that check where the new `current_episode` is set:

```python
    if (
        progress.current_episode is not None
        and progress.current_episode.maturity != StoryMaturity.PLOT
    ):
        from world.stories.services.frontier import resolve_frontier

        resolve_frontier(progress)
```

(Import `StoryMaturity` at module top per the file's import style.)

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_frontier_wiring --keepdb`
Expected: PASS. Then run the full episodes-service suite — existing behavior must not regress:
Run: `just test world.stories.tests.test_services_episodes world.stories.tests.test_integration_phase1 --keepdb`
Expected: PASS. If an existing test asserted the old "stays ACTIVE at frontier" behavior, update it to expect the new status and note it in the commit body.

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/services/episodes.py src/world/stories/tests/test_frontier_wiring.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): wire frontier resolution into resolve_episode"
```

---

## Task 9: Surface WAITING_FOR_GM / RESTING in status line + dashboards

Players see deliberately-ambiguous copy; GM/staff dashboards show `WAITING_FOR_GM` with staleness age.

**Files:**
- Read first: `src/world/stories/services/dashboards.py` (`compute_story_status_line`), and the gm-queue / staff-workload view code in `src/world/stories/views.py`
- Modify: `src/world/stories/services/dashboards.py`
- Test: `src/world/stories/tests/test_status_line_backbone.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_status_line_backbone.py
from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.dashboards import compute_story_status_line


class StatusLineTests(TestCase):
    def _progress(self, status):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        ep = EpisodeFactory(chapter=ChapterFactory(story=story))
        p = StoryProgressFactory(
            story=story, current_episode=ep, status=status
        )
        return p

    def test_waiting_for_gm_copy_is_player_safe(self):
        line = compute_story_status_line(self._progress(ProgressStatus.WAITING_FOR_GM))
        self.assertTrue(line)
        # No alarming finality language.
        self.assertNotIn("over", line.lower())
        self.assertNotIn("done", line.lower())

    def test_resting_copy_is_ambiguous_not_final(self):
        line = compute_story_status_line(self._progress(ProgressStatus.RESTING))
        self.assertNotIn("complete", line.lower())
        self.assertNotIn("the end", line.lower())
```

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_status_line_backbone --keepdb`
Expected: FAIL — `compute_story_status_line` does not yet branch on the new statuses (assertions on copy fail or it errors on unknown status).

**Step 3: Implement**

Read `compute_story_status_line(progress)` and add explicit branches near the top:

```python
    from world.stories.constants import ProgressStatus

    if progress.status == ProgressStatus.WAITING_FOR_GM:
        return "The trail goes quiet — your GM has been notified. More to come."
    if progress.status == ProgressStatus.RESTING:
        return "The story rests here for now."
    if progress.status == ProgressStatus.COMPLETED:
        return "This story has reached its conclusion."
```

Then, in the gm-queue and staff-workload querysets/serializers (read `views.py` to find them), include progress rows with `status=WAITING_FOR_GM` and expose `last_advanced_at` as the staleness age so a dropped ball is visibly old. If those endpoints already order by staleness, just widen the filter to include `WAITING_FOR_GM`; add/extend a focused view test in `test_views_gm_queue.py` / `test_views_staff_workload.py` asserting a `WAITING_FOR_GM` story appears with its age. Keep changes minimal and additive.

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_status_line_backbone world.stories.tests.test_views_gm_queue world.stories.tests.test_views_staff_workload --keepdb`
Expected: PASS.

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/services/dashboards.py src/world/stories/views.py src/world/stories/tests/test_status_line_backbone.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): player-safe WAITING_FOR_GM/RESTING status copy + dashboard surfacing"
```

---

## Task 10: StoryNote API (list + create only — append-only)

GM/staff/owner can read and append; never player-visible; no edit/delete.

**Files:**
- Read first: `src/world/stories/serializers.py`, `views.py`, `urls.py`, `permissions.py` (match existing ViewSet + permission + router patterns)
- Modify: `serializers.py`, `views.py`, `urls.py`
- Test: `src/world/stories/tests/test_views_story_note.py` (create)

**Step 1: Write the failing test**

```python
# src/world/stories/tests/test_views_story_note.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.factories import StoryFactory, StoryNoteFactory


class StoryNoteApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        StoryNoteFactory(story=cls.story, body="seed idea")

    def test_staff_can_list_notes_for_story(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(
            reverse("storynote-list"), {"story": self.story.pk}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_can_append_note(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("storynote-list"),
            {"story": self.story.pk, "body": "later: betrayal arc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_notes_are_not_editable(self):
        self.client.force_authenticate(user=self.staff)
        note = StoryNoteFactory(story=self.story)
        resp = self.client.patch(
            reverse("storynote-detail", kwargs={"pk": note.pk}),
            {"body": "x"},
            format="json",
        )
        self.assertIn(
            resp.status_code,
            (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN),
        )
```

> The exact router basename (`storynote`) depends on how `urls.py`
> registers it — match the existing registration style and adjust the
> `reverse()` names if the router uses a different basename.

**Step 2: Run to verify it fails**

Run: `just test world.stories.tests.test_views_story_note --keepdb`
Expected: FAIL — no route.

**Step 3: Implement**

- `serializers.py`: add a `StoryNoteSerializer(serializers.ModelSerializer)` with fields `["id", "story", "author_account", "body", "created_at"]`, `read_only_fields = ["id", "author_account", "created_at"]`. Set `author_account` from `request.user` in `create()` (mirror how other serializers in this file resolve the request account).
- `views.py`: add a `StoryNoteViewSet` using **only** list/retrieve/create mixins (e.g. `mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet`) — no update/destroy, so PATCH/DELETE return 405. `queryset = StoryNote.objects.all().order_by("-created_at")` (ordering on the queryset, not the model). Add a FilterSet exposing `story` (project rule: FilterSets, not raw query params), and a permission class restricting to staff or story owners/active GMs (reuse the existing story-owner permission pattern from `permissions.py`). Never expose to plain players.
- `urls.py`: register `StoryNoteViewSet` with the existing router (basename `storynote`).

Follow the existing `@extend_schema` / pagination conventions used by the other viewsets in this app (see project memory: drf-spectacular recipe when a viewset is not a `ModelViewSet`; add `@extend_schema` + the paginated-response helper as the item-app viewsets demonstrate).

**Step 4: Run to verify it passes**

Run: `just test world.stories.tests.test_views_story_note --keepdb`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/serializers.py src/world/stories/views.py src/world/stories/urls.py src/world/stories/filters.py src/world/stories/permissions.py src/world/stories/tests/test_views_story_note.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): append-only StoryNote API (list/create, GM/staff only)"
```

---

## Task 11: Docs + MODEL_MAP

**Files:**
- Modify: `docs/systems/stories.md` (add the new fields/models/services to the relevant sections)
- Modify: `docs/systems/INDEX.md` (Stories entry — note new models/services)
- Regenerate: `docs/systems/MODEL_MAP.md`

**Steps:**

1. Update `docs/systems/stories.md`: add `StoryMaturity`, `BeatKind`, `ProgressStatus` to the Enums block; add `Story.maturity`, `Chapter.maturity`, `Episode.maturity/resting_conclusion/is_ending`, `Beat.kind/advances/risk`, `Progress.status` to the model tables; add `StoryNote`; add `services/frontier.py`, `services/maturity.py` and the scope guard to the service-function tables; note the `UNASSIGNED` scope and the risk gate.
2. Update the Stories row in `docs/systems/INDEX.md` (new models + `frontier`/`maturity` services).
3. Regenerate the model map:
   Run: `uv run python tools/introspect_models.py`
   This rewrites `docs/systems/MODEL_MAP.md`.
4. Commit:

```bash
git -C C:/Users/apost/PycharmProjects/arxii add docs/systems/stories.md docs/systems/INDEX.md docs/systems/MODEL_MAP.md
git -C C:/Users/apost/PycharmProjects/arxii commit -m "docs(stories): document authoring backbone (maturity, beat kinds, frontier, StoryNote)"
```

---

## Task 12: Full regression on a fresh DB (required before claiming done)

`--keepdb` hides Evennia-setup-dependent failures. CI uses a fresh DB.

**Steps:**

1. Run the full stories suite **without** `--keepdb`:
   `echo "yes" | uv run arx test world.stories`
   Expected: all PASS on a fresh DB.
2. Run the cross-app suites most likely affected by the scope-default change and the new model fields:
   `echo "yes" | uv run arx test world.stories world.gm world.character_sheets`
   Expected: all PASS. (Add `world.covenants` if the `Story.covenant` interplay surfaces anything.)
3. `ruff check src/world/stories` and `ruff format --check src/world/stories` — clean.
4. If everything passes, the backbone is complete and runnable end-to-end: a story can be authored (Pitch→Outline→Plot per node, non-linear), assigned a scope, run, and a player walked to a frontier that classifies correctly as WAITING_FOR_GM or RESTING, with every richer beat resolving via the existing GM-mark path.
5. Final commit if any lint/regression fixes were needed:

```bash
git -C C:/Users/apost/PycharmProjects/arxii add -A
git -C C:/Users/apost/PycharmProjects/arxii commit -m "test(stories): fresh-DB regression green for authoring backbone"
```

---

## Out of scope (sequenced follow-ups — see design §10)

Do **not** build these here; each is its own later brainstorm:

1. Mission/Challenge resolution engine (the automated player→update loop via existing `resolve_challenge`).
2. Situation/Encounter live-session resolution + Sessions.
3. Consequence + reward *computation* (where `risk` numbers gain names/meaning; `Beat.*_consequences` ConsequencePool FKs already exist as the seam).
4. GM leveling / the real trust→risk ladder (replaces the staff/non-staff check with no schema change) + request-to-exceed escalation + per-category trust.
5. Covenant entity (the `Story.covenant` FK already exists as the seam).
6. Per-DAG-reachability "infant content ahead" detection (current frontier heuristic is story-wide "any immature node remains"); active push-ping to the GM account (current mechanism is dashboard surfacing with staleness age).

## Notes / decisions baked into this plan

- `Beat.kind` defaults to `TASK`, `advances=True`, `risk=0` — benign defaults so existing beat tests/factories are unaffected and `Beat.clean()` is left untouched (kind stays orthogonal to predicate_type).
- `Progress.status` is added alongside the existing `is_active` (not replacing it) so the many `is_active=True` filters across the app keep working; `WAITING_FOR_GM`/`RESTING` keep `is_active=True`, only `COMPLETED` clears it.
- `Story.scope` default changes to `UNASSIGNED`; `StoryFactory` sets `scope` explicitly so it is unaffected, but Task 2 Step 6 sweeps for any test relying on the old implicit default.
- One migration (Task 2) for all schema changes — do not split.
