# Location Ambient Stats Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the `world.locations` app — `LocationStatOverride` and `LocationStatModifier` models with cascade resolution, plus `is_outdoor` on `RoomProfile`, behind a single `effective_stat(room, stat_key)` service.

**Architecture:** Two `SharedMemoryModel` tables polymorphic over `Area` XOR `RoomProfile` via `core.mixins.DiscriminatorMixin`. Cascade walks the existing `AreaClosure` materialized view. Per-stat metadata (default, clamp, suggested change rate) lives as code constants. Read-time lazy decay via `applied_at + change_per_day`. Aggressively trimmed v1 — no bulk reads, no convenience write helpers, no cleanup sweep.

**Tech Stack:** Django 5 + Evennia, `factory_boy`, ruff, ty.

**Reference design doc:** `docs/plans/2026-05-09-location-stats-design.md`

---

## Pre-flight constraints

- Project rule: **never work on main**. Task 0 creates a feature branch.
- Project rule: **never use `cd && <command>` compounds** on Windows — use `git -C <path> ...` if path-targeting is needed. Working directory is repo root.
- Project rule: **`arx test`** for tests. Use `echo "yes" |` prefix for the DB-prompt. Use `just test <args>` recipe where possible.
- Project rule: **constants in `constants.py`**, not nested in models.
- Project rule: **`SharedMemoryModel`** for all concrete models; import from `evennia.utils.idmapper.models`.
- Project rule: **type annotations required** in apps listed in `[tool.ty.src].include` — `world.locations` will be added there. All non-test, non-migration, non-admin, non-factory functions need annotations.
- Project rule: **no JSON fields**, **absolute imports only**, **no Django signals**.
- Existing patterns to mirror:
  - `src/world/areas/` — small, self-contained app with constants/models/admin/factories/tests
  - `src/world/events/models.py:126` — concrete `DiscriminatorMixin` usage with `target_type` choice + `DISCRIMINATOR_MAP`
  - `src/evennia_extensions/factories.py:171` — `RoomProfileFactory` uses `django_get_or_create` because Evennia auto-creates `RoomProfile` on room save

---

### Task 0: Feature branch + commit existing docs

**Files:**
- Modify (already in working tree): `docs/roadmap/rooms-and-estates.md`
- Already written: `docs/plans/2026-05-09-location-stats-design.md` (untracked)

**Step 1: Create feature branch**

Run: `git checkout -b feature/location-ambient-stats`
Expected: switched to a new branch.

**Step 2: Stage and commit the design + roadmap update**

```bash
git add docs/plans/2026-05-09-location-stats-design.md \
        docs/plans/2026-05-09-location-stats.md \
        docs/roadmap/rooms-and-estates.md
git commit -m "docs(rooms): location-stats design + roadmap captures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Expected: commit succeeds. Plan file is committed alongside design + roadmap so the agent has it on disk when working.

---

### Task 1: App skeleton

**Files:**
- Create: `src/world/locations/__init__.py` (empty)
- Create: `src/world/locations/apps.py`
- Create: `src/world/locations/__init__.py` (empty)
- Create: `src/world/locations/migrations/__init__.py` (empty)
- Modify: `src/server/conf/settings.py` (`INSTALLED_APPS` block)
- Modify: `pyproject.toml` (`[tool.ty.src].include`)
- Modify: `tools/check_type_annotations.py` (`TYPED_DIRS`)

**Step 1: Create the empty app package and `apps.py`**

Create `src/world/locations/__init__.py` empty.

Create `src/world/locations/apps.py`:
```python
from django.apps import AppConfig


class LocationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.locations"
    verbose_name = "Locations"
```

Create `src/world/locations/migrations/__init__.py` empty.

**Step 2: Register in `INSTALLED_APPS`**

In `src/server/conf/settings.py`, add `"world.locations.apps.LocationsConfig",` to `INSTALLED_APPS`. Place it directly after `"world.areas.apps.AreasConfig",` (around line 79) so related apps are grouped.

**Step 3: Register in typed-apps lists**

In `pyproject.toml` `[tool.ty.src].include` list, add `"src/world/locations",          # Location ambient stats with cascade`. Place after `"src/world/narrative",`.

In `tools/check_type_annotations.py` `TYPED_DIRS`, add `"src/world/locations",` in the same relative position.

**Step 4: Verify Django finds the app**

Run: `echo "yes" | uv run arx manage check`
Expected: `System check identified no issues (0 silenced).`

**Step 5: Commit**

```bash
git add src/world/locations/__init__.py src/world/locations/apps.py \
        src/world/locations/migrations/__init__.py \
        src/server/conf/settings.py pyproject.toml \
        tools/check_type_annotations.py
git commit -m "feat(locations): scaffold world.locations app

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add `is_outdoor` to `RoomProfile`

**Files:**
- Modify: `src/evennia_extensions/models.py:372` (the `RoomProfile` class)
- Create: `src/evennia_extensions/migrations/0002_roomprofile_is_outdoor.py` (auto-generated)
- Create or modify: `src/evennia_extensions/tests/test_room_profile.py` (test file)

**Step 1: Write the failing test**

Look for existing room-profile tests under `src/evennia_extensions/tests/`. Add (or create file) `test_room_profile.py` with:

```python
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory


class RoomProfileIsOutdoorTests(TestCase):
    def test_default_is_indoor(self) -> None:
        profile = RoomProfileFactory()
        self.assertFalse(profile.is_outdoor)

    def test_field_is_settable(self) -> None:
        profile = RoomProfileFactory(is_outdoor=True)
        self.assertTrue(profile.is_outdoor)
```

If `src/evennia_extensions/tests/__init__.py` does not exist yet, check the layout first:

Run: `ls src/evennia_extensions/tests/` (or use Glob).

If the convention here is a flat `tests.py` rather than a `tests/` package, add the test to the existing `tests.py` instead.

**Step 2: Run test, confirm it fails**

Run: `echo "yes" | uv run arx test evennia_extensions -k IsOutdoor`
Expected: failure with `AttributeError: 'RoomProfile' object has no attribute 'is_outdoor'`.

**Step 3: Add the field on `RoomProfile`**

In `src/evennia_extensions/models.py`, in the `RoomProfile` class (around line 372–403), insert after the `is_public` field:

```python
is_outdoor = models.BooleanField(
    default=False,
    help_text=(
        "Whether this room is exposed to outdoor environment "
        "(weather, sky, etc.). Most rooms are indoor."
    ),
)
```

**Step 4: Generate migration**

Run: `echo "yes" | uv run arx manage makemigrations evennia_extensions`
Expected: a new migration file is created in `src/evennia_extensions/migrations/` named like `0002_roomprofile_is_outdoor.py`.

**Step 5: Apply migration**

Run: `echo "yes" | uv run arx manage migrate evennia_extensions`
Expected: migration applies cleanly.

**Step 6: Run tests**

Run: `echo "yes" | uv run arx test evennia_extensions -k IsOutdoor`
Expected: PASS.

**Step 7: Commit**

```bash
git add src/evennia_extensions/models.py \
        src/evennia_extensions/migrations/0002_roomprofile_is_outdoor.py \
        src/evennia_extensions/tests/  # or src/evennia_extensions/tests.py if flat
git commit -m "feat(rooms): add is_outdoor to RoomProfile

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Constants — `StatKey`, parent type, defaults, clamps, suggested rates

**Files:**
- Create: `src/world/locations/constants.py`

**Step 1: Write `constants.py`**

```python
"""Location stat catalog and per-stat metadata.

Adding a new stat:
    1. Add a new ``StatKey`` member.
    2. Add an entry to ``STAT_DEFAULTS``, ``STAT_CLAMPS``, and
       ``SUGGESTED_CHANGE_PER_DAY``.
    3. Run ``arx manage makemigrations world.locations`` if a Django
       migration is needed (TextChoices changes emit a no-op DB migration).
"""

from __future__ import annotations

from django.db import models


class LocationParentType(models.TextChoices):
    """Discriminator for Location*Stat rows: which FK is active."""

    AREA = "area", "Area"
    ROOM = "room", "Room"


class StatKey(models.TextChoices):
    """Catalog of location ambient stats.

    Stats cascade through the area hierarchy and may be authored at any
    level (continent, kingdom, region, city, ward, neighborhood, building,
    or individual room). See LocationStatOverride and LocationStatModifier
    for cascade semantics.
    """

    CRIME = "crime", "Crime"
    ORDER = "order", "Order"
    CLEANLINESS = "cleanliness", "Cleanliness"
    LIGHTING = "lighting", "Lighting"
    NOISE = "noise", "Noise"
    TRAFFIC = "traffic", "Traffic"


# Per-stat default value when no row exists in the cascade chain.
STAT_DEFAULTS: dict[str, int] = {
    StatKey.CRIME: 0,
    StatKey.ORDER: 50,
    StatKey.CLEANLINESS: 50,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: 50,
    StatKey.TRAFFIC: 50,
}

# Inclusive (min, max) bounds applied to the final cascade-resolved value.
STAT_CLAMPS: dict[str, tuple[int, int]] = {
    StatKey.CRIME: (0, 100),
    StatKey.ORDER: (0, 100),
    StatKey.CLEANLINESS: (0, 100),
    StatKey.LIGHTING: (-2, 2),
    StatKey.NOISE: (0, 100),
    StatKey.TRAFFIC: (0, 100),
}

# Suggested ``change_per_day`` value for new modifiers if the calling
# system has no opinion. Negative values decay toward zero; positive
# values grow; zero is permanent. Per-row override always wins.
SUGGESTED_CHANGE_PER_DAY: dict[str, int] = {
    StatKey.CRIME: -1,
    StatKey.ORDER: 0,
    StatKey.CLEANLINESS: -1,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: -2,
    StatKey.TRAFFIC: -1,
}
```

**Step 2: Smoke-check the import**

Run: `echo "yes" | uv run arx manage shell -c "from world.locations.constants import StatKey, STAT_DEFAULTS; print(list(StatKey), STAT_DEFAULTS)"`
Expected: prints all six stat keys and the defaults dict.

**Step 3: Commit**

```bash
git add src/world/locations/constants.py
git commit -m "feat(locations): stat catalog constants

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `LocationStatOverride` model + migration

**Files:**
- Create or modify: `src/world/locations/models.py`
- Create or modify: `src/world/locations/tests/__init__.py`
- Create: `src/world/locations/tests/test_models.py`
- Create: `src/world/locations/migrations/0001_initial.py` (auto-generated; will also include `LocationStatModifier` after Task 5 if you choose, but generate after Task 4 OR after Task 5 — recommend after Task 5 to keep one initial migration)

> **NOTE:** generate the migration after Task 5 so the initial migration covers both models. Tests in Task 4 use `--keepdb=False` and may run before the migration exists — they will use Django's test-DB autocreate path through `migrate`. To make Task 4 self-contained, either:
> - Generate `0001_initial.py` for Override only, run tests, then add Modifier in Task 5 with `0002_locationstatmodifier.py`, OR
> - Defer test runs in Task 4 until Task 5 lands the second model and a single `0001_initial.py` is generated.
>
> **Choose the first option** so Task 4 can fail-test → green-test on its own. Each task stays self-contained.

**Step 1: Write the failing test**

Create `src/world/locations/tests/__init__.py` (empty) and `src/world/locations/tests/test_models.py`:

```python
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationStatOverride


class LocationStatOverrideTests(TestCase):
    def test_create_with_area(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        row = LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        self.assertEqual(row.area, area)
        self.assertIsNone(row.room_profile)

    def test_create_with_room(self) -> None:
        room = RoomProfileFactory()
        row = LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=-2,
        )
        self.assertEqual(row.room_profile, room)
        self.assertIsNone(row.area)

    def test_clean_rejects_both_fks(self) -> None:
        area = AreaFactory()
        room = RoomProfileFactory()
        row = LocationStatOverride(
            parent_type=LocationParentType.AREA,
            area=area,
            room_profile=room,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_fk(self) -> None:
        row = LocationStatOverride(
            parent_type=LocationParentType.AREA,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_unique_override_per_area_stat(self) -> None:
        area = AreaFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationStatOverride.objects.create(
                parent_type=LocationParentType.AREA,
                area=area,
                stat_key=StatKey.CRIME,
                value=20,
            )

    def test_unique_override_per_room_stat(self) -> None:
        room = RoomProfileFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=-2,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationStatOverride.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=room,
                stat_key=StatKey.LIGHTING,
                value=2,
            )

    def test_different_stats_on_same_area_ok(self) -> None:
        area = AreaFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.ORDER,
            value=80,
        )
        self.assertEqual(
            LocationStatOverride.objects.filter(area=area).count(),
            2,
        )
```

**Step 2: Run tests, verify failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models`
Expected: ImportError or ModuleNotFoundError on `world.locations.models.LocationStatOverride` (model doesn't exist yet).

**Step 3: Implement `LocationStatOverride`**

Create `src/world/locations/models.py`:

```python
"""Models for the location ambient stats cascade.

See ``docs/plans/2026-05-09-location-stats-design.md`` for the full design.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from world.locations.constants import LocationParentType, StatKey


class LocationStatOverride(DiscriminatorMixin, SharedMemoryModel):
    """An absolute claim about a stat at a specific area or room.

    Most-specific override in the cascade chain wins. Overrides cut the
    cascade entirely: when any override exists at any level above (or
    equal to) the room, all modifiers are ignored.

    Used **rarely** — for warded sanctums, safehouses, magically
    stabilized chambers, or other deliberate "this is the value, period"
    claims. Most authored values should use ``LocationStatModifier``
    with ``change_per_day=0`` for a permanent additive instead.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type = models.CharField(
        max_length=10,
        choices=LocationParentType.choices,
        help_text="Selects which FK (area or room_profile) is active.",
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
    )
    stat_key = models.CharField(
        max_length=50,
        choices=StatKey.choices,
        db_index=True,
    )
    value = models.IntegerField(
        help_text="The absolute value asserted at this level. Final read clamps to STAT_CLAMPS.",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Location Stat Override"
        verbose_name_plural = "Location Stat Overrides"
        constraints = [
            models.UniqueConstraint(
                fields=["area", "stat_key"],
                condition=models.Q(area__isnull=False),
                name="unique_override_per_area_stat",
            ),
            models.UniqueConstraint(
                fields=["room_profile", "stat_key"],
                condition=models.Q(room_profile__isnull=False),
                name="unique_override_per_room_stat",
            ),
        ]
        indexes = [
            models.Index(fields=["area", "stat_key"]),
            models.Index(fields=["room_profile", "stat_key"]),
        ]

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Override {self.stat_key}={self.value} @ {target}"
```

**Step 4: Generate the initial migration (Override only)**

Run: `echo "yes" | uv run arx manage makemigrations world.locations`
Expected: `0001_initial.py` created in `src/world/locations/migrations/`.

**Step 5: Apply migration**

Run: `echo "yes" | uv run arx manage migrate world.locations`
Expected: migration applies cleanly.

**Step 6: Run tests**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models`
Expected: all 7 tests PASS.

**Step 7: Commit**

```bash
git add src/world/locations/models.py \
        src/world/locations/tests/__init__.py \
        src/world/locations/tests/test_models.py \
        src/world/locations/migrations/0001_initial.py
git commit -m "feat(locations): LocationStatOverride model

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `LocationStatModifier` model + decay/growth math

**Files:**
- Modify: `src/world/locations/models.py`
- Modify: `src/world/locations/tests/test_models.py`
- Create: `src/world/locations/migrations/0002_locationstatmodifier.py` (auto-generated)

**Step 1: Add modifier tests (failing)**

Append to `src/world/locations/tests/test_models.py`:

```python
from datetime import timedelta

from django.utils import timezone

from world.locations.models import LocationStatModifier


class LocationStatModifierCurrentValueTests(TestCase):
    def test_change_per_day_zero_is_static(self) -> None:
        area = AreaFactory()
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=0,
            applied_at=timezone.now() - timedelta(days=10),
        )
        self.assertEqual(mod.current_value(), 20)

    def test_decay_positive_value(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=5)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=-1,
            applied_at=anchor,
        )
        # 20 + (-1 * 5) = 15
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=5)), 15)

    def test_decayed_past_zero_returns_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=30)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=anchor,
        )
        # 10 + (-1 * 30) = -20 → clamped to 0
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=30)), 0)

    def test_growth_positive_value(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=10)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=2,
            applied_at=anchor,
        )
        # 5 + (2 * 10) = 25 (unbounded; cascade resolver clamps)
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=10)), 25)

    def test_negative_value_growing_toward_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=3)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=-10,
            change_per_day=2,
            applied_at=anchor,
        )
        # -10 + (2 * 3) = -4 (still negative, returned as-is)
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=3)), -4)

    def test_negative_value_passing_zero_returns_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=10)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=-10,
            change_per_day=2,
            applied_at=anchor,
        )
        # -10 + (2 * 10) = 10 → original sign was negative, crossed → 0
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=10)), 0)


class LocationStatModifierStackingTests(TestCase):
    def test_multiple_modifiers_on_same_area_and_stat_allowed(self) -> None:
        area = AreaFactory()
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            source="rebellion",
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            source="market_day",
        )
        self.assertEqual(
            LocationStatModifier.objects.filter(area=area, stat_key=StatKey.CRIME).count(),
            2,
        )
```

**Step 2: Run tests, verify failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models`
Expected: ImportError on `LocationStatModifier`.

**Step 3: Implement `LocationStatModifier`**

Append to `src/world/locations/models.py` (after `LocationStatOverride`):

```python
class LocationStatModifier(DiscriminatorMixin, SharedMemoryModel):
    """An additive contribution to a stat at a specific area or room.

    Modifiers stack across the cascade chain. The effective value at a
    room is the sum of every modifier's :meth:`current_value` plus the
    per-stat default, clamped to bounds — provided no override exists in
    the chain.

    Carries its own ``change_per_day`` so consuming systems can model
    decay or growth rates that depend on IC mechanics. Read-time math is
    lazy; rows are not mutated by time passing.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type = models.CharField(
        max_length=10,
        choices=LocationParentType.choices,
        help_text="Selects which FK (area or room_profile) is active.",
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_modifiers",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_modifiers",
    )
    stat_key = models.CharField(
        max_length=50,
        choices=StatKey.choices,
        db_index=True,
    )
    value = models.IntegerField(
        help_text=(
            "The magnitude at applied_at. Read-side computes the current "
            "value via change_per_day * days_elapsed."
        ),
    )
    change_per_day = models.IntegerField(
        default=0,
        help_text=(
            "Signed: negative decays toward zero, positive grows away from "
            "zero, zero is permanent. Per-row override of any per-stat "
            "default."
        ),
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Free-text label for the originating system or event. Use this "
            "to bulk-clean rows when the source ends "
            "(e.g. ``LocationStatModifier.objects.filter(source='rebellion_1234').delete()``)."
        ),
    )
    applied_at = models.DateTimeField(
        default=timezone.now,
        help_text="Decay anchor. Update this to 'refresh' the modifier.",
    )

    class Meta:
        verbose_name = "Location Stat Modifier"
        verbose_name_plural = "Location Stat Modifiers"
        indexes = [
            models.Index(fields=["area", "stat_key"]),
            models.Index(fields=["room_profile", "stat_key"]),
        ]

    def current_value(self, *, now: datetime | None = None) -> int:
        """Return the lazy decay/growth-resolved value.

        Returns 0 once the modifier has crossed its original sign
        (a positive value decayed past zero, or a negative value grown
        past zero). Otherwise returns ``value + change_per_day * days``.
        """
        if self.change_per_day == 0:
            return self.value
        anchor = now if now is not None else timezone.now()
        elapsed = anchor - self.applied_at
        days = elapsed.total_seconds() / 86400.0
        new_value = self.value + int(self.change_per_day * days)
        if self.value > 0 and new_value <= 0:
            return 0
        if self.value < 0 and new_value >= 0:
            return 0
        return new_value

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Modifier {self.stat_key}+{self.value} @ {target}"
```

Also adjust the file's existing `from datetime import datetime, timedelta` import; if `timedelta` isn't used in the final file, drop it to keep ruff happy.

**Step 4: Generate migration**

Run: `echo "yes" | uv run arx manage makemigrations world.locations`
Expected: `0002_locationstatmodifier.py` created.

**Step 5: Apply migration**

Run: `echo "yes" | uv run arx manage migrate world.locations`
Expected: migration applies cleanly.

**Step 6: Run tests**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models`
Expected: all model tests PASS (Override + Modifier).

**Step 7: Commit**

```bash
git add src/world/locations/models.py \
        src/world/locations/tests/test_models.py \
        src/world/locations/migrations/0002_locationstatmodifier.py
git commit -m "feat(locations): LocationStatModifier with lazy decay/growth

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `effective_stat` cascade service

**Files:**
- Create: `src/world/locations/services.py`
- Create: `src/world/locations/tests/test_services.py`

**Step 1: Write the failing test**

Create `src/world/locations/tests/test_services.py`:

```python
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import (
    STAT_CLAMPS,
    STAT_DEFAULTS,
    LocationParentType,
    StatKey,
)
from world.locations.models import LocationStatModifier, LocationStatOverride
from world.locations.services import effective_stat


class CascadeDefaultsTests(TestCase):
    def test_returns_default_when_no_rows(self) -> None:
        room = RoomProfileFactory().objectdb
        self.assertEqual(
            effective_stat(room, StatKey.ORDER),
            STAT_DEFAULTS[StatKey.ORDER],
        )

    def test_room_with_no_profile_returns_default(self) -> None:
        # Profile is auto-created by Evennia; manually delete to simulate
        # a room with no profile.
        room = RoomProfileFactory().objectdb
        room.room_profile.delete()
        room.refresh_from_db()
        self.assertEqual(
            effective_stat(room, StatKey.CRIME),
            STAT_DEFAULTS[StatKey.CRIME],
        )

    def test_clamps_to_bounds(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        room_profile = RoomProfileFactory(area=ward)
        # Override well above the clamp range
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=999,
        )
        clamp_max = STAT_CLAMPS[StatKey.CRIME][1]
        self.assertEqual(
            effective_stat(room_profile.objectdb, StatKey.CRIME),
            clamp_max,
        )


class CascadeOverrideTests(TestCase):
    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_room_override_wins_over_area_override(self) -> None:
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=0,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 0)

    def test_more_specific_area_override_wins(self) -> None:
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=30,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=70,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 70)

    def test_override_anywhere_hides_modifiers(self) -> None:
        # Override at city, modifier at ward — modifier must be ignored
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=50,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 10)


class CascadeModifierStackingTests(TestCase):
    def setUp(self) -> None:
        self.region = AreaFactory(level=AreaLevel.REGION)
        self.city = AreaFactory(level=AreaLevel.CITY, parent=self.region)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_modifiers_at_multiple_levels_sum(self) -> None:
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.region,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=20,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=5,
        )
        # 0 default + 10 + 20 + 5 = 35
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 35)

    def test_decayed_modifier_contributes_zero(self) -> None:
        # value 10, decay -1/day, applied 30 days ago → 0
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 0)
```

**Step 2: Run tests, verify failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_services`
Expected: ImportError on `world.locations.services`.

**Step 3: Implement the service**

Create `src/world/locations/services.py`:

```python
"""Read services for the location ambient stats cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.areas.models import AreaClosure
from world.locations.constants import STAT_CLAMPS, STAT_DEFAULTS, StatKey
from world.locations.models import LocationStatModifier, LocationStatOverride

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


def _clamp(value: int, stat_key: str) -> int:
    bounds = STAT_CLAMPS.get(stat_key)
    if bounds is None:
        return value
    low, high = bounds
    return max(low, min(high, value))


def effective_stat(room: "DefaultObject", stat_key: str) -> int:
    """Cascade-resolve a single stat for a room, clamped to per-stat bounds.

    Algorithm:
      1. Resolve ``room.room_profile`` and its area. If the profile is
         missing, return ``STAT_DEFAULTS[stat_key]`` clamped.
      2. Look up the area's ancestors (and itself) via ``AreaClosure``.
      3. If any ``LocationStatOverride`` exists for the ancestor set or
         the room_profile and matches ``stat_key``, pick the most-specific
         (room > deepest area) and return its value, clamped.
      4. Otherwise sum every ``LocationStatModifier.current_value`` for
         the same scope and ``stat_key``, add ``STAT_DEFAULTS[stat_key]``,
         clamp, return.
    """

    default = STAT_DEFAULTS.get(stat_key, 0)
    profile = getattr(room, "room_profile", None)
    if profile is None:
        return _clamp(default, stat_key)

    area = profile.area
    ancestor_ids: list[int] = []
    if area is not None:
        ancestor_ids = list(
            AreaClosure.objects.filter(descendant_id=area.pk).values_list(
                "ancestor_id", flat=True
            )
        )

    # Step 3: most-specific override wins, modifiers ignored.
    overrides = list(
        LocationStatOverride.objects.filter(stat_key=stat_key).filter(
            models.Q(room_profile=profile)
            | models.Q(area_id__in=ancestor_ids)
        )
    )
    if overrides:
        # Specificity: room beats any area; among areas, deeper level wins.
        # Area.level is an int (smaller = more specific, per AreaLevel).
        room_overrides = [o for o in overrides if o.room_profile_id == profile.pk]
        if room_overrides:
            return _clamp(room_overrides[0].value, stat_key)
        # All remaining are area-scoped; pick the smallest area.level.
        chosen = min(overrides, key=lambda o: o.area.level)
        return _clamp(chosen.value, stat_key)

    # Step 4: sum modifier current_values.
    modifiers = LocationStatModifier.objects.filter(stat_key=stat_key).filter(
        models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids)
    )
    total = default + sum(mod.current_value() for mod in modifiers)
    return _clamp(total, stat_key)
```

Add `from django.db import models` near the top of the file.

**Step 4: Run tests**

Run: `echo "yes" | uv run arx test world.locations.tests.test_services`
Expected: all 8 tests PASS.

**Step 5: Run the whole `world.locations` test module to confirm nothing regressed**

Run: `echo "yes" | uv run arx test world.locations`
Expected: all tests PASS.

**Step 6: Commit**

```bash
git add src/world/locations/services.py \
        src/world/locations/tests/test_services.py
git commit -m "feat(locations): effective_stat cascade service

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Factories

**Files:**
- Create: `src/world/locations/factories.py`

**Step 1: Write factories**

Create `src/world/locations/factories.py`:

```python
import factory
import factory.django

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationStatModifier, LocationStatOverride


class LocationStatOverrideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatOverride

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    stat_key = StatKey.CRIME
    value = 50

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )


class LocationStatModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatModifier

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    stat_key = StatKey.CRIME
    value = 10
    change_per_day = 0
    source = ""

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )
```

**Step 2: Smoke-check via shell**

Run:
```
echo "yes" | uv run arx manage shell -c "from world.locations.factories import LocationStatOverrideFactory, LocationStatModifierFactory; print(LocationStatOverrideFactory.build()); print(LocationStatModifierFactory.build())"
```
Expected: prints two stub instances without errors.

(If the smoke-check writes to DB unintentionally, switch the smoke command to a unit test instead — but `factory.build()` does NOT save by design.)

**Step 3: Commit**

```bash
git add src/world/locations/factories.py
git commit -m "feat(locations): factories for tests

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Admin

**Files:**
- Create: `src/world/locations/admin.py`

**Step 1: Write admin registrations**

Create `src/world/locations/admin.py`:

```python
from django.contrib import admin

from world.locations.models import LocationStatModifier, LocationStatOverride


@admin.register(LocationStatOverride)
class LocationStatOverrideAdmin(admin.ModelAdmin):
    list_display = ("__str__", "parent_type", "stat_key", "value", "last_updated")
    list_filter = ("parent_type", "stat_key")
    search_fields = ("source",)
    autocomplete_fields = ("area", "room_profile")
    readonly_fields = ("last_updated",)
    fieldsets = (
        (
            "What and where",
            {
                "fields": ("parent_type", "area", "room_profile", "stat_key", "value"),
                "description": (
                    "Use Override only for deliberate cascade-cuts (warded "
                    "sanctums, safehouses, magically stabilized chambers). "
                    "For 'this is the normal value at this level' use a "
                    "Modifier with change_per_day=0 instead — overrides "
                    "hide all modifiers in the chain."
                ),
            },
        ),
        ("Audit", {"fields": ("last_updated",)}),
    )


@admin.register(LocationStatModifier)
class LocationStatModifierAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "parent_type",
        "stat_key",
        "value",
        "change_per_day",
        "applied_at",
    )
    list_filter = ("parent_type", "stat_key")
    search_fields = ("source",)
    autocomplete_fields = ("area", "room_profile")
    fieldsets = (
        (
            "What and where",
            {
                "fields": ("parent_type", "area", "room_profile", "stat_key"),
            },
        ),
        (
            "Magnitude and change",
            {
                "fields": ("value", "change_per_day", "applied_at"),
                "description": (
                    "value is the magnitude at applied_at. change_per_day "
                    "is signed: negative decays toward zero, positive grows "
                    "away from zero, zero is permanent. Read-side computes "
                    "current value lazily."
                ),
            },
        ),
        (
            "Provenance",
            {
                "fields": ("source",),
                "description": (
                    "Free-text label for the originating system. Use to "
                    "bulk-clean by source when a triggering event ends."
                ),
            },
        ),
    )
```

**Step 2: Smoke-check Django still loads**

Run: `echo "yes" | uv run arx manage check`
Expected: no issues.

If the admin registration triggers admin-autocomplete prerequisites that don't exist (e.g., AreaAdmin missing `search_fields`), drop `autocomplete_fields = ("area", ...)` for that model and use the default raw FK widget.

**Step 3: Commit**

```bash
git add src/world/locations/admin.py
git commit -m "feat(locations): admin registrations with discipline help text

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: App `CLAUDE.md` documentation

**Files:**
- Create: `src/world/locations/CLAUDE.md`

**Step 1: Write the doc**

Create `src/world/locations/CLAUDE.md`:

```markdown
# Locations - Ambient Stats Cascade

Authored substrate for ambient room/area stats (crime, order, lighting, …).
Stats cascade through the area hierarchy and are read via a single service.

See `docs/plans/2026-05-09-location-stats-design.md` for the full design and
the rationale behind every choice.

## Models

- **`LocationStatOverride`** — absolute claim at a specific area or room.
  Most-specific override in the cascade chain wins, and any override
  anywhere in the chain causes ALL modifiers in that chain to be ignored.
  **Use rarely** — for warded sanctums, safehouses, magically stabilized
  chambers. The "this is the value, period" claim.
- **`LocationStatModifier`** — additive contribution. Stacks across the
  cascade chain. Carries `change_per_day` for read-time decay/growth.
  **The common authoring path** — including for what feels like
  "the permanent value at this level," which is just a modifier with
  `change_per_day=0`.

## Cascade rule

For any `(room, stat_key)`:

1. Walk the closure chain from the room outward via `AreaClosure`.
2. **If any level in the chain has authored an Override** → use the
   most-specific Override's value (clamped). All Modifiers ignored.
3. **Otherwise** → sum every Modifier's `current_value()` across the
   chain, plus `STAT_DEFAULTS[stat_key]`, clamp.

## Authoring discipline

- Default to **Modifier**. Most authored values — even ones that feel
  static, like a noble manor's prestige — should be a Modifier with
  `change_per_day=0`. They're called "modifiers" but they're equally
  valid as authored baselines that happen to never change.
- Reach for **Override** only when you mean "ignore everything upstream
  and downstream — this is the value." If you find yourself authoring
  Overrides routinely, you're probably misusing them.
- Use the `source` field on Modifiers when the originating system needs
  to clean up later: `LocationStatModifier.objects.filter(source="rebellion_1234").delete()`.

## Reading

Single service:

```python
from world.locations.services import effective_stat

crime_here = effective_stat(room, StatKey.CRIME)
```

That's it. No bulk reads, no convenience write helpers, no cleanup sweep
in v1 — they're added when consumers need them.

## Adding a new stat

1. Add a member to `StatKey` in `constants.py`.
2. Add entries to `STAT_DEFAULTS`, `STAT_CLAMPS`, `SUGGESTED_CHANGE_PER_DAY`.
3. Run `echo "yes" | uv run arx manage makemigrations world.locations` —
   TextChoices changes emit a no-op DB migration.
4. Run `arx manage migrate world.locations`.
```

**Step 2: Commit**

```bash
git add src/world/locations/CLAUDE.md
git commit -m "docs(locations): CLAUDE.md with authoring discipline

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Final regression run

**Step 1: Run all affected app suites with `--keepdb`**

Run: `echo "yes" | uv run arx test world.locations world.areas evennia_extensions --keepdb`
Expected: all PASS.

**Step 2: Lint**

Run: `uv run ruff check src/world/locations src/evennia_extensions/models.py`
Expected: no findings. If found, `uv run ruff check src/world/locations src/evennia_extensions/models.py --fix` and re-run.

**Step 3: Type-check**

Run: `uv run ty check src/world/locations`
Expected: no errors.

**Step 4: Full regression without `--keepdb`** (matches CI fresh-DB behavior)

Run: `echo "yes" | uv run arx test world.locations world.areas evennia_extensions`
Expected: all PASS on fresh DB.

If any test depends on auto-created RoomProfile and fails on fresh DB, the fix is to use the factory's `django_get_or_create` semantics consistently — the design avoided implicit-default reliance.

**Step 5: Update MODEL_MAP** (per CLAUDE.md guidance after model changes)

Run: `uv run python tools/introspect_models.py`
Expected: `docs/systems/MODEL_MAP.md` updated.

**Step 6: Commit MODEL_MAP and any incidental fixes**

```bash
git add docs/systems/MODEL_MAP.md
git commit -m "chore(locations): regenerate MODEL_MAP after locations app

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If the regen produces no diff, skip this commit.)

**Step 7: Final summary**

Print a status: branch is `feature/location-ambient-stats`, all tests pass on fresh DB, ready for PR. The user creates the PR manually via the GitHub web UI per CLAUDE.md (no `gh` commands).

---

## Done

The wedge ships:
- `world.locations` app registered, type-checked
- `LocationStatOverride` and `LocationStatModifier` models with constraints and indexes
- `StatKey` TextChoices + per-stat constants
- `is_outdoor` on `RoomProfile`
- `effective_stat(room, stat_key)` service
- Factories, admin with discipline help text, app `CLAUDE.md`
- Tests across cascade rule, decay/growth math, partial-unique constraints, DiscriminatorMixin enforcement, default fallback
- MODEL_MAP regenerated

Deferred items live in `docs/roadmap/rooms-and-estates.md` and the design doc — no action needed on them in this branch.
