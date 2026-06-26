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
| `TrainingAllocation` | Weekly training plan entry for a skill/specialization | `character` (FK ObjectDB), `skill` (FK Skill, XOR), `specialization` (FK Specialization, XOR), `mentor` (FK Persona, optional), `ap_amount` |

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

## Training Allocations

Persistent weekly training plans map Action Points to development-point gains for a single
skill or specialization. All mutations run through `ManageTrainingAction`
(`actions/definitions/progression.py`, registry key `manage_training`) and are reached by both
the web API and the telnet `training` command.

### Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrainingAllocation` | One weekly plan entry | `character`, `skill` (XOR), `specialization` (XOR), `mentor` (optional Persona), `ap_amount` |

Constraints enforce exactly one of `skill`/`specialization`, `ap_amount >= 1`, and uniqueness
per `(character, skill)` and `(character, specialization)`.

### Service Functions (`world/skills/services.py`)

| Function | Purpose |
|----------|---------|
| `create_training_allocation(character, ap_amount, *, skill, specialization, mentor)` | Creates an allocation, validating the weekly AP budget |
| `update_training_allocation(allocation, *, ap_amount, mentor)` | Updates an existing allocation |
| `remove_training_allocation(allocation)` | Deletes an allocation |
| `calculate_training_development(allocation)` | Computes development points from the training formula |
| `process_weekly_training()` | Processes all allocations, awards dev points, consumes AP |
| `apply_weekly_rust(trained_skills)` | Adds rust to untrained skills |
| `run_weekly_skill_cron()` | Orchestrator: training then rust; registered as `skills.weekly_training` in `world/game_clock/tasks.py` |

### Training Formula

```
base_gain     = 5 × AP × path_level
mentor_bonus  = (AP + teaching) × (mentor_skill / student_skill) × (relationship_tier + 1)
dev_points    = base_gain + mentor_bonus
```

### API Endpoints

- `GET /api/skills/training-allocations/` — List the played character's allocations plus remaining weekly AP budget
  - Response: `{ allocations: [...], remaining_weekly_budget: <int> }`
- `POST /api/skills/training-allocations/` — Create an allocation; body `{ skill_id | specialization_id, ap_amount, mentor_persona_id? }`
- `PATCH /api/skills/training-allocations/{id}/` — Update `ap_amount` and/or `mentor_persona_id`
- `DELETE /api/skills/training-allocations/{id}/` — Remove the allocation

All writes dispatch through `ManageTrainingAction` (`registry_key="manage_training"`) so the
web and telnet paths share the same validation and mutation logic.

### Telnet Command

Defined in `commands/progression.py`:

```
training                           — list allocations and weekly AP budget
training add skill=<id> ap=<n> [mentor=<id>]
training add spec=<id> ap=<n> [mentor=<id>]
training update id=<id> [ap=<n>] [mentor=<id>]
training remove id=<id>
```

`spec` is an alias for `specialization`. Omitting `mentor` on update leaves it unchanged;
`mentor=` (empty) clears the mentor.

### Cron

`run_weekly_skill_cron()` is registered in `world/game_clock/tasks.py` as the weekly task
`skills.weekly_training` (`interval=7 days`, anchored Sunday midnight EST / Monday 05:00 UTC,
same cadence as `weekly_rollover`). It processes every character's allocations, awards
`DevelopmentTransaction` rows with `source=TRAINING` and `reason=SYSTEM_AWARD`, and then
applies weekly rust to skills that received no training (or other development) that week.

---

## Integration Points

- **Trait System**: `Skill.trait` is a OneToOneField to `Trait` (trait_type=SKILL), giving skills unified check resolution
- **Classes/Paths app**: `PathSkillSuggestion` links to `classes.Path` for CG skill templates
- **Character Creation**: Stage 5 uses skills for allocation with point budgets
- **Character Sheets**: Display skills with development progress and rust status
- **Checks app**: Skill values feed into check resolution via the Trait system
- **Action Points**: Training allocations consume weekly AP from `ActionPointPool`
- **Progression**: `process_weekly_training()` writes `DevelopmentTransaction` records (source `TRAINING`, reason `SYSTEM_AWARD`)
