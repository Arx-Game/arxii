# Species System

Species/race definitions with stat bonuses, subspecies hierarchy, and starting language assignments.

**Source:** `src/world/species/`

---

## Enums

The species app has no local enums. Stat bonuses reference `PrimaryStat` from the traits system:

```python
from world.traits.constants import PrimaryStat
# STRENGTH, AGILITY, STAMINA, CHARM, PRESENCE, PERCEPTION, INTELLECT, WITS, WILLPOWER
```

---

## Models

All models use `SharedMemoryModel` (cached) and `NaturalKeyMixin` (fixture support).

### Lookup Tables (SharedMemoryModel)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Species` | Core species/subspecies with optional parent hierarchy | `name`, `description`, `parent` (FK self), `sort_order`, `starting_languages` (M2M to Language) |
| `SpeciesStatBonus` | Permanent stat modifier for a species | `species` (FK), `stat` (PrimaryStat choices), `value` (SmallInt) |
| `Language` | Languages available in the game | `name`, `description` |

### Hierarchy Design

Species uses a single-level parent/child hierarchy:
- **Top-level** (parent=null): Directly playable (e.g., Human) or category-only (e.g., Elven)
- **Subspecies** (parent set): Playable subspecies under a category (e.g., Rex'alfar -> Elven)

Access control for which species are available in CG is handled by `Beginnings.allowed_species` in the `character_creation` app, not in this model.

---

## Key Methods

### Species

```python
from world.species.models import Species

# Check if a species is a subspecies
species.is_subspecies  # Returns True if parent_id is not None

# Get stat bonuses as a dict
species.get_stat_bonuses_dict()
# Returns: {"strength": 1, "charm": -1}

# Access children (subspecies)
species.children.all()

# Access starting languages
species.starting_languages.all()

# String representation includes parent
str(subspecies)  # "Rex'alfar (Elven)"
str(top_level)   # "Human"
```

### SpeciesStatBonus

```python
from world.species.models import SpeciesStatBonus

# Access all bonuses for a species
species.stat_bonuses.all()

# String includes sign
str(bonus)  # "Infernal: -1 Charm"
```

---

## Integration Points

- **Forms System** (`world.forms`): `SpeciesFormTrait` links species to available physical appearance traits and options for CG.
- **Character Creation** (`world.character_creation`): `Beginnings.allowed_species` controls which species are selectable during character creation.
- **Traits System** (`world.traits`): `SpeciesStatBonus.stat` uses `PrimaryStat` choices from `world.traits.constants`.

---

## Admin

All models registered in Django admin:

- **`SpeciesAdmin`** - List display with parent filter, stat bonus summary, and language count. Includes `SpeciesChildrenInline` (read-only subspecies list with change links) and `SpeciesStatBonusInline` (editable stat bonuses). Uses `filter_horizontal` for starting languages.
- **`LanguageAdmin`** - Simple list with name search.
