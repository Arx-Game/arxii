# Traits System

Character stats, trait definitions, and check resolution lookup tables (point conversion, ranks, result charts).

**Source:** `src/world/traits/`
**API Base:** `/api/traits/`

---

## A skill is a Trait

A skill is a `Trait` whose `trait_type` is `SKILL` (#5008, ADR-5008). `skills.Skill` is a
Django proxy of `Trait` (#5015): a typed view with no table of its own, whose default manager
returns only skill-type traits and whose `save()` sets the type.

- **Its fields** are the trait's: name, category, description, and the skill's hover text
  (`tooltip`), sheet and creation order (`display_order`) and whether it is offered
  (`is_active`). Those three are general `Trait` columns; other traits keep their defaults.
- **Referencing a skill:** a FK to `Skill`. The column holds the trait's pk, and the proxy's
  manager means admin pickers offer only skills. Specializations hang off it
  (`Specialization.parent_skill`).
- **Rating and progress** are the trait's `CharacterTraitValue` (read through the trait
  handler, `skill_rating(sheet, skill)`) and `progression.DevelopmentPoints` row (#5010).
- **Identity map:** `Skill` shares `Trait`'s, so a row read through `Skill` can come back as
  the cached `Trait` instance. Put skill behaviour on `Trait`, not on the proxy.
- **Why no table:** a profile row exists only to extend a row we cannot modify (Evennia's);
  `Trait` is ours (owner, #5008). `species.Language` still sits beside its LANGUAGE trait in
  the old companion shape, deliberately untouched.

---

## Enums (models.py)

```python
from world.traits.models import (
    TraitType,      # STAT, SKILL, MODIFIER, OTHER
    TraitCategory,  # PHYSICAL, SOCIAL, MENTAL, MAGIC, COMBAT, GENERAL, CRAFTING, WAR, OTHER
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Trait` | Trait definition template with case-insensitive caching; `skills.Skill` is its proxy for SKILL traits | `name`, `trait_type` (TraitType), `category` (TraitCategory), `description`, `is_public`, `tooltip`, `display_order`, `is_active` |
| `TraitRankDescription` | Descriptive labels for trait values during CG | `trait` (FK Trait), `value`, `label`, `description` |
| `PointConversionRange` | Converts trait values to weighted points (exponential curves) | `trait_type` (TraitType), `min_value`, `max_value`, `points_per_level` |
| `CheckRank` | Maps point totals to rank levels for check resolution | `rank`, `min_points`, `name`, `description` |
| `CheckOutcome` | Defines possible check outcomes (success, failure, etc.) | `name`, `success_level` (-10 to +10), `description`, `display_template` |
| `ResultChart` | Result charts for different rank differences | `rank_difference`, `name` |
| `ResultChartOutcome` | Outcome ranges (1-100) within a result chart | `chart` (FK ResultChart), `min_roll`, `max_roll`, `outcome` (FK CheckOutcome) |

### Character Data (SharedMemoryModel - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterTraitValue` | Character's actual trait value | `character` (FK ObjectDB), `trait` (FK Trait), `value` (int, any value) |

---

## Value Scale

- **Stored and shown:** 1-100 integers. Every surface shows the stored value for stats and
  skills alike (ADR-5091, #5091): strength 20 reads 20, a skill at 35 reads 35.
- **Stat point:** `STAT_POINT_VALUE` (10, `world/traits/models.py`), the step character
  creation, maturation, level stat points and GM raises move a stat by.
  `whole_stat_points(value)` (`value // 10`) is an internal step for formulas tuned per whole
  stat point (fatigue capacity); it is never shown.
- NPCs may have negative values or values above 100

---

## Key Methods

### Trait (case-insensitive lookup with caching)

```python
from world.traits.models import Trait

# Case-insensitive cached lookup (returns Trait or None)
trait = Trait.get_by_name("strength")
```

`get_by_name` delegates to the generic natural-key index (`core/natural_keys.py`,
#2687): `Trait.NaturalKeyConfig.lookup_table = True` loads the whole table once and
serves every subsequent lookup from memory. The index is kept fresh automatically
by `NaturalKeyMixin.save()` — there is no manual cache to clear.

### PointConversionRange (trait value to points)

```python
from world.traits.models import PointConversionRange, TraitType

# Calculate total weighted points for a trait value
points = PointConversionRange.calculate_points(TraitType.STAT, trait_value=50)

# Check if a value falls within a specific range
range_obj.contains_value(25)  # True/False
```

### CheckRank (points to rank)

```python
from world.traits.models import CheckRank

# Get highest rank achievable with given points
rank = CheckRank.get_rank_for_points(150)

# Calculate rank difference between roller and target
diff = CheckRank.get_rank_difference(roller_points=200, target_points=100)
```

### ResultChart (rank difference to chart)

```python
from world.traits.models import ResultChart

# Get chart for a rank difference (exact match or closest)
chart = ResultChart.get_chart_for_difference(rank_difference=2)

# Clear chart cache (auto-needed if charts modified)
ResultChart.clear_cache()
```

### ResultChartOutcome (roll to outcome)

```python
# Check if a roll falls within this outcome's range
chart_outcome.contains_roll(75)  # True/False
```

### TraitHandler (character trait interface)

```python
from world.traits.handlers import TraitHandler

# Accessed via character typeclass: character.traits
handler = character.traits

# Get trait value (a stat includes its modifiers, valued and tapered in the stat lane)
value = handler.get_trait_value("strength")

# Get base value without modifiers
base = handler.get_base_trait_value("strength")

# Set a trait value
handler.set_trait_value("strength", 50)

# Get CharacterTraitValue object (or DefaultTraitValue if missing)
trait_obj = handler.get_trait_object("strength")

# Get all traits of a specific type
stats = handler.get_traits_by_type("stat")  # dict[str, CharacterTraitValue]

# Get all traits organized by category
all_traits = handler.get_all_traits()  # dict[category, dict[name, CharacterTraitValue]]

# Get only public traits
public = handler.get_public_traits()

# Calculate total weighted points for a list of traits
points = handler.calculate_check_points(["strength", "dexterity"])

# Clear and reinitialize cache
handler.clear_cache()
```

---

## Check Resolution Pipeline

The traits app provides the lookup tables. Actual check resolution lives in `world/checks/`.

```
trait_value -> PointConversionRange -> points
points -> CheckRank -> rank
roller_rank - target_rank -> rank_difference
rank_difference -> ResultChart -> chart
roll (1-100) -> ResultChartOutcome -> CheckOutcome
```

---

## API Endpoints

### Stat Definitions
- `GET /api/traits/stat-definitions/` - List all stat-type Trait records (read-only, 9 stats)
- `GET /api/traits/stat-definitions/{id}/` - Get single stat definition

---

## Admin

All models registered with appropriate admin interfaces:

- `TraitAdmin` - List/filter by `trait_type`, `category`, `is_public` with inline `TraitRankDescription` editing. Skills are authored on `SkillAdmin`, the proxy's page (see `docs/systems/skills.md`); here a skill that has specializations cannot be retyped away from Skill, and saving a skill-type trait makes its modifier target. The rank-description row's display value is blank on the empty add row, which on a stat trait used to fail the page.
- `CharacterTraitValueAdmin` - Search by character key and trait name, filter by trait type/category
- `PointConversionRangeAdmin` - List by trait type and value range
- `CheckRankAdmin` - Ordered by rank
- `CheckOutcomeAdmin` - Filter by `success_level`, search by name/description
- `ResultChartAdmin` - Ordered by `rank_difference` with inline `ResultChartOutcome` editing

---

## Integration Points

- **Checks app**: Uses `PointConversionRange`, `CheckRank`, `ResultChart`, `CheckOutcome` for check resolution
- **Skills app**: `Skill` model links to `Trait` via OneToOneField
- **Distinctions app**: Stat modifiers applied via `TraitHandler.get_trait_value()`
- **Character Creation**: Trait display and stat allocation
- **Character Sheets**: Trait display via `TraitHandler`
- **Mechanics app**: Provides stat modifiers consumed by `TraitHandler._get_stat_modifier()`
- **Stat lane (#4726, ADR-4726-A)**: `_get_stat_modifier` totals the stat target's CHARACTER
  and EQUIPMENT contributions (`world.checks.services.modifier_target_contributions`) and
  CONDITION contributions (`world.conditions.services.condition_target_contributions`) as a
  checks `ModifierBreakdown` tapered by `load_taper_rules(ModifierLane.STAT)`. A sized technique
  buff or distinction effect on a stat reads the stat lane's `ModifierValue` table; values are
  in stored units (the number the sheet shows). Every reader of `get_trait_value` sees this one number.
  The table and taper rows load only when needed, so a read with nothing sized and no pile of
  one kind adds no query (the #552 fatigue hot path). See `docs/systems/checks.md`, "The stat
  lane".
- **Skills join the lane (#4820)**: `get_trait_value` folds the same breakdown for a
  `TraitType.SKILL` trait whose target exists (`MODIFIABLE_TRAIT_TYPES`), in the skill's own
  units; `get_trait_modifier(trait)` returns the bonus alone for the sheet. Advancement reads the
  stored value, never this one. See `docs/systems/skills.md`, "A card's bonus on a skill".
