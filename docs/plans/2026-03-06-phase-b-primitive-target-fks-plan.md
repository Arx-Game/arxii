# Phase B: Primitive Target FKs — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `target_capability`, `target_check_type`, `target_damage_type` FKs to ModifierTarget; merge duplicate `conditions.CheckType` into `checks.CheckType`; fix `DamageType.resonance` to point to `magic.Resonance`.

**Architecture:** Follow the Phase A pattern — domain models stay where they are, ModifierTarget gets OneToOneField FKs pointing to them. The duplicate `conditions.CheckType` (simple name/desc lookup) gets deleted in favor of the full `checks.CheckType` model.

**Tech Stack:** Django, Evennia, FactoryBoy, Django REST Framework

**Design doc:** `docs/plans/2026-03-06-phase-b-primitive-target-fks-design.md`

---

## Context for the Implementer

### What is ModifierTarget?

`ModifierTarget` (mechanics app) is the unified registry of "things that can be modified on a character." Each row has a `category` FK to `ModifierCategory` and optional OneToOneField FKs to domain models:
- `target_trait` → `traits.Trait` (for stat-category targets)
- `target_affinity` → `magic.Affinity` (for affinity-category targets, added in Phase A)
- `target_resonance` → `magic.Resonance` (for resonance-category targets, added in Phase A)

We're adding three more:
- `target_capability` → `conditions.CapabilityType`
- `target_check_type` → `checks.CheckType`
- `target_damage_type` → `conditions.DamageType`

### The CheckType Duplication Problem

Two `CheckType` models exist:
1. **`conditions.CheckType`** — Simple: `name`, `description`. Used by condition effects.
2. **`checks.CheckType`** — Full: `name`, `category`, `description`, `is_active`, `display_order`, plus trait/aspect weights. Used by check resolution.

They represent the same domain concept. We delete `conditions.CheckType` and re-point all FKs to `checks.CheckType`.

### The DamageType.resonance FK Problem

`DamageType.resonance` is a OneToOneField to `mechanics.ModifierTarget`. After Phase A extracted resonances into `magic.Resonance`, this FK should point to `magic.Resonance` directly.

### Running Tests

```bash
# Run a specific app's tests:
echo "yes" | arx test --settings settings.test_settings world.conditions

# Run all tests:
echo "yes" | arx test --settings settings.test_settings
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `src/world/mechanics/models.py` | ModifierTarget model — add new FKs here |
| `src/world/conditions/models.py` | CapabilityType, DamageType, conditions.CheckType (delete), effect models |
| `src/world/checks/models.py` | checks.CheckType — the surviving CheckType |
| `src/world/conditions/services.py` | Uses conditions.CheckType — switch import |
| `src/world/conditions/factories.py` | conditions.CheckTypeFactory (delete), ConditionCheckModifierFactory (update) |
| `src/world/conditions/admin.py` | Registers conditions.CheckType (remove registration) |
| `src/world/conditions/serializers.py` | CheckTypeSerializer using conditions.CheckType (remove) |
| `src/world/conditions/views.py` | CheckTypeViewSet using conditions.CheckType (remove) |
| `src/world/conditions/urls.py` | Routes for check-types endpoint (remove) |
| `src/world/conditions/tests/test_services.py` | Imports conditions.CheckTypeFactory (switch) |
| `src/world/mechanics/factories.py` | ModifierTargetFactory — no changes needed (FKs are nullable) |

---

## Task 1: Add `target_capability` FK to ModifierTarget

**Files:**
- Modify: `src/world/mechanics/models.py`
- Test: `src/world/mechanics/tests/test_models.py`

**Step 1: Write the test**

Add to `src/world/mechanics/tests/test_models.py`:

```python
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory


class ModifierTargetCapabilityFKTest(TestCase):
    """Tests for ModifierTarget.target_capability FK."""

    @classmethod
    def setUpTestData(cls):
        cls.capability = CapabilityTypeFactory(name="movement")
        cls.category = ModifierCategoryFactory(name="capability")

    def test_modifier_target_links_to_capability(self):
        """ModifierTarget can point to a CapabilityType via target_capability."""
        mt = ModifierTargetFactory(
            name="movement",
            category=self.category,
            target_capability=self.capability,
        )
        self.assertEqual(mt.target_capability, self.capability)

    def test_reverse_accessor(self):
        """CapabilityType.modifier_target reverse accessor works."""
        mt = ModifierTargetFactory(
            name="movement",
            category=self.category,
            target_capability=self.capability,
        )
        self.assertEqual(self.capability.modifier_target, mt)

    def test_nullable(self):
        """target_capability is null by default."""
        mt = ModifierTargetFactory(name="generic", category=self.category)
        self.assertIsNone(mt.target_capability)
```

**Step 2: Run to verify failure**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

Expected: FAIL — `target_capability` field doesn't exist yet.

**Step 3: Add the FK to ModifierTarget**

In `src/world/mechanics/models.py`, add to the `ModifierTarget` class after `target_resonance`:

```python
    target_capability = models.OneToOneField(
        "conditions.CapabilityType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The capability this target represents (capability category only).",
    )
```

Also remove (or update) the comment on line ~107 that says `# target_check_type: FK to conditions.CheckType — roll modifier system` since we're implementing these now.

**Step 4: Run test to verify pass**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

**Step 5: Commit**

```bash
git add src/world/mechanics/models.py src/world/mechanics/tests/test_models.py
git commit -m "feat: add target_capability FK to ModifierTarget"
```

---

## Task 2: Add `target_check_type` FK to ModifierTarget

**Files:**
- Modify: `src/world/mechanics/models.py`
- Test: `src/world/mechanics/tests/test_models.py`

**Step 1: Write the test**

Add to `src/world/mechanics/tests/test_models.py`:

```python
from world.checks.factories import CheckTypeFactory as ChecksCheckTypeFactory


class ModifierTargetCheckTypeFKTest(TestCase):
    """Tests for ModifierTarget.target_check_type FK."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = ChecksCheckTypeFactory(name="stealth")
        cls.category = ModifierCategoryFactory(name="check")

    def test_modifier_target_links_to_check_type(self):
        """ModifierTarget can point to a checks.CheckType via target_check_type."""
        mt = ModifierTargetFactory(
            name="stealth",
            category=self.category,
            target_check_type=self.check_type,
        )
        self.assertEqual(mt.target_check_type, self.check_type)

    def test_reverse_accessor(self):
        """CheckType.modifier_target reverse accessor works."""
        mt = ModifierTargetFactory(
            name="stealth",
            category=self.category,
            target_check_type=self.check_type,
        )
        self.assertEqual(self.check_type.modifier_target, mt)

    def test_nullable(self):
        """target_check_type is null by default."""
        mt = ModifierTargetFactory(name="generic2", category=self.category)
        self.assertIsNone(mt.target_check_type)
```

**Step 2: Run to verify failure**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

**Step 3: Add the FK**

In `src/world/mechanics/models.py`, add after `target_capability`:

```python
    target_check_type = models.OneToOneField(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The check type this target represents (check category only).",
    )
```

**Step 4: Run test to verify pass**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

**Step 5: Commit**

```bash
git add src/world/mechanics/models.py src/world/mechanics/tests/test_models.py
git commit -m "feat: add target_check_type FK to ModifierTarget"
```

---

## Task 3: Add `target_damage_type` FK to ModifierTarget

**Files:**
- Modify: `src/world/mechanics/models.py`
- Test: `src/world/mechanics/tests/test_models.py`

**Step 1: Write the test**

Add to `src/world/mechanics/tests/test_models.py`:

```python
from world.conditions.factories import DamageTypeFactory


class ModifierTargetDamageTypeFKTest(TestCase):
    """Tests for ModifierTarget.target_damage_type FK."""

    @classmethod
    def setUpTestData(cls):
        cls.damage_type = DamageTypeFactory(name="fire")
        cls.category = ModifierCategoryFactory(name="resistance")

    def test_modifier_target_links_to_damage_type(self):
        """ModifierTarget can point to a DamageType via target_damage_type."""
        mt = ModifierTargetFactory(
            name="fire_resistance",
            category=self.category,
            target_damage_type=self.damage_type,
        )
        self.assertEqual(mt.target_damage_type, self.damage_type)

    def test_reverse_accessor(self):
        """DamageType.modifier_target reverse accessor works."""
        mt = ModifierTargetFactory(
            name="fire_resistance",
            category=self.category,
            target_damage_type=self.damage_type,
        )
        self.assertEqual(self.damage_type.modifier_target, mt)

    def test_nullable(self):
        """target_damage_type is null by default."""
        mt = ModifierTargetFactory(name="generic3", category=self.category)
        self.assertIsNone(mt.target_damage_type)
```

**Step 2: Run to verify failure**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

**Step 3: Add the FK**

In `src/world/mechanics/models.py`, add after `target_check_type`:

```python
    target_damage_type = models.OneToOneField(
        "conditions.DamageType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The damage type this target represents (resistance category only).",
    )
```

**Step 4: Run test to verify pass**

```bash
echo "yes" | arx test --settings settings.test_settings world.mechanics.tests.test_models
```

**Step 5: Commit**

```bash
git add src/world/mechanics/models.py src/world/mechanics/tests/test_models.py
git commit -m "feat: add target_damage_type FK to ModifierTarget"
```

---

## Task 4: Fix `DamageType.resonance` FK to point to `magic.Resonance`

**Files:**
- Modify: `src/world/conditions/models.py`
- Test: `src/world/conditions/tests/test_services.py` (or a new test file)

**Step 1: Write the test**

Add a test. You can add it to `src/world/conditions/tests/test_services.py` or create a small dedicated test. Here we'll add it at the top of test_services:

```python
from world.magic.factories import ResonanceModifierTargetFactory


class DamageTypeResonanceFKTest(TestCase):
    """Tests for DamageType.resonance FK pointing to magic.Resonance."""

    def test_damage_type_links_to_resonance(self):
        """DamageType.resonance points to a magic.Resonance model."""
        from world.magic.models import Resonance
        resonance = ResonanceModifierTargetFactory(name="Fire")
        # ResonanceModifierTargetFactory creates a ModifierTarget, not a Resonance.
        # We need to use the Resonance model directly.
        # Actually, after Phase A the magic app has proper Resonance/Affinity models.
        # Let's import and use them.
        from world.magic.factories import ResonanceFactory
        res = ResonanceFactory(name="FireRes")
        dt = DamageTypeFactory(name="fire_dt", resonance=res)
        self.assertEqual(dt.resonance, res)
        self.assertEqual(res.damage_type, dt)
```

Wait — we need to check if `ResonanceFactory` exists. Looking at the magic factories, I see `ResonanceModifierTargetFactory` but that creates a ModifierTarget, not a `magic.Resonance`. Let me check for a proper ResonanceFactory.

Actually, from the Phase A context, `Resonance` and `Affinity` models were created in the magic app. Let me check for their factories. The conversation summary mentions `ResonanceFactory` was used. Let me verify.

**Step 1 (revised): Write the test**

First, check that `ResonanceFactory` and `AffinityFactory` exist in `src/world/magic/factories.py`. If not, they need to be created (they should exist from Phase A). Use them:

```python
class DamageTypeResonanceFKTest(TestCase):
    """Tests for DamageType.resonance FK pointing to magic.Resonance."""

    def test_damage_type_links_to_resonance(self):
        """DamageType.resonance points to a magic.Resonance."""
        from world.magic.factories import AffinityFactory, ResonanceFactory
        affinity = AffinityFactory(name="Celestial")
        resonance = ResonanceFactory(name="Fire", affinity=affinity)
        dt = DamageTypeFactory(name="fire_dt", resonance=resonance)
        self.assertEqual(dt.resonance, resonance)

    def test_reverse_accessor(self):
        """Resonance.damage_type reverse accessor works."""
        from world.magic.factories import AffinityFactory, ResonanceFactory
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(name="Lightning", affinity=affinity)
        dt = DamageTypeFactory(name="lightning_dt", resonance=resonance)
        self.assertEqual(resonance.damage_type, dt)

    def test_null_resonance(self):
        """DamageType with no associated resonance."""
        dt = DamageTypeFactory(name="physical_dt")
        self.assertIsNone(dt.resonance)
```

**Step 2: Run to verify failure**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions.tests.test_services.DamageTypeResonanceFKTest
```

Expected: FAIL — resonance FK still points to ModifierTarget, not Resonance.

**Step 3: Change the FK**

In `src/world/conditions/models.py`, change `DamageType.resonance`:

```python
# Before:
    resonance = models.OneToOneField(
        "mechanics.ModifierTarget",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="damage_type",
        help_text="Associated magical resonance (category='resonance'), if any",
    )

# After:
    resonance = models.OneToOneField(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="damage_type",
        help_text="Associated magical resonance, if any",
    )
```

**Step 4: Run test to verify pass**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions.tests.test_services.DamageTypeResonanceFKTest
```

**Step 5: Commit**

```bash
git add src/world/conditions/models.py src/world/conditions/tests/test_services.py
git commit -m "fix: DamageType.resonance FK points to magic.Resonance instead of ModifierTarget"
```

---

## Task 5: Merge `conditions.CheckType` into `checks.CheckType` — Models

This is the biggest task. We delete `conditions.CheckType` and re-point three FKs.

**Files:**
- Modify: `src/world/conditions/models.py`

**Step 1: Re-point FKs in conditions/models.py**

Change three FK references from `CheckType` (local model) to `"checks.CheckType"`:

1. `ConditionCheckModifier.check_type` — currently `models.ForeignKey(CheckType, ...)`. Change to `models.ForeignKey("checks.CheckType", ...)`.

2. `ConditionTemplate.cure_check_type` — currently `models.ForeignKey(CheckType, ...)`. Change to `models.ForeignKey("checks.CheckType", ...)`.

3. `ConditionStage.resist_check_type` — currently `models.ForeignKey(CheckType, ...)`. Change to `models.ForeignKey("checks.CheckType", ...)`.

4. Update `ConditionCheckModifier.NaturalKeyConfig.dependencies` — change `"conditions.CheckType"` to `"checks.CheckType"`.

5. Delete the `conditions.CheckType` class entirely from the file.

6. Remove `CheckType` from any `__all__` if present (it's not, but check).

**Step 2: Run tests to verify the model change works**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

Expected: FAIL — tests still import `CheckType` and `CheckTypeFactory` from conditions.

**Step 3: Commit the model change**

```bash
git add src/world/conditions/models.py
git commit -m "refactor: delete conditions.CheckType, re-point FKs to checks.CheckType"
```

---

## Task 6: Merge `conditions.CheckType` — Factories

**Files:**
- Modify: `src/world/conditions/factories.py`

**Step 1: Update the factories**

In `src/world/conditions/factories.py`:

1. Remove the `CheckType` import from the conditions models import block.
2. Delete the `CheckTypeFactory` class entirely.
3. Change `ConditionCheckModifierFactory.check_type` from `factory.SubFactory(CheckTypeFactory)` to `factory.SubFactory("world.checks.factories.CheckTypeFactory")`.

The updated import block:

```python
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)
```

The updated `ConditionCheckModifierFactory`:

```python
class ConditionCheckModifierFactory(DjangoModelFactory):
    """Factory for ConditionCheckModifier."""

    class Meta:
        model = ConditionCheckModifier

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    modifier_value = -10
    scales_with_severity = False
```

**Step 2: Run tests**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

Expected: FAIL — test_services.py still imports `CheckTypeFactory` from conditions.

**Step 3: Commit**

```bash
git add src/world/conditions/factories.py
git commit -m "refactor: delete conditions.CheckTypeFactory, use checks.CheckTypeFactory"
```

---

## Task 7: Merge `conditions.CheckType` — Tests

**Files:**
- Modify: `src/world/conditions/tests/test_services.py`

**Step 1: Update imports**

In `src/world/conditions/tests/test_services.py`, change the import:

```python
# Before:
from world.conditions.factories import (
    CapabilityTypeFactory,
    CheckTypeFactory,
    ...
)

# After:
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ...
)
```

Remove `CheckTypeFactory` from the conditions.factories import list. Add a separate import from checks.factories.

**Step 2: Run tests**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

Expected: PASS — all conditions tests should pass now.

**Step 3: Commit**

```bash
git add src/world/conditions/tests/test_services.py
git commit -m "refactor: conditions tests use checks.CheckTypeFactory"
```

---

## Task 8: Merge `conditions.CheckType` — Admin

**Files:**
- Modify: `src/world/conditions/admin.py`

**Step 1: Update admin.py**

1. Remove `CheckType` from the conditions models import.
2. Delete the `CheckTypeAdmin` class and its `@admin.register(CheckType)` decorator.
3. The `ConditionCheckModifierInline` uses `autocomplete_fields = ["check_type", "stage"]` — this still works because the FK now points to `checks.CheckType` and `checks.admin.py` already registers `CheckType` with `search_fields`.

Updated import:

```python
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)
```

**Step 2: Run tests (admin doesn't have dedicated tests, but verify nothing breaks)**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

**Step 3: Commit**

```bash
git add src/world/conditions/admin.py
git commit -m "refactor: remove conditions.CheckType from admin (now in checks admin)"
```

---

## Task 9: Merge `conditions.CheckType` — Serializers, Views, URLs

**Files:**
- Modify: `src/world/conditions/serializers.py`
- Modify: `src/world/conditions/views.py`
- Modify: `src/world/conditions/urls.py`

**Step 1: Update serializers.py**

Remove `CheckType` from the models import and delete the `CheckTypeSerializer` class.

Updated import:

```python
from world.conditions.models import (
    CapabilityType,
    ConditionCategory,
    ConditionInstance,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)
```

**Step 2: Update views.py**

1. Remove `CheckType` from the conditions models import.
2. Remove `CheckTypeSerializer` from the serializers import.
3. Delete the `CheckTypeViewSet` class.

Updated model import:

```python
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionTemplate,
    DamageType,
)
```

Updated serializers import:

```python
from world.conditions.serializers import (
    CapabilityTypeSerializer,
    ConditionCategorySerializer,
    ConditionInstanceObserverSerializer,
    ConditionInstanceSerializer,
    ConditionTemplateDetailSerializer,
    ConditionTemplateSerializer,
    DamageTypeSerializer,
)
```

**Step 3: Update urls.py**

Remove `CheckTypeViewSet` from the import and remove its router registration.

Updated import:

```python
from world.conditions.views import (
    CapabilityTypeViewSet,
    CharacterConditionsViewSet,
    ConditionCategoryViewSet,
    ConditionTemplateViewSet,
    DamageTypeViewSet,
)
```

Remove this line:
```python
router.register("check-types", CheckTypeViewSet, basename="check-type")
```

**Step 4: Run tests**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

**Step 5: Commit**

```bash
git add src/world/conditions/serializers.py src/world/conditions/views.py src/world/conditions/urls.py
git commit -m "refactor: remove conditions.CheckType from serializers, views, URLs"
```

---

## Task 10: Update conditions services.py import

**Files:**
- Modify: `src/world/conditions/services.py`

**Step 1: Update import**

Change the import in `src/world/conditions/services.py`:

```python
# Before (line 31):
from world.conditions.models import (
    CapabilityType,
    CheckType,
    ...
)

# After:
from world.checks.models import CheckType
from world.conditions.models import (
    CapabilityType,
    ...
)
```

Remove `CheckType` from the `conditions.models` import block. Add a separate import from `checks.models`.

**Step 2: Run tests**

```bash
echo "yes" | arx test --settings settings.test_settings world.conditions
```

**Step 3: Commit**

```bash
git add src/world/conditions/services.py
git commit -m "refactor: conditions services imports CheckType from checks app"
```

---

## Task 11: Remove stale future-FK comments from ModifierTarget

**Files:**
- Modify: `src/world/mechanics/models.py`

**Step 1: Update comments**

In `src/world/mechanics/models.py`, find the comment block around lines 106-110:

```python
    # Future target FKs — added when their systems are built:
    # target_capability: FK to conditions.CapabilityType — capability modifier system
    # target_check_type: FK to conditions.CheckType — roll modifier system
    # target_condition: FK to conditions.ConditionTemplate — condition modifier system
    # See TECH_DEBT.md §"Future Target FKs" for full tracking list.
```

Replace with:

```python
    # Future target FKs — added when their systems are built:
    # target_condition: FK to conditions.ConditionTemplate — condition modifier system
    # See TECH_DEBT.md §"Future Target FKs" for full tracking list.
```

(Remove the lines for `target_capability` and `target_check_type` since we just implemented them.)

**Step 2: Commit**

```bash
git add src/world/mechanics/models.py
git commit -m "chore: remove stale future-FK comments for implemented FKs"
```

---

## Task 12: Update TECH_DEBT.md

**Files:**
- Modify: `src/world/mechanics/TECH_DEBT.md`

**Step 1: Mark completed items**

In the "Future Target FKs" table, update:

| Category | Future FK | Blocked On |
|----------|----------|------------|
| ~~capability~~ | ~~target_capability~~ | **DONE** (Phase B) |
| ~~roll_modifier~~ | ~~target_check_type~~ | **DONE** (Phase B) |
| ~~resistance~~ | ~~target_damage_type~~ | **DONE** (Phase B) |

Also update the resonance row if not already done:

| ~~resonance~~ | ~~target_resonance~~ | **DONE** (Phase A) |

**Step 2: Commit**

```bash
git add src/world/mechanics/TECH_DEBT.md
git commit -m "docs: mark Phase B target FKs as done in TECH_DEBT.md"
```

---

## Task 13: Update CLAUDE.md docs

**Files:**
- Modify: `src/world/mechanics/CLAUDE.md`
- Modify: `src/world/magic/CLAUDE.md`

**Step 1: Update mechanics CLAUDE.md**

In the ModifierTarget field table, add the new FK fields:

```markdown
| target_capability | OneToOne(CapabilityType, null) | FK to the CapabilityType this target represents |
| target_check_type | OneToOne(CheckType, null) | FK to the CheckType this target represents |
| target_damage_type | OneToOne(DamageType, null) | FK to the DamageType this target represents (resistance) |
```

**Step 2: Update magic CLAUDE.md**

Update the note about `DamageType.resonance` if it mentions ModifierTarget. The conditions app CLAUDE.md may also need updating if it exists. Check and update as needed.

**Step 3: Commit**

```bash
git add src/world/mechanics/CLAUDE.md src/world/magic/CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase B changes"
```

---

## Task 14: Regenerate migrations and full test run

**IMPORTANT:** This is a destructive step. We delete ALL migrations, drop+recreate the DB, regenerate, and add materialized view RunSQL operations.

**Step 1: Delete all existing migrations**

```bash
find src -path "*/migrations/0*.py" -delete
```

**Step 2: Drop and recreate the database**

```bash
"/c/Program Files/PostgreSQL/17/bin/psql.exe" -p 5433 -U postgres -c "DROP DATABASE IF EXISTS arxii;" && \
"/c/Program Files/PostgreSQL/17/bin/psql.exe" -p 5433 -U postgres -c "CREATE DATABASE arxii OWNER arxii;"
```

Password: `reddawn25`

**Step 3: Regenerate all migrations**

```bash
arx manage makemigrations
```

If this prompts for anything, accept defaults. This should create fresh 0001_initial.py for each app.

**Step 4: Add materialized view RunSQL operations**

Two apps need manual RunSQL additions:

1. **`src/world/areas/migrations/0001_initial.py`** — Add at the end of `operations`:

```python
migrations.RunSQL(
    sql="""
        CREATE MATERIALIZED VIEW IF NOT EXISTS areas_areaclosure AS
        WITH RECURSIVE closure(ancestor_id, descendant_id, depth) AS (
            SELECT id, id, 0 FROM areas_area
            UNION ALL
            SELECT c.ancestor_id, a.id, c.depth + 1
            FROM closure c
            JOIN areas_area a ON a.parent_id = c.descendant_id
        )
        SELECT
            row_number() OVER () AS id,
            ancestor_id,
            descendant_id,
            depth
        FROM closure;

        CREATE UNIQUE INDEX IF NOT EXISTS areas_areaclosure_pkey
            ON areas_areaclosure (id);
        CREATE INDEX IF NOT EXISTS areas_areaclosure_ancestor
            ON areas_areaclosure (ancestor_id);
        CREATE INDEX IF NOT EXISTS areas_areaclosure_descendant
            ON areas_areaclosure (descendant_id);
    """,
    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS areas_areaclosure;",
),
```

2. **`src/world/codex/migrations/0002_initial.py`** (or whichever migration has SubjectBreadcrumb) — Add RunSQL for the breadcrumb materialized view. Check the existing migration file from main branch for the exact SQL.

**Step 5: Apply migrations**

```bash
DJANGO_SETTINGS_MODULE=server.conf.settings python -c "
import django; django.setup()
from django.core.management import call_command
call_command('migrate', '--run-syncdb')
"
```

Or use: `echo "yes" | arx manage migrate`

**Step 6: Run full test suite**

```bash
echo "yes" | arx test --settings settings.test_settings
```

Expected: All tests pass.

**Step 7: Stage and commit**

Stage all migration files and any files touched by ruff auto-fix:

```bash
git add src/*/migrations/*.py src/world/*/migrations/*.py
git commit -m "chore: regenerate all migrations for Phase B"
```

---

## Task 15: Run ruff and final verification

**Step 1: Run ruff on all changed files**

```bash
ruff check src/world/conditions/ src/world/mechanics/ src/world/checks/ --fix
ruff format src/world/conditions/ src/world/mechanics/ src/world/checks/
```

**Step 2: Run full test suite one more time**

```bash
echo "yes" | arx test --settings settings.test_settings
```

**Step 3: Commit any ruff fixes**

```bash
git add -u
git commit -m "style: ruff fixes for Phase B"
```
