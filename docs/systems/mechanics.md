# Mechanics System

Game engine for modifier collection, stacking, amplification, immunity, and source tracking from distinctions (and future sources like equipment and spells).

**Source:** `src/world/mechanics/`
**API Base:** `/api/mechanics/`

---

## Enums (constants.py)

```python
from world.mechanics.constants import (
    ResonanceAffinity,          # CELESTIAL, ABYSSAL, PRIMAL
    STAT_CATEGORY_NAME,         # "stat"
    GOAL_CATEGORY_NAME,         # "goal"
    GOAL_PERCENT_CATEGORY_NAME, # "goal_percent"
    GOAL_POINTS_CATEGORY_NAME,  # "goal_points"
    RESONANCE_CATEGORY_NAME,    # "resonance"
)
```

## Types (types.py)

```python
from world.mechanics.types import (
    ModifierSourceDetail,  # Dataclass: source_name, base_value, amplification, final_value, is_amplifier, blocked_by_immunity
    ModifierBreakdown,     # Dataclass: modifier_type_name, sources (list[ModifierSourceDetail]), total, has_immunity, negatives_blocked
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ModifierCategory` | Broad groupings for modifier types (stat, magic, affinity, resonance, goal, etc.) | `name` (unique), `description`, `display_order` |
| `ModifierType` | Unified registry of all things that can be modified; replaces separate Affinity, Resonance, GoalDomain models | `name`, `category` (FK ModifierCategory), `description`, `display_order`, `is_active`, `affiliated_affinity` (self FK), `opposite` (self OneToOne), `resonance_affinity` (ResonanceAffinity) |

### Per-Character Data (regular models)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ModifierSource` | Encapsulates where a modifier originated; links effect template to character instance | `distinction_effect` (FK DistinctionEffect), `character_distinction` (FK CharacterDistinction, CASCADE) |
| `CharacterModifier` | Materialized modifier value on a character for fast lookup (SharedMemoryModel) | `character` (FK CharacterSheet), `value` (int, can be negative), `source` (FK ModifierSource, CASCADE), `expires_at` (nullable datetime), `created_at` |

### Key Model Properties

```python
# ModifierSource
source.source_type     # "distinction" or "unknown"
source.modifier_type   # ModifierType from source.distinction_effect.target
source.source_display  # "Distinction: Strong" (human-readable)

# CharacterModifier
modifier.modifier_type  # Derived from source.modifier_type (not stored directly)
```

### Stacking Rules

- All modifiers for a given `modifier_type` stack (values are summed).
- Modifiers with `value == 0` are hidden from display.
- `modifier_type` is derived from `source.distinction_effect.target` -- never stored directly on `CharacterModifier`.

---

## Key Methods

### Service Functions (`services.py`)

```python
from world.mechanics.services import (
    get_modifier_for_character,
    get_modifier_total,
    get_modifier_breakdown,
    create_distinction_modifiers,
    delete_distinction_modifiers,
    update_distinction_rank,
)

# Main helper: look up modifiers by category/type name (handles missing sheet/type gracefully)
total = get_modifier_for_character(character, "stat", "strength")
# Returns int (0 if no sheet, no ModifierType, or no modifiers)

# Get total for a specific ModifierType (requires CharacterSheet + ModifierType instances)
total = get_modifier_total(sheet, modifier_type)

# Get detailed breakdown with amplification/immunity calculations
breakdown = get_modifier_breakdown(sheet, modifier_type)
# Returns ModifierBreakdown with sources, total, has_immunity, negatives_blocked
```

### Amplification and Immunity

```python
# get_modifier_breakdown applies these rules:
# 1. Amplifying sources: add their amplifies_sources_by bonus to all OTHER sources
# 2. Immunity: if any source grants_immunity_to_negative, all negative final values are blocked

breakdown = get_modifier_breakdown(sheet, modifier_type)
breakdown.total            # Final stacked value after amplification/immunity
breakdown.has_immunity     # True if any source grants negative immunity
breakdown.negatives_blocked  # Count of negative modifiers blocked by immunity
for source in breakdown.sources:
    source.base_value       # Raw modifier value
    source.amplification    # Bonus from other amplifying sources
    source.final_value      # base_value + amplification
    source.is_amplifier     # Whether this source amplifies others
    source.blocked_by_immunity  # Whether this source was blocked
```

### Distinction Lifecycle

```python
from world.mechanics.services import create_distinction_modifiers, delete_distinction_modifiers, update_distinction_rank

# When a CharacterDistinction is granted: create ModifierSource + CharacterModifier per effect
modifiers = create_distinction_modifiers(character_distinction)
# Also updates CharacterResonanceTotal for resonance-targeting effects

# When a CharacterDistinction is removed: cascade-delete all modifiers
count = delete_distinction_modifiers(character_distinction)
# Also subtracts from CharacterResonanceTotal

# When rank changes: recalculate modifier values
update_distinction_rank(character_distinction)
# Also adjusts CharacterResonanceTotal by the difference
```

---

## Modifier Type Naming Conventions

| Category | Naming Pattern | Examples |
|----------|---------------|----------|
| `stat` | Lowercase stat name | `strength`, `dexterity`, `charm` |
| `action_points` | `ap_` prefix + descriptor | `ap_daily_regen`, `ap_weekly_regen`, `ap_maximum` |
| `development` | Category + `_skill_development_rate` | `physical_skill_development_rate`, `all_skill_development_rate` |
| `height_band` | Descriptive name | `max_height_band_bonus` |
| `resonance` | Resonance name | Uses `affiliated_affinity`, `opposite`, `resonance_affinity` fields |
| `goal` / `goal_percent` / `goal_points` | Goal domain names | Standing, Wealth, Knowledge, etc. |

---

## API Endpoints

### Modifier Categories
- `GET /api/mechanics/categories/` - List all modifier categories (no pagination, small lookup table)

### Modifier Types
- `GET /api/mechanics/types/` - List active modifier types
- `GET /api/mechanics/types/{id}/` - Retrieve single modifier type

**Query Parameters:**
- `category` - Filter by category name (case-insensitive)
- `is_active` - Filter by active status

### Character Modifiers
- `GET /api/mechanics/character-modifiers/` - List character modifiers
- `GET /api/mechanics/character-modifiers/{id}/` - Retrieve single modifier

**Query Parameters:**
- `character` - Filter by CharacterSheet ID

---

## Integration Points

- **Distinctions**: Primary modifier source. `create_distinction_modifiers()` is called when a `CharacterDistinction` is created; `delete_distinction_modifiers()` on removal; `update_distinction_rank()` on rank change.
- **Magic**: Resonance-targeting effects call `add_resonance_total()` to keep `CharacterResonanceTotal` in sync.
- **Action Points**: `ActionPointPool._get_ap_modifier()` calls `get_modifier_for_character(character, "action_points", type_name)` for regen and maximum adjustments.
- **Progression**: Development rate modifiers use `get_modifier_for_character(character, "development", modifier_name)` to scale development point awards.
- **Equipment** (future): Will follow the same `ModifierSource` pattern with equipment-specific FK fields.
- **Conditions** (future): Will follow the same pattern for status effect modifiers.

---

## Admin

All models registered with search, filters, and `list_select_related` for performance:

- `ModifierCategoryAdmin` - Editable `display_order`, truncated description display
- `ModifierTypeAdmin` - Filterable by category and active status, editable `display_order` and `is_active`
- `ModifierSourceAdmin` - Shows source type and display, `raw_id_fields` for FKs
- `CharacterModifierAdmin` - Custom display methods for character name and modifier type (since `modifier_type` is a derived property), `list_select_related` through full source chain
