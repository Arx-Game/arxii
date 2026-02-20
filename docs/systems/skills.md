# Skills System

Character skills and specializations with development tracking, linked to the Trait system for unified check resolution.

**Source:** `src/world/skills/`
**API Base:** `/api/skills/`

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Skill` | Parent skill linked to Trait system | `trait` (OneToOne Trait, limited to SKILL type), `tooltip`, `display_order`, `is_active` |
| `Specialization` | Specific application under a parent skill | `name`, `parent_skill` (FK Skill), `description`, `tooltip`, `display_order`, `is_active` |
| `SkillPointBudget` | CG point budget configuration (single-row model) | `path_points` (50), `free_points` (60), `points_per_tier` (10), `specialization_unlock_threshold` (30), `max_skill_value` (30), `max_specialization_value` (30) |
| `PathSkillSuggestion` | Suggested skill allocation for a path (template) | `character_path` (FK Path), `skill` (FK Skill), `suggested_value`, `display_order` |

### Character Data (SharedMemoryModel - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterSkillValue` | Character's skill value with progression | `character` (FK ObjectDB), `skill` (FK Skill), `value`, `development_points`, `rust_points` |
| `CharacterSpecializationValue` | Character's specialization value (no rust) | `character` (FK ObjectDB), `specialization` (FK Specialization), `value`, `development_points` |

---

## Value Scale

- **Internal:** 10, 20, 30, ... (stored value, increments of 10)
- **Display:** 1.0, 2.0, 3.0, ... (shown to players, computed as `value / 10`)
- **CG max:** 30 (configurable via `SkillPointBudget.max_skill_value`)

---

## Key Concepts

### Development Points
- Progress toward next skill level (e.g., 450/1000)
- Earned through training, scenes, missions
- Resets when level increases

### Rust Points
- Blocks development until cleared (must train to remove rust before gaining new levels)
- Only affects parent skills; specializations are immune
- Encourages specialization over jack-of-all-trades builds

### CG Point Budget
- Path points (default 50): Suggested by path template, freely redistributable
- Free points (default 60): Player's choice
- Total: 110 points (default)
- Cost: 10 per tier (flat rate)
- Specialization unlock: Parent skill must reach 30 (configurable)

---

## Key Methods

### Skill (properties delegated from Trait)

```python
from world.skills.models import Skill

skill = Skill.objects.get(pk=1)

# Properties delegated from linked Trait
skill.name         # -> self.trait.name
skill.category     # -> self.trait.category
skill.description  # -> self.trait.description
```

### Specialization

```python
from world.skills.models import Specialization

spec = Specialization.objects.get(pk=1)
spec.parent_name  # -> self.parent_skill.name
```

### CharacterSkillValue / CharacterSpecializationValue

```python
from world.skills.models import CharacterSkillValue, CharacterSpecializationValue

# Display value (1.0 scale)
csv = CharacterSkillValue.objects.get(character=char, skill=skill)
csv.display_value  # e.g., 3.0 for value=30
```

### SkillPointBudget (single-row configuration)

```python
from world.skills.models import SkillPointBudget

# Get or create the active budget (atomic, uses pk=1)
budget = SkillPointBudget.get_active_budget()

budget.total_points  # path_points + free_points (default 110)
budget.path_points   # 50
budget.free_points   # 60
budget.points_per_tier  # 10
budget.specialization_unlock_threshold  # 30
```

---

## API Endpoints

### Skills
- `GET /api/skills/skills/` - List all active skills (light serializer, no specializations)
- `GET /api/skills/skills/{id}/` - Get single skill with nested specializations
- `GET /api/skills/skills/with_specializations/` - All skills with specializations in one request (for CG)

**Query Parameters:**
- `is_active` - Filter by active status (defaults to active only)

### Specializations
- `GET /api/skills/specializations/` - List all active specializations
- `GET /api/skills/specializations/{id}/` - Get single specialization

**Query Parameters:**
- `parent_skill` - Filter by parent skill ID
- `is_active` - Filter by active status (defaults to active only)

### Path Skill Suggestions
- `GET /api/skills/path-skill-suggestions/` - List path skill suggestions

**Query Parameters:**
- `character_path` - Filter by path ID

### Skill Budget
- `GET /api/skills/skill-budget/` - Get the active skill point budget (returns single object, not array)

---

## Admin

All models registered with appropriate admin interfaces:

- `SkillAdmin` - List/filter by category and active status, inline `Specialization` editing, ordered by `display_order`
- `SpecializationAdmin` - List/filter by `parent_skill` and active status, search by name and parent skill
- `CharacterSkillValueAdmin` - Shows `value`, `display_value`, `development_points`, `rust_points`; filter by skill
- `CharacterSpecializationValueAdmin` - Shows `value`, `display_value`, `development_points`; filter by parent skill
- `SkillPointBudgetAdmin` - Single-row model; `has_add_permission` returns False if row exists, `has_delete_permission` always False

---

## Integration Points

- **Trait System**: `Skill.trait` is a OneToOneField to `Trait` (trait_type=SKILL), giving skills unified check resolution
- **Classes/Paths app**: `PathSkillSuggestion` links to `classes.Path` for CG skill templates
- **Character Creation**: Stage 5 uses skills for allocation with point budgets
- **Character Sheets**: Display skills with development progress and rust status
- **Checks app**: Skill values feed into check resolution via the Trait system
