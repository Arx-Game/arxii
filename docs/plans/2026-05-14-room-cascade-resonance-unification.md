# Room Cascade Resonance Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collapse the magic-app's tag-only `RoomAuraProfile` / `RoomResonance` into the existing locations cascade (`LocationStatModifier` / `LocationStatOverride`) so a single cascade substrate carries every area-walked value in the codebase — stats *and* resonance — with magnitude, override, and decay all working uniformly.

**Architecture:** Add a second discriminator (`key_type` = STAT or RESONANCE) to the existing cascade models, with a nullable `resonance` FK alongside `stat_key`. Migrate `RoomResonance` tag rows to cascade rows with author-chosen default magnitudes. Drop `RoomAuraProfile` and `RoomResonance` entirely. Repoint `ResonanceGrant.source_room_aura_profile` → `source_room_profile`. Rename `LocationStat*` → `LocationValue*` since the table is no longer stat-only. The locations app gains a string FK to `magic.Resonance` — this is the only domain dep it will take (cascading is unique to area hierarchy; finite set of axes).

**Tech Stack:** Django 5.x, PostgreSQL, Evennia framework, `SharedMemoryModel` identity map, `DiscriminatorMixin` for multi-discriminator validation, `AreaClosure` materialized view for hierarchy walks. Tests via `arx test`. No `gh` CLI. No compound bash commands on Windows.

---

## Background

### What exists today (pre-plan)

**Locations app** (`src/world/locations/`, added in PR #432 on 2026-05-10):

- `LocationStatModifier(DiscriminatorMixin, SharedMemoryModel)` — additive contribution to a stat at an area or room. Fields: `parent_type` (AREA/ROOM), `area` FK, `room_profile` FK, `stat_key` (CharField from `StatKey` TextChoices), `value`, `change_per_day`, `source`, `applied_at`.
- `LocationStatOverride(DiscriminatorMixin, SharedMemoryModel)` — absolute claim. Short-circuits the cascade entirely. Fields: `parent_type`, `area`, `room_profile`, `stat_key`, `value`, `last_updated`.
- `StatKey` TextChoices: `CRIME`, `ORDER`, `CLEANLINESS`, `LIGHTING`, `NOISE`, `TRAFFIC`.
- `effective_stat(room, stat_key) -> int` walks `AreaClosure` from the room outward: if any Override exists at any level → most-specific Override's value wins (all Modifiers ignored); otherwise sum all Modifier `current_value()`s plus `STAT_DEFAULTS[key]`, clamp.
- Bulk: `effective_stats_for_rooms(rooms, stat_keys)`. History: `ownership_history_for`, `tenancy_history_for`. Cleanup: `cleanup_decayed_modifiers()`.

**Magic-app room aura** (`src/world/magic/models/room_aura.py`, added in Spec C):

- `RoomAuraProfile(SharedMemoryModel)` — OneToOne to `RoomProfile`. **No fields beyond the FK.** Marker that "this room has magical character."
- `RoomResonance(SharedMemoryModel)` — through-model: `room_aura_profile` FK, `resonance` FK, `set_by` (AccountDB FK), `set_at`. Tag-only — **no magnitude**.
- Consumers: residence trickle (`get_residence_resonances`, `residence_trickle_tick`), `RoomsByPropertyView`, `ResonanceGrant.source_room_aura_profile` audit FK.

### The duplication

Both systems answer "what's at this room" but with different abilities:
- RoomResonance tells you *flavor* (celestial-tagged) but not *intensity*.
- LocationStatModifier tells you *intensity* (crime=42) but only for fixed StatKey choices.

The cathedral example from the brainstorm — region neutral, city +100 predari, cathedral 1000 celestial absolute override — wants both pieces: intensity AND a Resonance-typed key. Neither system delivers alone.

### Why merge into locations

We considered three architectures:
- **Option α (chosen):** Add `resonance` FK to the existing cascade models. One table family, one cascade, one mental model. Locations imports `magic.Resonance` — directional dep, but cascading is unique to areas, so the finite set of cascade axes won't sprawl into a junction.
- **Option β:** Lift cascade into `evennia_extensions`, keep both apps domain-agnostic. More invasive, no real long-term win given the small set of cascade axes.
- **Option γ:** Abstract base + per-domain cascade tables. Over-engineered for a finite set; pays duplication cost to solve a future that won't materialize.

User explicitly confirmed: cascading is an *area*-system thing, not a general hierarchy pattern. Other "hierarchies" in the codebase (noble titles, org ranks, gift trees) don't cascade values. With that constraint, option α wins.

### What's NOT in this plan

The **technique pre-cast backfire trigger** is out of scope. It needs its own design pass — formula for comparing room cascade resonance vs character resonance vs technique resonance, consequence pool routing, severity scaling, perform_check integration. That becomes a follow-up plan once this cascade unification lands. This plan stops at "the cascade can answer `effective_value(room, resonance=celestial) -> 1000`."

---

## Pre-Flight Checks

Before starting, verify:

- Current branch is clean: `git -C C:/Users/apost/PycharmProjects/arxii status` shows no uncommitted changes
- New feature branch: `git -C C:/Users/apost/PycharmProjects/arxii checkout -b feature/room-cascade-resonance-unification`
- Dev DB is healthy: `echo "yes" | uv run arx test world.locations --keepdb` passes baseline

The user does NOT use git worktrees. Work on the feature branch directly.

---

## Phase 1: Add resonance axis to the cascade (non-breaking additions)

Each task is additive — existing `LocationStatModifier` rows keep working untouched throughout this phase.

### Task 1: Add `KeyType` enum and `RESONANCE_DEFAULT_MAGNITUDE` constant

**Files:**
- Modify: `src/world/locations/constants.py`

**Step 1: Add the enum**

In `src/world/locations/constants.py`, add after `LocationParentType`:

```python
class KeyType(models.TextChoices):
    """Which field carries the cascade row's key.

    STAT → ``stat_key`` (CharField, StatKey enum).
    RESONANCE → ``resonance`` (FK to ``magic.Resonance``).

    Exactly one is populated per row; the model's ``clean()`` validates
    via DiscriminatorMixin._validate_discriminator.
    """

    STAT = "stat", "Stat"
    RESONANCE = "resonance", "Resonance"


# Default magnitude when migrating tag-only RoomResonance rows to the cascade.
# Authors should re-tune per room afterwards. 100 is a starting baseline that
# sits in the middle of any plausible per-resonance scale.
RESONANCE_DEFAULT_MAGNITUDE: int = 100
```

**Step 2: Run linting and existing tests to confirm no breakage**

Run: `uv run ruff check src/world/locations/constants.py`
Expected: PASS, no issues

Run: `echo "yes" | uv run arx test world.locations`
Expected: PASS, all existing tests still green (we haven't touched models yet)

**Step 3: Commit**

```powershell
git -C C:/Users/apost/PycharmProjects/arxii add src/world/locations/constants.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(locations): add KeyType enum for cascade axis discriminator"
```

---

### Task 2: Add `key_type` + `resonance` FK to `LocationStatModifier`

**Files:**
- Modify: `src/world/locations/models.py` (LocationStatModifier class)
- Create: `src/world/locations/migrations/0004_locationstatmodifier_resonance.py` (generated)

**Step 1: Write failing test for the new field**

Add to `src/world/locations/tests/test_models.py`:

```python
def test_locationstatmodifier_resonance_key_clean(self):
    """A row with key_type=RESONANCE requires resonance and forbids stat_key."""
    from world.locations.constants import KeyType
    from world.magic.factories import ResonanceFactory

    resonance = ResonanceFactory()
    row = LocationStatModifier(
        parent_type=LocationParentType.ROOM,
        room_profile=self.room_profile,
        key_type=KeyType.RESONANCE,
        resonance=resonance,
        value=100,
    )
    row.full_clean()  # should not raise

def test_locationstatmodifier_resonance_key_requires_resonance(self):
    """key_type=RESONANCE with resonance=None fails clean."""
    from world.locations.constants import KeyType

    row = LocationStatModifier(
        parent_type=LocationParentType.ROOM,
        room_profile=self.room_profile,
        key_type=KeyType.RESONANCE,
        stat_key=StatKey.CRIME,  # wrong field set
        value=100,
    )
    with self.assertRaises(ValidationError) as ctx:
        row.full_clean()
    assert "resonance" in ctx.exception.message_dict

def test_locationstatmodifier_stat_key_still_works(self):
    """Existing key_type=STAT path continues to work unchanged."""
    from world.locations.constants import KeyType

    row = LocationStatModifier(
        parent_type=LocationParentType.ROOM,
        room_profile=self.room_profile,
        key_type=KeyType.STAT,
        stat_key=StatKey.CRIME,
        value=42,
    )
    row.full_clean()  # should not raise
```

**Step 2: Run to confirm failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models -k key_type`
Expected: FAIL — `LocationStatModifier` has no `key_type` field

**Step 3: Add fields and discriminator validation**

In `src/world/locations/models.py`, modify `LocationStatModifier`:

```python
from world.locations.constants import HolderType, KeyType, LocationParentType, StatKey


class LocationStatModifier(DiscriminatorMixin, SharedMemoryModel):
    """[existing docstring...]"""

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    # NEW: second discriminator for axis (stat vs resonance).
    KEY_TYPE_DISCRIMINATOR_FIELD = "key_type"
    KEY_TYPE_DISCRIMINATOR_MAP = {
        KeyType.STAT: "stat_key",
        KeyType.RESONANCE: "resonance",
    }

    parent_type = models.CharField(...)
    area = models.ForeignKey(...)
    room_profile = models.ForeignKey(...)

    # NEW: key axis discriminator + the resonance FK.
    key_type = models.CharField(
        max_length=10,
        choices=KeyType.choices,
        default=KeyType.STAT,
        help_text="Selects which key field (stat_key or resonance) is active.",
    )
    stat_key = models.CharField(
        max_length=50,
        choices=StatKey.choices,
        db_index=True,
        blank=True,
        default="",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cascade_modifiers",
    )

    value = models.IntegerField(...)
    change_per_day = models.IntegerField(...)
    source = models.CharField(...)
    applied_at = models.DateTimeField(...)

    class Meta:
        verbose_name = "Location Stat Modifier"
        verbose_name_plural = "Location Stat Modifiers"
        indexes = [
            models.Index(fields=["area", "stat_key"]),
            models.Index(fields=["room_profile", "stat_key"]),
            # NEW: resonance-keyed lookup indexes.
            models.Index(fields=["area", "resonance"]),
            models.Index(fields=["room_profile", "resonance"]),
        ]

    def clean(self) -> None:
        """Validate BOTH discriminators (parent and key)."""
        parent_errors = self._validate_discriminator(
            self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP
        )
        key_errors = self._validate_discriminator(
            self.KEY_TYPE_DISCRIMINATOR_FIELD, self.KEY_TYPE_DISCRIMINATOR_MAP
        )
        errors = {**parent_errors, **key_errors}
        if errors:
            raise ValidationError(errors)
```

Notes for the implementor:
- `stat_key` becomes `blank=True, default=""` because for RESONANCE rows it must be empty.
- The discriminator validator treats `""` as falsy and `None` as falsy — verify by reading `_validate_discriminator` in `src/core/mixins.py` (it uses `getattr(self, expected_field) is None`). Since `stat_key` is a CharField that returns `""` not `None`, the validator may need a small adjustment. **Verify behavior first** by running the failing test; if `_validate_discriminator` doesn't handle empty CharField correctly, extend the mixin OR override the validation locally.
- Look at `feedback_partial_unique_indexes.md` — partial UniqueConstraints already create indexes. Make sure the new resonance indexes aren't duplicating any existing constraint coverage. For Modifier we don't have UniqueConstraints (multiple modifier rows per key are valid), so explicit indexes are fine.

**Step 4: Generate the migration**

Run: `uv run arx manage makemigrations locations`
Expected output: creates `src/world/locations/migrations/0004_locationstatmodifier_resonance.py`

Inspect the generated migration to verify it:
- Adds `key_type` (CharField, default STAT)
- Adds `resonance` (FK, nullable)
- Adds `stat_key` blank/default tweak
- Adds the two new indexes

**Step 5: Apply the migration locally**

Run: `uv run arx manage migrate locations`
Expected: migration applies cleanly

**Step 6: Run the new tests to verify they pass**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models -k key_type`
Expected: PASS, 3 tests

**Step 7: Run the full locations suite to verify no regression**

Run: `echo "yes" | uv run arx test world.locations`
Expected: all existing tests still PASS

**Step 8: Commit**

```powershell
git -C C:/Users/apost/PycharmProjects/arxii add src/world/locations/models.py src/world/locations/migrations/0004_locationstatmodifier_resonance.py src/world/locations/tests/test_models.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(locations): add resonance key to LocationStatModifier"
```

---

### Task 3: Add `key_type` + `resonance` FK to `LocationStatOverride`

Same shape as Task 2 but for `LocationStatOverride`. The existing `UniqueConstraint` on `(area, stat_key)` / `(room_profile, stat_key)` needs sibling constraints for `(area, resonance)` / `(room_profile, resonance)`.

**Files:**
- Modify: `src/world/locations/models.py` (LocationStatOverride class)
- Modify: `src/world/locations/tests/test_models.py`
- Create: `src/world/locations/migrations/0005_locationstatoverride_resonance.py`

**Step 1: Write failing tests**

Add to `src/world/locations/tests/test_models.py` mirroring the modifier tests (`test_locationstatoverride_resonance_key_clean`, `..._requires_resonance`, `..._stat_key_still_works`).

Also add:

```python
def test_locationstatoverride_unique_per_room_resonance(self):
    """Only one override row per (room, resonance) — partial UniqueConstraint."""
    from world.locations.constants import KeyType
    from world.magic.factories import ResonanceFactory

    resonance = ResonanceFactory()
    LocationStatOverride.objects.create(
        parent_type=LocationParentType.ROOM,
        room_profile=self.room_profile,
        key_type=KeyType.RESONANCE,
        resonance=resonance,
        value=1000,
    )
    with self.assertRaises(IntegrityError):
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=500,
        )
```

**Step 2: Run to confirm failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_models -k override`
Expected: FAIL

**Step 3: Add fields and constraints**

Mirror the Modifier shape. Add to `LocationStatOverride.Meta.constraints`:

```python
constraints = [
    # Existing stat_key constraints
    models.UniqueConstraint(
        fields=["area", "stat_key"],
        condition=models.Q(area__isnull=False) & models.Q(stat_key__gt=""),
        name="unique_override_per_area_stat",
    ),
    models.UniqueConstraint(
        fields=["room_profile", "stat_key"],
        condition=models.Q(room_profile__isnull=False) & models.Q(stat_key__gt=""),
        name="unique_override_per_room_stat",
    ),
    # NEW resonance constraints
    models.UniqueConstraint(
        fields=["area", "resonance"],
        condition=models.Q(area__isnull=False) & models.Q(resonance__isnull=False),
        name="unique_override_per_area_resonance",
    ),
    models.UniqueConstraint(
        fields=["room_profile", "resonance"],
        condition=models.Q(room_profile__isnull=False) & models.Q(resonance__isnull=False),
        name="unique_override_per_room_resonance",
    ),
]
```

Implementor note: the existing stat_key constraints needed the `stat_key__gt=""` condition added because RESONANCE rows have `stat_key=""` and the original constraint was `area__isnull=False` only. Without this tweak, multiple resonance rows on the same area would collide on the empty stat_key. Verify by writing a test that creates two RESONANCE rows on the same area with different resonances — should succeed.

**Step 4: makemigrations / migrate / test / commit** (same flow as Task 2)

```powershell
uv run arx manage makemigrations locations
uv run arx manage migrate locations
echo "yes" | uv run arx test world.locations.tests.test_models
git -C C:/Users/apost/PycharmProjects/arxii add -A
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(locations): add resonance key to LocationStatOverride"
```

---

### Task 4: Generalize `effective_stat` → `effective_value` (polymorphic axis)

**Files:**
- Modify: `src/world/locations/services.py`
- Modify: `src/world/locations/tests/test_services.py`

**Step 1: Write failing test for `effective_value(room, resonance=R)`**

Add to `src/world/locations/tests/test_services.py`:

```python
def test_effective_value_resonance_cascade_walks_to_area(self):
    """A modifier on the city contributes to a room inside the city."""
    from world.locations.constants import KeyType
    from world.locations.services import effective_value
    from world.magic.factories import ResonanceFactory

    predari = ResonanceFactory(name="Predari")
    LocationStatModifier.objects.create(
        parent_type=LocationParentType.AREA,
        area=self.city,
        key_type=KeyType.RESONANCE,
        resonance=predari,
        value=100,
        change_per_day=0,
    )
    result = effective_value(self.room_in_city, resonance=predari)
    assert result == 100

def test_effective_value_resonance_override_short_circuits(self):
    """A room-level resonance override wipes city-level modifiers."""
    from world.locations.constants import KeyType
    from world.locations.services import effective_value
    from world.magic.factories import ResonanceFactory

    predari = ResonanceFactory(name="Predari")
    copperi = ResonanceFactory(name="Copperi")
    LocationStatModifier.objects.create(
        parent_type=LocationParentType.AREA, area=self.city,
        key_type=KeyType.RESONANCE, resonance=predari, value=100,
    )
    LocationStatOverride.objects.create(
        parent_type=LocationParentType.ROOM, room_profile=self.room_profile,
        key_type=KeyType.RESONANCE, resonance=copperi, value=1000,
    )
    # Same-resonance override would short-circuit; different-resonance override
    # does NOT short-circuit predari resolution.
    assert effective_value(self.room_in_city, resonance=predari) == 100
    assert effective_value(self.room_in_city, resonance=copperi) == 1000

def test_effective_value_requires_exactly_one_axis(self):
    from world.locations.services import effective_value
    from world.magic.factories import ResonanceFactory

    with self.assertRaises(ValueError):
        effective_value(self.room_in_city)  # neither
    with self.assertRaises(ValueError):
        effective_value(self.room_in_city, stat_key=StatKey.CRIME, resonance=ResonanceFactory())

def test_effective_value_stat_key_still_works(self):
    """Backwards path: effective_value(room, stat_key=X) matches old effective_stat."""
    from world.locations.services import effective_stat, effective_value
    LocationStatModifier.objects.create(
        parent_type=LocationParentType.AREA, area=self.city,
        key_type=KeyType.STAT, stat_key=StatKey.CRIME, value=20,
    )
    assert effective_value(self.room_in_city, stat_key=StatKey.CRIME) == effective_stat(
        self.room_in_city, StatKey.CRIME
    )
```

**Step 2: Run to confirm failure**

Run: `echo "yes" | uv run arx test world.locations.tests.test_services -k effective_value`
Expected: FAIL — `effective_value` not defined

**Step 3: Implement**

In `src/world/locations/services.py`:

```python
def effective_value(
    room: DefaultObject,
    *,
    stat_key: StatKey | None = None,
    resonance: Resonance | None = None,
) -> int:
    """Cascade-resolved value at this room for one axis.

    Exactly one of ``stat_key`` or ``resonance`` must be provided.

    Walks the room's area ancestry via ``AreaClosure``:
    - If any Override exists at any level → most-specific Override wins,
      all Modifiers ignored. Result is clamped (stats only).
    - Otherwise → sum every Modifier's ``current_value()`` across the
      chain, plus the per-stat default for stats (or 0 for resonance),
      clamp (stats only).

    Resonance values are not clamped — author whatever magnitude makes sense.
    """
    if (stat_key is None) == (resonance is None):
        raise ValueError("Provide exactly one of stat_key or resonance.")

    profile, ancestor_ids = _room_profile_and_ancestors(room)
    if profile is None:
        return STAT_DEFAULTS[stat_key] if stat_key is not None else 0

    # Build the axis-specific filter once.
    if stat_key is not None:
        axis_filter = Q(key_type=KeyType.STAT, stat_key=stat_key)
        default_value = STAT_DEFAULTS[stat_key]
        clamp = STAT_CLAMPS[stat_key]
    else:
        axis_filter = Q(key_type=KeyType.RESONANCE, resonance=resonance)
        default_value = 0
        clamp = None  # resonance is unclamped

    # Override path
    override_q = (
        Q(parent_type=LocationParentType.ROOM, room_profile=profile)
        | Q(parent_type=LocationParentType.AREA, area_id__in=ancestor_ids)
    )
    override = (
        LocationStatOverride.objects.filter(axis_filter & override_q)
        .annotate(
            specificity=Case(
                When(parent_type=LocationParentType.ROOM, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("specificity")
        .first()
    )
    if override is not None:
        return _clamp(override.value, clamp)

    # Modifier path
    modifier_q = (
        Q(parent_type=LocationParentType.ROOM, room_profile=profile)
        | Q(parent_type=LocationParentType.AREA, area_id__in=ancestor_ids)
    )
    modifiers = LocationStatModifier.objects.filter(axis_filter & modifier_q)
    total = default_value + sum(m.current_value() for m in modifiers)
    return _clamp(total, clamp)


def _clamp(value: int, clamp: tuple[int, int] | None) -> int:
    if clamp is None:
        return value
    lo, hi = clamp
    return max(lo, min(hi, value))


def effective_stat(room: DefaultObject, stat_key: StatKey) -> int:
    """Deprecated thin wrapper. Prefer ``effective_value(room, stat_key=…)``."""
    return effective_value(room, stat_key=stat_key)
```

Implementor notes:
- Add imports: `from django.db.models import Case, IntegerField, Q, Value, When`; `from world.magic.models import Resonance` (under `if TYPE_CHECKING:` to avoid runtime cycle — the queryset uses string FK refs already).
- The "ancestry specificity ordering" logic above is a simplification — verify against the existing `effective_stat` impl in `services.py`. If the existing function orders by depth via `AreaClosure.depth`, mirror that ordering exactly so resonance reads use the same most-specific-wins rule.
- Keep `effective_stat` as a wrapper so callers can migrate gradually. Don't rip out old callers in this task.

**Step 4: Run tests**

Run: `echo "yes" | uv run arx test world.locations.tests.test_services -k effective_value`
Expected: PASS, 4 tests

Run full locations suite: `echo "yes" | uv run arx test world.locations`
Expected: all pass

**Step 5: Commit**

```powershell
git -C C:/Users/apost/PycharmProjects/arxii add src/world/locations/services.py src/world/locations/tests/test_services.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(locations): add polymorphic effective_value(stat_key OR resonance)"
```

---

### Task 5: Bulk read variant `effective_values_for_rooms`

Same TDD pattern as Task 4 but for the bulk read. Verify query count is independent of room count (the `_bulk_room_profiles_and_ancestors` helper already exists — reuse it).

**Files:**
- Modify: `src/world/locations/services.py`
- Modify: `src/world/locations/tests/test_bulk_reads.py`

**Step 1: Write failing test** that creates 3 rooms across 2 cities, sets resonance modifiers at various tiers, and asserts the returned dict shape:

```python
def test_effective_values_for_rooms_resonance_axis(self):
    """Bulk read with resonance axis returns {room_pk: {resonance: value}}."""
    # ...setup...
    result = effective_values_for_rooms(
        [room_a, room_b, room_c],
        resonances=[predari, copperi],
    )
    assert result[room_a.pk][predari] == 100
    assert result[room_b.pk][copperi] == 1000  # override
    # ...etc
```

Also add an `assertNumQueries` test — should be 4 queries: profiles + closure + overrides + modifiers, independent of room count.

**Step 2: Implement** by extending `effective_stats_for_rooms` into a polymorphic `effective_values_for_rooms(rooms, *, stat_keys=None, resonances=None)`. Exactly-one validation as in Task 4. Use the existing `_bulk_room_profiles_and_ancestors` helper.

**Step 3-5:** standard test / commit cycle.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(locations): bulk effective_values_for_rooms with resonance axis"
```

---

### Task 6: Factories support resonance cascade rows

**Files:**
- Modify: `src/world/locations/factories.py`

Add factory traits or kwargs so tests can write `LocationStatModifierFactory(resonance=R, value=100)` and have `key_type` auto-set to RESONANCE. Recommend a `_create` override following the pattern in `feedback_factory_get_or_create_kwargs.md` (factory kwargs must apply to pre-existing rows when `django_get_or_create` is in play).

```python
class LocationStatModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatModifier

    parent_type = LocationParentType.ROOM
    room_profile = factory.SubFactory(RoomProfileFactory)
    key_type = KeyType.STAT
    stat_key = StatKey.CRIME
    value = 0
    change_per_day = 0
    source = ""

    @factory.lazy_attribute
    def key_type(self):
        # If caller passed resonance, infer RESONANCE; else STAT.
        return KeyType.RESONANCE if self._declarations.get("resonance") else KeyType.STAT
```

Implementor note: `factory.lazy_attribute` referencing `_declarations` is fragile. Simpler: provide two factories or a trait:

```python
class LocationStatModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatModifier
    parent_type = LocationParentType.ROOM
    room_profile = factory.SubFactory(RoomProfileFactory)
    key_type = KeyType.STAT
    stat_key = StatKey.CRIME
    resonance = None
    value = 0
    change_per_day = 0
    source = ""

    class Params:
        resonance_axis = factory.Trait(
            key_type=KeyType.RESONANCE,
            stat_key="",
            resonance=factory.SubFactory("world.magic.factories.ResonanceFactory"),
        )
```

Use: `LocationStatModifierFactory(resonance_axis=True, resonance=predari, value=100)`.

Same for Override factory.

Test, commit.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "test(locations): factory traits for resonance-axis cascade rows"
```

---

## Phase 2: Migrate magic-side usages to the new cascade

Phase 1 has the cascade ready to hold resonance data. Phase 2 redirects writes/reads. **At the end of Phase 2 the old RoomResonance table still exists but is unused — Phase 3 deletes it.**

### Task 7: Rewrite `tag_room_resonance` / `untag_room_resonance` to write cascade rows

**Files:**
- Modify: `src/world/magic/services/gain.py` (or wherever these helpers currently live — grep for the function bodies)
- Modify: `src/world/magic/tests/test_gain_services.py`

**Step 1: Find the current impl**

Run: `grep -rn "def tag_room_resonance" src/world/magic/`

**Step 2: Write a failing test** asserting that `tag_room_resonance(room_profile, resonance)` creates a `LocationStatModifier` row (NOT a `RoomResonance` row anymore):

```python
def test_tag_room_resonance_writes_cascade_row(self):
    from world.locations.constants import KeyType, RESONANCE_DEFAULT_MAGNITUDE
    from world.locations.models import LocationStatModifier
    from world.magic.services.gain import tag_room_resonance

    tag_room_resonance(self.room_profile, self.celestial_resonance)
    row = LocationStatModifier.objects.get(
        room_profile=self.room_profile,
        key_type=KeyType.RESONANCE,
        resonance=self.celestial_resonance,
    )
    assert row.value == RESONANCE_DEFAULT_MAGNITUDE
    assert row.change_per_day == 0
```

**Step 3: Implement**

Rewrite `tag_room_resonance` to call `LocationStatModifier.objects.get_or_create(...)` with `defaults={"value": RESONANCE_DEFAULT_MAGNITUDE, "change_per_day": 0, "source": f"tag_room_resonance:account={set_by.pk if set_by else 'system'}"}`.

Rewrite `untag_room_resonance` to delete the matching cascade row.

**Step 4-5:** Tests, commit.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): tag_room_resonance writes to cascade not RoomResonance"
```

---

### Task 8: Rewrite `get_residence_resonances(sheet)` against the cascade

**Files:**
- Modify: `src/world/magic/services/gain.py`
- Modify: `src/world/magic/tests/test_gain_services.py`

**Step 1: Update the test** to assert that `get_residence_resonances(sheet)` reads from `LocationStatModifier` rows on the residence room, not `RoomResonance`. Make the old tests still pass with the new backing data.

**Step 2: Implement** — query the room's cascade rows with `key_type=RESONANCE` and intersect with `sheet`'s claimed resonances. Use `effective_value(room, resonance=...)` and filter `> 0`, OR query the cascade table directly if performance matters for the daily tick.

Implementor decision point: the per-tick query budget matters here. A direct `.filter(room_profile=..., key_type=RESONANCE, resonance__in=claimed_resonances)` is one query and returns the rows the tick needs. The full `effective_value` walk is overkill for the trickle (we want "what resonances does the room emit," not the cascade-resolved magnitude). Use the direct filter, document why in a comment.

**Step 3-5:** test, commit.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): get_residence_resonances reads from cascade"
```

---

### Task 9: Update `RoomsByPropertyView` to query the cascade

**Files:**
- Modify: `src/world/magic/views.py:1588` (RoomsByPropertyView)
- Modify: `src/world/magic/tests/test_rooms_by_property_view.py`

Read the existing view first to understand the filter shape. Likely query becomes: "rooms whose `room_profile` has a `LocationStatModifier` with `key_type=RESONANCE, resonance__in=...`".

Update API tests to use the cascade-row factory traits. Run the API test suite.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): RoomsByPropertyView queries the cascade"
```

---

### Task 10: Add `source_room_profile` FK on `ResonanceGrant`

**Files:**
- Modify: `src/world/magic/models/grant.py` (ResonanceGrant)
- Create: `src/world/magic/migrations/00XX_resonancegrant_source_room_profile.py`
- Modify: `src/world/magic/tests/test_gain_models.py`

**Step 1: Add the new nullable FK**

```python
source_room_profile = models.ForeignKey(
    "evennia_extensions.RoomProfile",
    null=True,
    blank=True,
    on_delete=models.PROTECT,
    related_name="resonance_grants",
)
```

Keep `source_room_aura_profile` for now — both fields coexist during data migration.

**Step 2: makemigrations / migrate / verify**

```powershell
uv run arx manage makemigrations magic
uv run arx manage migrate magic
echo "yes" | uv run arx test world.magic.tests.test_gain_models
```

**Step 3: Commit**

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): add ResonanceGrant.source_room_profile FK (transitional)"
```

---

### Task 11: Update `residence_trickle_tick` and audit-write paths to populate `source_room_profile`

**Files:**
- Modify: `src/world/magic/services/gain.py`
- Modify: `src/world/magic/services/resonance.py`
- Modify: `src/world/magic/tests/test_gain_tick.py`

Any code that writes `ResonanceGrant(source_room_aura_profile=...)` should now write `source_room_profile=room_aura_profile.room_profile` instead. During this task both fields still exist — write to BOTH so the data is consistent for the upcoming data migration. Add a TODO to remove the dual-write in Task 14.

Actually — simpler — since we're going to migrate-and-drop the old FK in Task 14, only write to the new FK from here on. The data migration in Task 14 backfills old rows.

Test, commit.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): residence trickle writes source_room_profile on ResonanceGrant"
```

---

## Phase 3: Data migration and old-model retirement

All writers now go to the new cascade. Now: migrate historical data, then drop the old tables.

### Task 12: Data migration — `RoomResonance` rows → `LocationStatModifier` rows

**Files:**
- Create: `src/world/magic/migrations/00XX_migrate_roomresonance_to_cascade.py` (data migration)

This is a `RunPython` migration that, for each `RoomResonance` row:
- Looks up the `RoomProfile` (via the `RoomAuraProfile` join)
- Creates a `LocationStatModifier` with `parent_type=ROOM, room_profile=…, key_type=RESONANCE, resonance=…, value=RESONANCE_DEFAULT_MAGNITUDE, change_per_day=0, source=f"migrated_from_roomresonance:set_by={row.set_by_id or 'none'}"`
- Uses `get_or_create` to make the migration idempotent

```python
from django.db import migrations
from django.utils import timezone


def migrate_roomresonance_to_cascade(apps, schema_editor):
    RoomResonance = apps.get_model("magic", "RoomResonance")
    LocationStatModifier = apps.get_model("locations", "LocationStatModifier")

    for row in RoomResonance.objects.select_related("room_aura_profile", "resonance").all():
        profile_id = row.room_aura_profile.room_profile_id
        LocationStatModifier.objects.get_or_create(
            parent_type="ROOM",
            room_profile_id=profile_id,
            key_type="resonance",
            resonance_id=row.resonance_id,
            defaults={
                "value": 100,
                "change_per_day": 0,
                "source": f"migrated_from_roomresonance:set_by={row.set_by_id or 'none'}",
                "applied_at": row.set_at or timezone.now(),
            },
        )


def reverse_unsupported(apps, schema_editor):
    raise RuntimeError("RoomResonance → cascade migration is one-way.")


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "00XX_resonancegrant_source_room_profile"),
        ("locations", "0005_locationstatoverride_resonance"),  # whatever Task 3 produced
    ]
    operations = [
        migrations.RunPython(migrate_roomresonance_to_cascade, reverse_unsupported),
    ]
```

Implementor notes:
- Use `apps.get_model(...)` — never import the live model classes in data migrations.
- The TextChoices VALUES are what gets written (`"ROOM"`, `"resonance"`), not the enum members. Verify by inspecting the existing locations migrations for the values used.
- The `RESONANCE_DEFAULT_MAGNITUDE` constant value (100) is hardcoded here because data migrations should not import runtime constants — the value gets baked in.
- This migration must run **after** the cascade resonance field exists (Phase 1 migrations) and **before** any RoomResonance teardown.

**Step 1: Add migration**

**Step 2: Test by running**

```powershell
uv run arx manage migrate magic
echo "yes" | uv run arx test world.magic
```

**Step 3: Commit**

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): data-migrate RoomResonance rows to locations cascade"
```

---

### Task 13: Data migration — `ResonanceGrant.source_room_aura_profile` → `source_room_profile`

Mirror Task 12 for the audit FK. For each `ResonanceGrant` with `source_room_aura_profile_id IS NOT NULL`, set `source_room_profile_id = room_aura_profile.room_profile_id`. Idempotent.

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(magic): data-migrate ResonanceGrant audit FK to source_room_profile"
```

---

### Task 14: Update `ResonanceGrant` CheckConstraints and drop `source_room_aura_profile`

**Files:**
- Modify: `src/world/magic/models/grant.py`
- Create: migration

The existing CheckConstraints enforce "if source=ROOM_RESIDENCE then source_room_aura_profile IS NOT NULL" — that constraint needs to be replaced with "...source_room_profile IS NOT NULL." Then the old field is removed.

```powershell
uv run arx manage makemigrations magic
uv run arx manage migrate magic
echo "yes" | uv run arx test world.magic
git -C C:/Users/apost/PycharmProjects/arxii commit -m "refactor(magic): drop ResonanceGrant.source_room_aura_profile, point audit at RoomProfile"
```

---

### Task 15: Drop `RoomAuraProfile` and `RoomResonance` models

**Files:**
- Modify: `src/world/magic/models/room_aura.py` — delete both classes (or delete the whole file if nothing else lives in it)
- Modify: `src/world/magic/models/__init__.py` — remove exports
- Modify: `src/world/magic/admin.py` — remove `RoomAuraProfileAdmin`
- Modify: `src/world/magic/factories.py` — remove `RoomAuraProfileFactory` and any RoomResonance factory
- Update: any remaining test references (should be zero by this point — if not, those tests need rewriting against the cascade first)
- Create: migration deleting the two models

**Step 1: grep for residual references**

Run: `grep -rn "RoomAuraProfile\|RoomResonance" src/ docs/`
Expected: should turn up only the models being deleted + their factory + admin + docs comments. If there are live consumers still using these, **stop** and rewrite those consumers first.

**Step 2: Delete the code and generate the migration**

```powershell
uv run arx manage makemigrations magic
```

Expected: a migration with `DeleteModel("RoomResonance")` and `DeleteModel("RoomAuraProfile")`.

**Step 3: Apply, test, commit**

```powershell
uv run arx manage migrate magic
echo "yes" | uv run arx test world.magic
git -C C:/Users/apost/PycharmProjects/arxii commit -m "refactor(magic): drop RoomAuraProfile and RoomResonance — replaced by cascade"
```

---

## Phase 4: Rename for honesty

The models are no longer stat-only. Rename to reflect that.

### Task 16: Rename `LocationStatModifier` → `LocationValueModifier`, `LocationStatOverride` → `LocationValueOverride`

**Files:**
- Modify: `src/world/locations/models.py` — class renames
- Modify: every importer (grep first to enumerate)
- Modify: `src/world/locations/admin.py`, `factories.py`, `services.py`, `tests/`
- Modify: any FK string references `"locations.LocationStatModifier"` → `"locations.LocationValueModifier"`
- Modify: docstrings, CLAUDE.md
- Create: migration with `RenameModel` for both

**Step 1: Enumerate all references**

Run: `grep -rn "LocationStatModifier\|LocationStatOverride" src/ docs/`

**Step 2: Rename via find/replace** in each file. Be precise — these are exact class names, no risk of false matches.

**Step 3: Generate migration**

```powershell
uv run arx manage makemigrations locations
```

Expected: a migration with `migrations.RenameModel("LocationStatModifier", "LocationValueModifier")` and the override version.

**Step 4: Apply, test, commit**

```powershell
uv run arx manage migrate locations
echo "yes" | uv run arx test world.locations world.magic
git -C C:/Users/apost/PycharmProjects/arxii commit -m "refactor(locations): rename LocationStat* → LocationValue*"
```

---

### Task 17: Rename `effective_stat` → `effective_value` as the canonical entry point

The polymorphic `effective_value` already exists (Task 4 added it alongside `effective_stat` as a thin wrapper). Now delete the wrapper and update all callers.

**Step 1: grep for callers**

Run: `grep -rn "effective_stat(" src/`

**Step 2: Update each caller** to use `effective_value(room, stat_key=...)` keyword form.

**Step 3: Delete the wrapper** in `services.py`. Same for `effective_stats_for_rooms` → `effective_values_for_rooms`.

**Step 4: Test, commit**

```powershell
echo "yes" | uv run arx test world.locations world.magic
git -C C:/Users/apost/PycharmProjects/arxii commit -m "refactor(locations): rename effective_stat → effective_value at all callsites"
```

---

### Task 18: Update CLAUDE.md and systems docs

**Files:**
- Modify: `src/world/locations/CLAUDE.md` — describe the resonance axis, update model names, mention the magic.Resonance dep
- Modify: `src/world/magic/CLAUDE.md` — remove `RoomAuraProfile`/`RoomResonance` sections, note that room-aura data lives in `locations` cascade now
- Modify: `docs/systems/INDEX.md` — locations section to mention dual-axis, magic section to drop the aura models from the model listing
- Modify: `docs/systems/magic.md` if it duplicates the model listing

Commit:

```powershell
git -C C:/Users/apost/PycharmProjects/arxii commit -m "docs: update CLAUDE.md and systems index for cascade unification"
```

---

## Phase 5: Verification

### Task 19: Full no-keepdb regression run

Per CLAUDE.md: "Before pushing anything that touches migrations, factories, service functions that call create_object, typeclass initialization, or test settings, run the full suite WITHOUT --keepdb."

This plan touches all of those. Run the full suite from a fresh DB:

```powershell
echo "yes" | uv run arx test
```

Expected: full suite PASS. If anything fails, root-cause it — don't assume `--keepdb` masking, this run is the truth.

If everything passes, the branch is ready for PR.

---

## Out of scope (follow-up plan)

The **technique pre-cast backfire trigger** — described in the conversation as the original motivating use case (Bob's 5000 predari abyssal clashing with the Cathedral's 1000 celestial) — is NOT in this plan. It depends on:

1. This cascade unification landing (it reads via `effective_value(room, resonance=...)`)
2. A formula spec — how does (character resonance × abyssal aura) × (technique resonance) compare to (room cascade celestial value) to produce a severity number?
3. Consequence routing — does backfire reuse the soulfray mishap path, the AnimaRitualPerformance mishap pool, or a new "environmental backlash" `ConsequenceEffect` set?
4. A `perform_check` integration — is the character given a save against the backfire? What CheckType? What difficulty curve?

Once this plan lands, the trigger can be designed as a focused follow-up. Open a brainstorming session on the formula + consequence shape, then plan the trigger implementation against the now-unified cascade reads.

---

## Skills referenced

- `superpowers:executing-plans` — execute this plan task-by-task
- `superpowers:test-driven-development` — TDD discipline for each task (write failing test, run, implement, run, commit)
- `superpowers:verification-before-completion` — before claiming the plan complete, run the no-keepdb regression in Task 19
