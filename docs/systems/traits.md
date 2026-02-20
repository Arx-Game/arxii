# Traits System

Character stats, trait definitions, and check resolution lookup tables (point conversion, ranks, result charts).

**Source:** `src/world/traits/`
**API Base:** `/api/traits/`

---

## Enums (models.py)

```python
from world.traits.models import (
    TraitType,      # STAT, SKILL, MODIFIER, OTHER
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
| `Trait` | Trait definition template with case-insensitive caching | `name`, `trait_type` (TraitType), `category` (TraitCategory), `description`, `is_public` |
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

# Clear name cache when traits are modified (auto-called on save)
Trait.clear_name_cache()
```

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

# Get trait value (includes stat modifiers from distinctions)
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

- `TraitAdmin` - List/filter by `trait_type`, `category`, `is_public` with inline `TraitRankDescription` editing
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
