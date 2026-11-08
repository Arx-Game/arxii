# Traits System

Character stats, trait definitions, and check resolution lookup tables (point conversion, ranks, result charts).

**Source:** `src/world/traits/`
**API Base:** `/api/traits/`

---

## A skill is a Trait

A skill is a `Trait` whose `trait_type` is `SKILL`, and nothing else (#5008, ADR-5008).
There is no separate skill model.

- **Where its fields live.** Name, category and description are the trait's. So are the
  skill's hover text (`Trait.tooltip`), its order in character creation and on the sheet
  (`Trait.display_order`) and whether it is offered at all (`Trait.is_active`). Those three
  are general `Trait` fields; non-skill traits keep their defaults.
- **Its specializations** hang off the trait: `skills.Specialization.parent_skill` is a FK to
  `Trait`, limited to skill-type traits.
- **Referencing a skill.** Every reference is a FK to `Trait` with
  `limit_choices_to={"trait_type": "skill"}` (magic pickers add `category=MAGIC`, see
  `world/magic/skill_choices.py`). The field keeps a skill-flavoured name (`skill`,
  `parent_skill`, `teaching_skill`, `snapshot_skill`), because what it holds is a skill.
- **A character's rating** is that trait's `CharacterTraitValue`, read through the trait
  handler (`skill_rating(sheet, skill)`), and its progress and rust are that trait's
  `progression.DevelopmentPoints` row (#5010). See `docs/systems/skills.md`.
- **Authoring.** One admin page, the Trait page: tooltip, order and active are plain fields,
  specializations are an inline, and saving a skill makes the modifier target its bonuses
  land on (`mechanics.services.ensure_skill_target`).
- **The rule behind it.** A profile row exists only to extend a row we cannot modify, such as
  Evennia's. `Trait` is ours, so a skill gets columns on it, not a companion table.
  `species.Language` still sits beside its LANGUAGE trait in the old companion shape; it was
  left as it is.

---

## Enums (models.py)

```python
from world.traits.models import (
    TraitType,      # STAT, SKILL, MODIFIER, LANGUAGE, OTHER
    TraitCategory,  # PHYSICAL, SOCIAL, MENTAL, MAGIC, COMBAT, GENERAL, CRAFTING, WAR, OTHER
)
```

---

## Types (types.py)

```python
from world.traits.types import (
    StatDisplayInfo,  # Dataclass: value, display, modifiers (for API/UI responses)
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Trait` | Trait definition template with case-insensitive caching; a SKILL-type trait is a skill | `name`, `trait_type` (TraitType), `category` (TraitCategory), `description`, `is_public`, `tooltip`, `display_order`, `is_active` |
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

- **Internal:** 1-100 integers (stored in database)
- **Display:** 1.0-10.0 (shown to players, computed as `value / 10`)
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

# Get display value (1.0-10.0 scale)
display = handler.get_trait_display_value("strength")

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

- `TraitAdmin` - List/filter by `trait_type`, `category`, `is_public` with inline `TraitRankDescription` editing. A skill is authored here in full (#5006, #5008): `tooltip`, `display_order` and `is_active` are plain fields, `SpecializationInline` edits its specializations (refused on a non-skill trait), and saving a skill-type trait runs `ensure_skill_target_or_warn`. The rank-description row's display value is blank on the empty add row, which on a stat trait used to fail the page.
- `CharacterTraitValueAdmin` - Search by character key and trait name, filter by trait type/category
- `PointConversionRangeAdmin` - List by trait type and value range
- `CheckRankAdmin` - Ordered by rank
- `CheckOutcomeAdmin` - Filter by `success_level`, search by name/description
- `ResultChartAdmin` - Ordered by `rank_difference` with inline `ResultChartOutcome` editing

---

## Integration Points

- **Checks app**: Uses `PointConversionRange`, `CheckRank`, `ResultChart`, `CheckOutcome` for check resolution
- **Skills app**: a skill is a SKILL-type `Trait`; `skills.Specialization` and every other skill FK point at `Trait` (see "A skill is a Trait" above)
- **Distinctions app**: Stat modifiers applied via `TraitHandler.get_trait_value()`
- **Character Creation**: Trait display and stat allocation
- **Character Sheets**: Trait display via `TraitHandler`
- **Mechanics app**: Provides stat modifiers consumed by `TraitHandler._get_stat_modifier()`
- **Stat lane (#4726, ADR-4726-A)**: `_get_stat_modifier` totals the stat target's CHARACTER
  and EQUIPMENT contributions (`world.checks.services.modifier_target_contributions`) and
  CONDITION contributions (`world.conditions.services.condition_target_contributions`) as a
  checks `ModifierBreakdown` tapered by `load_taper_rules(ModifierLane.STAT)`. A sized technique
  buff or distinction effect on a stat reads the stat lane's `ModifierValue` table; values are
  in stored units (x10 the shown stat). Every reader of `get_trait_value` sees this one number.
  The table and taper rows load only when needed, so a read with nothing sized and no pile of
  one kind adds no query (the #552 fatigue hot path). See `docs/systems/checks.md`, "The stat
  lane".
- **Skills join the lane (#4820)**: `get_trait_value` folds the same breakdown for a
  `TraitType.SKILL` trait whose target exists (`MODIFIABLE_TRAIT_TYPES`), in the skill's own
  units; `get_trait_modifier(trait)` returns the bonus alone for the sheet. Advancement reads the
  stored value, never this one. See `docs/systems/skills.md`, "A card's bonus on a skill".
