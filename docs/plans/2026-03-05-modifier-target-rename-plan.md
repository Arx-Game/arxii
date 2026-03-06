# ModifierType → ModifierTarget Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `ModifierType` to `ModifierTarget`, add `target_trait` FK to `Trait`, eliminate string-based modifier lookups, and stub unfinished consumers.

**Architecture:** Codebase-wide rename (93 files), new FK on renamed model, service layer rewrite removing string lookups in favor of FK-based resolution. Dev-only DB wipe and fixture reload.

**Tech Stack:** Django ORM, SharedMemoryModel, FactoryBoy, fixtures with natural keys.

---

## Important Notes

- **This is a dev-only change.** No production data exists. We will wipe the DB and reload from fixtures.
- **The rename is atomic.** Steps 1-3 must all complete before tests can pass — renaming the model breaks every import until all references are updated.
- **Fixtures are gitignored.** Fixture changes are local-only, created for `arx manage loaddata`.
- **Run command:** `arx test <app>` runs tests. Use `echo "yes" |` prefix if DB prompt appears.
- **Migration squash:** After model changes, delete all existing migrations for affected apps and run `arx manage makemigrations <app>` to create a fresh `0001_initial.py`.

---

## Task 1: Rename Model and All References in Mechanics App

The core rename. Changes every class, import, variable, and string in the mechanics app.

**Files to modify:**
- `src/world/mechanics/models.py`
- `src/world/mechanics/admin.py`
- `src/world/mechanics/factories.py`
- `src/world/mechanics/serializers.py`
- `src/world/mechanics/services.py`
- `src/world/mechanics/views.py`
- `src/world/mechanics/urls.py`
- `src/world/mechanics/CLAUDE.md`
- `src/world/mechanics/TECH_DEBT.md`

**Renames:**
- `ModifierType` → `ModifierTarget` (class name)
- `ModifierTypeManager` → `ModifierTargetManager` (manager class)
- `ModifierTypeFactory` → `ModifierTargetFactory` (factory class)
- `ModifierTypeSerializer` → `ModifierTargetSerializer` (serializer class)
- `ModifierTypeListSerializer` → `ModifierTargetListSerializer` (serializer class)
- `ModifierTypeFilter` → `ModifierTargetFilter` (filter class)
- `ModifierTypeViewSet` → `ModifierTargetViewSet` (viewset class)
- `ModifierTypeAdmin` → `ModifierTargetAdmin` (admin class)
- `ModifierCategory.types` related_name → `targets`
- `ModifierSource.modifier_type` property → `modifier_target`
- `CharacterModifier.modifier_type` property → `modifier_target`
- `ModifierTypeType` TYPE_CHECKING alias → `ModifierTargetType`
- All docstrings and comments mentioning `ModifierType`

**In models.py specifically:**
- Rename the class and manager
- Change `ModifierCategory` related_name from `"types"` to `"targets"`
- Rename both `modifier_type` properties on `ModifierSource` and `CharacterModifier` to `modifier_target`
- Update the TYPE_CHECKING import alias
- Update all docstrings

**In services.py:**
- Rename all `modifier_type` parameters to `modifier_target`
- Rename `ModifierType` imports to `ModifierTarget`
- Update `ModifierBreakdown` field references (`modifier_type_name` → `modifier_target_name`) — check `types.py` too
- **Do NOT remove `get_modifier_for_character` yet** — that's Task 4

**In serializers.py:**
- Rename serializer classes
- Rename `modifier_type_id` and `modifier_type_name` SerializerMethodFields to `modifier_target_id` and `modifier_target_name`
- Update the method implementations

**In views.py:**
- Rename filter class and viewset class
- Update queryset model reference

**In urls.py:**
- Update router registration: `router.register(r"modifier-targets", ModifierTargetViewSet)`

**After all renames in mechanics app, commit:**
```bash
git add src/world/mechanics/
git commit -m "refactor(mechanics): rename ModifierType to ModifierTarget in mechanics app"
```

---

## Task 2: Rename All FK References in Other App Models

Update every model file outside mechanics that has a FK or reference to `ModifierType`.

**Files to modify:**
- `src/world/distinctions/models.py` — `DistinctionEffect.target` FK, docstrings
- `src/world/magic/models.py` — resonance FKs and comments
- `src/world/goals/models.py` — `GoalDomain` FK references, comments
- `src/world/conditions/models.py` — `DamageType.resonance` FK, `gates_modifiers` M2M
- `src/world/codex/models.py` — FK to ModifierType
- `src/world/relationships/models.py` — M2M to ModifierType
- `src/world/character_creation/models.py` — comment references
- `src/world/action_points/models.py` — comment references

**For each file:**
- Change `"mechanics.ModifierType"` → `"mechanics.ModifierTarget"` in FK/M2M declarations
- Update import statements
- Update docstrings and comments

**After all model FK renames, commit:**
```bash
git add src/world/distinctions/ src/world/magic/ src/world/goals/ src/world/conditions/ src/world/codex/ src/world/relationships/ src/world/character_creation/ src/world/action_points/
git commit -m "refactor: rename ModifierType FK references across all apps"
```

---

## Task 3: Rename All Non-Model Code (Services, Factories, Serializers, Views, Admin)

Update every non-model, non-test file that imports or references ModifierType.

**Files to modify:**

**Distinctions app:**
- `src/world/distinctions/factories.py` — `ModifierTypeFactory` → `ModifierTargetFactory`

**Magic app:**
- `src/world/magic/factories.py` — `ResonanceModifierTypeFactory` → `ResonanceModifierTargetFactory`, `AffinityModifierTypeFactory` → `AffinityModifierTargetFactory`, and all SubFactory references
- `src/world/magic/serializers.py` — `ModifierTypeSerializer` import/usage
- `src/world/magic/views.py` — imports and usage
- `src/world/magic/services.py` — import references

**Goals app:**
- `src/world/goals/factories.py` — `GoalDomainFactory` base class reference
- `src/world/goals/serializers.py` — imports and references
- `src/world/goals/services.py` — `ModifierType` import and queries
- `src/world/goals/views.py` — references
- `src/world/goals/types.py` — comments
- `src/world/goals/admin.py` — comments

**Character creation app:**
- `src/world/character_creation/serializers.py` — `ModifierType` import and queries
- `src/world/character_creation/services.py` — `ModifierType` import and queries

**Progression app:**
- No model changes, but `awards.py` references will be updated in Task 4

**Character sheets app:**
- Check for any serializer references

**After all non-model renames, commit:**
```bash
git commit -am "refactor: rename ModifierType references in services, factories, serializers"
```

---

## Task 4: Add target_trait FK and Rewrite Service Layer

The substantive new behavior. Add the FK, remove string-based lookups, update the stat consumer, stub unfinished consumers.

**Files to modify:**
- `src/world/mechanics/models.py` — add `target_trait` FK
- `src/world/mechanics/services.py` — remove `get_modifier_for_character`, add `get_stat_modifier`
- `src/world/mechanics/types.py` — rename `modifier_type_name` field if present
- `src/world/traits/handlers.py` — update `_get_stat_modifier` to use FK
- `src/world/action_points/models.py` — stub `_get_ap_modifier`
- `src/world/progression/services/awards.py` — stub `get_development_rate_modifier`
- `src/world/goals/services.py` — this uses `ModifierType.objects.filter(category__name=...)` which is a valid query pattern (not the string-lookup function), so update import only
- `src/world/character_creation/models.py` — `_get_distinction_bonus` uses DistinctionEffect.target filtering, not get_modifier_for_character, so update docstring only

**Step 1: Add target_trait FK to ModifierTarget**

```python
# In ModifierTarget model, after is_active field:
target_trait = models.ForeignKey(
    "traits.Trait",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="modifier_targets",
    help_text="The trait this target modifies. Populated for stat category; "
    "null for categories whose target systems aren't built yet. "
    "See TECH_DEBT.md for tracking.",
)
# Future target FKs — added when their systems are built:
# target_capability: FK to conditions.CapabilityType — capability modifier system
# target_check_type: FK to conditions.CheckType — roll modifier system
# target_condition: FK to conditions.ConditionTemplate — condition modifier system
# See TECH_DEBT.md §"Future Target FKs" for full tracking list.
```

**Step 2: Remove get_modifier_for_character from services.py**

Delete the entire `get_modifier_for_character` function (lines 119-155).

**Step 3: Update TraitHandler._get_stat_modifier**

```python
def _get_stat_modifier(self, stat_name: str) -> int:
    """
    Get the total modifier for a stat from character's distinctions etc.

    Uses the ModifierTarget.target_trait FK for type-safe lookup
    instead of string matching.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415
    from world.traits.models import Trait  # noqa: PLC0415

    try:
        sheet = self.character.sheet_data
    except Exception:
        return 0

    try:
        trait = Trait.objects.get(name__iexact=stat_name)
        target = ModifierTarget.objects.get(target_trait=trait)
        return get_modifier_total(sheet, target)
    except (Trait.DoesNotExist, ModifierTarget.DoesNotExist):
        return 0
```

**Step 4: Stub action_points consumer**

Replace `_get_ap_modifier` in `action_points/models.py`:

```python
def _get_ap_modifier(self, modifier_type_name: str) -> int:
    """
    Get the total modifier for an AP type from character's distinctions etc.

    TODO: AP modifier system not yet built. When the AP regen/cron system
    is implemented, add a target FK on ModifierTarget for AP-category entries
    and replace this stub with FK-based lookup. See TECH_DEBT.md.
    """
    return 0
```

**Step 5: Stub progression consumer**

Replace `get_development_rate_modifier` call in `progression/services/awards.py`:

```python
def get_development_rate_modifier(character: "ObjectDB", trait: Trait) -> int:
    """
    Get development rate modifier for a trait's category.

    TODO: Development rate modifier system not yet built. When the progression
    system tracks development rates, add a target FK on ModifierTarget for
    development-category entries and replace this stub with FK-based lookup.
    See TECH_DEBT.md.
    """
    return 0
```

Note: The goals service and character_creation service don't use `get_modifier_for_character` — they query `ModifierTarget.objects.filter()` directly using the category name, which is a valid query pattern (not the string-lookup anti-pattern). Those just need the import rename.

**Commit:**
```bash
git commit -am "feat(mechanics): add target_trait FK, remove string-based lookups, stub consumers"
```

---

## Task 5: Update All Test Files

Update every test file to use renamed classes and factories. Also add tests for the new target_trait FK and verify stubs.

**Test files to update (rename only — find/replace):**
- `src/world/mechanics/tests/test_models.py`
- `src/world/mechanics/tests/test_services.py`
- `src/world/mechanics/tests/test_views.py`
- `src/world/mechanics/tests/test_resonance_integration.py`
- `src/world/distinctions/tests/test_models.py`
- `src/world/distinctions/tests/test_serializers.py`
- `src/world/distinctions/tests/test_views.py`
- `src/world/distinctions/tests/test_fixture_integrity.py`
- `src/world/goals/tests/test_services.py`
- `src/world/goals/tests/test_serializers.py`
- `src/world/magic/tests/test_models.py`
- `src/world/magic/tests/test_services.py`
- `src/world/magic/tests/test_affinity_totals.py`
- `src/world/magic/tests/test_serializers.py`
- `src/world/magic/tests/test_motif.py`
- `src/world/magic/tests/test_anima_ritual.py`
- `src/world/magic/tests/test_traditions.py`
- `src/world/magic/tests/test_views.py`
- `src/world/conditions/tests/test_services.py`
- `src/world/character_creation/tests/test_models.py`
- `src/world/character_creation/tests/test_services.py`
- `src/world/character_creation/tests/test_application_services.py`
- `src/world/action_points/tests/test_models.py`
- `src/world/progression/tests/test_services.py`
- `src/world/relationships/tests/test_models.py`
- `src/world/relationships/tests/test_views.py`
- `src/world/character_sheets/tests/test_viewset.py`
- `src/world/traits/tests.py`
- `src/web/admin/tests/test_export_import.py`

**New tests to add in `src/world/mechanics/tests/test_models.py`:**

```python
class ModifierTargetTraitFKTest(TestCase):
    """Tests for ModifierTarget.target_trait FK."""

    def test_stat_target_with_trait_fk(self):
        """Stat-category targets can link to a Trait."""
        from world.traits.models import Trait, TraitType
        trait = Trait.objects.create(name="test_str", trait_type=TraitType.STAT)
        cat = ModifierCategoryFactory(name="stat")
        target = ModifierTargetFactory(name="test_str", category=cat, target_trait=trait)
        self.assertEqual(target.target_trait, trait)

    def test_non_stat_target_null_trait(self):
        """Non-stat targets have null target_trait."""
        cat = ModifierCategoryFactory(name="action_points")
        target = ModifierTargetFactory(name="ap_regen", category=cat, target_trait=None)
        self.assertIsNone(target.target_trait)
```

**New tests for stubs in `src/world/action_points/tests/test_models.py`:**

```python
def test_ap_modifier_returns_zero_stub(self):
    """AP modifier is stubbed — returns 0 until AP system is built."""
    # TODO: Replace this test when AP modifier system is built
    result = self.pool._get_ap_modifier("ap_daily_regen")
    self.assertEqual(result, 0)
```

**Update tests in `src/world/mechanics/tests/test_services.py`:**
- Remove any tests for `get_modifier_for_character` (the deleted function)
- Update remaining tests to use `ModifierTarget` naming

**Commit:**
```bash
git commit -am "test: update all tests for ModifierTarget rename and new FK"
```

---

## Task 6: Squash Migrations and Update Fixtures

Since we're wiping the DB, squash migrations for all affected apps and update fixtures.

**Step 1: Delete existing migrations for affected apps**

Delete all migration files (except `__init__.py`) for:
- `src/world/mechanics/migrations/`
- `src/world/goals/migrations/` (has FK to ModifierTarget)

Other apps (distinctions, magic, conditions, etc.) reference `mechanics.ModifierType` in their migrations. These need the migration reference updated OR squashed too. Check each migration directory for references:
- `src/world/distinctions/migrations/`
- `src/world/magic/migrations/`
- `src/world/conditions/migrations/`
- `src/world/codex/migrations/`
- `src/world/relationships/migrations/`
- `src/world/character_creation/migrations/`

For any migration file referencing `mechanics.ModifierType`, it needs to reference `mechanics.ModifierTarget` instead. The safest approach: squash ALL world app migrations that reference mechanics.

**Step 2: Regenerate migrations**

```bash
arx manage makemigrations mechanics
arx manage makemigrations goals
# ... and any other app that was squashed
```

**Step 3: Update fixture files**

Rename fixture files:
- `src/world/mechanics/fixtures/initial_modifier_types.json` → `initial_modifier_targets.json`
- `src/world/mechanics/fixtures/new_modifier_types.json` → `new_modifier_targets.json`

In both files:
- `"model": "mechanics.modifiertype"` → `"model": "mechanics.modifiertarget"`
- Stat-category entries get `"target_trait": ["strength"]` etc. (using Trait natural key)
- Non-stat entries get `"target_trait": null`

In all other fixture files that reference ModifierType natural keys:
- Update any `["mechanics", "modifiertype", ...]` references to `["mechanics", "modifiertarget", ...]`

**Step 4: Verify fixture load order**

Traits fixtures must load before modifier_targets fixtures. Check `src/world/distinctions/tests/test_fixture_integrity.py` and update load order if needed.

**Commit:**
```bash
git commit -am "refactor: squash migrations and update fixtures for ModifierTarget"
```

---

## Task 7: Update Documentation

Update all documentation files.

**Files to modify:**
- `src/world/mechanics/CLAUDE.md` — full rewrite of model references
- `src/world/mechanics/TECH_DEBT.md` — mark Phase 1 done, add "Future Target FKs" section
- `src/world/magic/CLAUDE.md` — update ModifierType references
- `src/world/distinctions/CLAUDE.md` — if it exists, update references
- `docs/systems/mechanics.md` — full update
- `docs/systems/INDEX.md` — update model listings
- `docs/systems/magic.md` — update references
- `docs/systems/goals.md` — update references
- `docs/systems/action_points.md` — update references
- `docs/roadmap/ROADMAP.md` — add modifier target FK tracking

**TECH_DEBT.md updates:**
- Mark issue #1 (No FK to What It Modifies) as DONE
- Mark issue #2 (Naming Confusion) as DONE
- Add new section: "Future Target FKs" with the tracking table from the design doc
- Keep issues #3 and #4 (EffectBundle) as pending Phase 2

**Do NOT update old plan documents** (docs/plans/2026-01-*) — those are historical records.

**Commit:**
```bash
git commit -am "docs: update all documentation for ModifierTarget rename"
```

---

## Task 8: DB Wipe, Migrate, Load Fixtures, Full Test Suite

Final verification.

**Step 1: Wipe the database**

```bash
arx manage flush --no-input
```

Or if migrations are squashed from scratch:
```bash
arx manage migrate --run-syncdb
```

**Step 2: Run migrations**

```bash
arx manage migrate
```

**Step 3: Load fixtures in order**

```bash
# Traits first (dependency for modifier_targets)
arx manage loaddata initial_primary_stats

# Then mechanics
arx manage loaddata initial_modifier_categories
arx manage loaddata initial_modifier_targets
arx manage loaddata new_modifier_targets

# Then everything else in dependency order
arx manage loaddata initial_categories  # distinctions
# ... remaining fixtures
```

**Step 4: Run full test suite**

```bash
echo "yes" | arx test world.mechanics
echo "yes" | arx test world.distinctions
echo "yes" | arx test world.magic
echo "yes" | arx test world.goals
echo "yes" | arx test world.traits
echo "yes" | arx test world.action_points
echo "yes" | arx test world.progression
echo "yes" | arx test world.character_creation
echo "yes" | arx test world.conditions
echo "yes" | arx test world.character_sheets
echo "yes" | arx test world.relationships
echo "yes" | arx test web.admin
```

**Step 5: Run linting**

```bash
ruff check src/world/mechanics/ src/world/distinctions/ src/world/magic/ src/world/goals/ src/world/traits/ src/world/action_points/ src/world/progression/ src/world/character_creation/ src/world/conditions/
```

**Step 6: Verify no remaining references**

```bash
grep -r "ModifierType" src/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
grep -r "modifier_type" src/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
grep -r "modifiertype" src/ --include="*.json" | grep -v "__pycache__"
```

Any remaining hits should only be in:
- Old plan documents (historical, don't update)
- The generated `schema.json` (regenerate with `arx manage spectacular`)

**Final commit if any cleanup needed.**
