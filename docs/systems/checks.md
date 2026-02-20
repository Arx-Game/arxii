# Checks System

Database-defined check types with weighted trait and aspect composition, resolved through the rank/chart/outcome pipeline.

**Source:** `src/world/checks/`

---

## Types (types.py)

```python
from world.checks.types import (
    CheckResult,  # Dataclass returned by perform_check (no roll numbers exposed)
)
```

### CheckResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `check_type` | `CheckType` | The check type that was resolved |
| `outcome` | `CheckOutcome \| None` | The resolved outcome |
| `chart` | `ResultChart \| None` | The result chart used |
| `roller_rank` | `CheckRank \| None` | Roller's rank |
| `target_rank` | `CheckRank \| None` | Target's rank |
| `rank_difference` | `int` | roller_rank - target_rank |
| `trait_points` | `int` | Points from weighted traits |
| `aspect_bonus` | `int` | Bonus from path aspects |
| `total_points` | `int` | trait_points + aspect_bonus + extra_modifiers |

### CheckResult Properties

```python
result.outcome_name   # str: outcome name or "Unknown"
result.success_level  # int: outcome success_level or 0
result.chart_name     # str: chart name or "No Chart Found"
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CheckCategory` | Groups check types (Social, Combat, Exploration, Magic) | `name` (unique), `description`, `display_order` |
| `CheckType` | Named check definition with trait/aspect composition | `name`, `category` (FK CheckCategory), `description`, `is_active`, `display_order` |
| `CheckTypeTrait` | Weighted trait contribution to a check type | `check_type` (FK CheckType), `trait` (FK Trait), `weight` (Decimal, default 1.0) |
| `CheckTypeAspect` | Weighted aspect relevance for a check type | `check_type` (FK CheckType), `aspect` (FK Aspect), `weight` (Decimal, default 1.0) |

---

## Key Methods

### perform_check (main resolution function)

```python
from world.checks.services import perform_check

# Perform a check against a flat difficulty
result = perform_check(
    character=character,           # ObjectDB instance
    check_type=check_type,         # CheckType instance
    target_difficulty=0,           # Target points to beat (default 0)
    extra_modifiers=0,             # Bonus/penalty from caller (goals, magic, combat, conditions)
)

# Use the result
result.outcome_name    # "Success", "Catastrophic Failure", etc.
result.success_level   # -10 to +10
result.trait_points    # Points from character's traits
result.aspect_bonus    # Bonus from path aspects
result.total_points    # Final total
```

### get_rollmod (public helper)

```python
from world.checks.services import get_rollmod

# Sum of character.sheet_data.rollmod + character.account.player_data.rollmod
# Returns 0 for missing relations
rollmod = get_rollmod(character)
```

---

## Resolution Pipeline

```
1. Weighted trait points
   For each CheckTypeTrait:
     raw_value = handler.get_trait_value(trait.name)
     weighted_value = int(raw_value * weight)
     points += PointConversionRange.calculate_points(trait_type, weighted_value)

2. Aspect bonus from path
   latest_path = CharacterPathHistory (most recent)
   For each CheckTypeAspect with matching PathAspect:
     bonus += int(check_aspect_weight * path_aspect_weight * character_level)

3. Total = trait_points + aspect_bonus + extra_modifiers

4. Total points -> CheckRank.get_rank_for_points()
   Target difficulty -> CheckRank.get_rank_for_points()
   rank_difference = roller_rank - target_rank

5. ResultChart.get_chart_for_difference(rank_difference)

6. Roll 1-100 (random.randint)
   rollmod = get_rollmod(character)
   effective_roll = clamp(roll + rollmod, 1, 100)

7. Query ResultChartOutcome for matching range -> CheckOutcome

8. Return CheckResult dataclass
```

---

## Internal Service Functions

```python
# These are private (_prefixed) and called by perform_check internally:

# Calculate weighted trait points from CheckTypeTrait entries
_calculate_trait_points(handler, check_type) -> int

# Calculate aspect bonus from character's most recent path
_calculate_aspect_bonus(character, check_type, level) -> int

# Get character's primary class level (or highest, or default 1)
_get_character_level(character) -> int

# Look up ResultChartOutcome for a roll value on a chart
_get_outcome_for_roll(chart, roll) -> CheckOutcome | None
```

---

## Admin

All models registered with appropriate admin interfaces:

- `CheckCategoryAdmin` - List with editable `display_order`, inline `CheckType` editing, search by name
- `CheckTypeAdmin` - List/filter by `category` and `is_active`, editable `is_active` and `display_order`, inline `CheckTypeTrait` and `CheckTypeAspect` editing with autocomplete fields

---

## Design Principles

- **No check persistence** -- results are transient, consumed by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals, magic, combat, and conditions compute their own `extra_modifiers` before calling `perform_check`
- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect)
- **No API endpoints** -- check types are staff-defined via admin; resolution is called programmatically by other systems

---

## Integration Points

- **Traits app**: Uses `PointConversionRange`, `CheckRank`, `ResultChart`, `CheckOutcome` for the resolution pipeline
- **Classes app**: Uses `Aspect` and `PathAspect` for aspect bonus calculation, `CharacterClassLevel` for character level
- **Progression app**: Uses `CharacterPathHistory` for current path lookup
- **Attempts app**: Calls `perform_check()` for resolution; provides roulette display content via `ConsequenceDisplay`
- **Callers** (goals, magic, combat, conditions): Compute `extra_modifiers` before calling `perform_check()`
