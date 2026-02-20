# Classes System

Character paths with evolution hierarchy through stages of power, plus legacy character classes with level tracking and aspect-based bonuses.

**Source:** `src/world/classes/`

---

## Enums (models.py)

```python
from world.classes.models import PathStage
# PROSPECT = 1   - Level 1-2, pre-awakening, selected in CG
# POTENTIAL = 2   - Level 3, awakening potential
# PUISSANT = 3    - Level 6, magical power
# TRUE = 4        - Level 11, true mastery
# GRAND = 5       - Level 16, grand power
# TRANSCENDENT = 6 - Level 21+, beyond mortal
```

---

## Models

### Path System (SharedMemoryModel - cached, primary system)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Path` | Narrative path definition with evolution hierarchy | `name`, `description`, `stage` (PathStage), `minimum_level`, `parent_paths` (M2M self, asymmetric), `is_active`, `icon_url`, `icon_name`, `sort_order` |
| `Aspect` | Broad character archetype for check bonuses | `name`, `description` |
| `PathAspect` | Links a path to an aspect with a weight multiplier | `character_path` (FK Path), `aspect` (FK Aspect), `weight` (default 1) |

### Character Class System (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterClass` | Class definition with trait requirements | `name`, `description`, `is_hidden`, `minimum_level` (0-10), `core_traits` (M2M to Trait) |
| `CharacterClassLevel` | Character-to-class assignment with level | `character` (FK ObjectDB), `character_class` (FK), `level` (1-10), `is_primary` |

---

## Key Methods

### Path

```python
from world.classes.models import Path, PathStage

# Create a path
path = Path.objects.create(
    name="Path of Steel",
    description="The martial path",
    stage=PathStage.PROSPECT,
    minimum_level=1,
)

# Evolution hierarchy
vanguard.parent_paths.add(steel_path)   # Steel can evolve into Vanguard
steel_path.child_paths.all()            # Paths that evolve from Steel

# Cached path aspects (optimized for prefetch_related with to_attr)
path.cached_path_aspects  # list[PathAspect] - invalidate with: del path.cached_path_aspects

# String representation
str(path)  # "Path of Steel (Prospect)"
```

### CharacterClassLevel

```python
from world.classes.models import CharacterClassLevel

# Get all classes for a character
CharacterClassLevel.objects.filter(character=character)

# Check elite eligibility (level 6+)
class_level.is_elite_eligible  # True if level >= 6

# Get primary class
CharacterClassLevel.objects.get(character=character, is_primary=True)
```

### PathAspect

```python
from world.classes.models import PathAspect

# Get aspects for a path
path.path_aspects.select_related("aspect").all()

# String representation
str(path_aspect)  # "Path of Steel: Warfare (weight 2)"
```

---

## Cross-App Relationships

The Path model integrates with other apps through their own models:

- **Codex System** (`world.codex`): `PathCodexGrant` links paths to codex entries that are granted when a path is chosen.
- **Skills System** (`world.skills`): `PathSkillSuggestion` links paths to suggested skills for that path.
- **Traits System** (`world.traits`): `CharacterClass.core_traits` references `Trait` for class trait requirements.

Both `PathCodexGrant` and `PathSkillSuggestion` appear as inlines on the Path admin page.

---

## Admin

Path and Aspect models registered with appropriate filters, search, and inline editing:

- **`PathAdmin`** - List display with stage filter, active status, parent count, and aspect summary. Includes `PathAspectInline` (aspect weights with autocomplete), `PathCodexGrantInline` (codex entry grants), and `PathSkillSuggestionInline` (skill suggestions). Fieldsets group core fields, display options, and evolution hierarchy separately.
- **`AspectAdmin`** - Simple list with path count display, name/description search.
