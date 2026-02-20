# Goals System

Goal domain allocation and journal-based XP progression with percentage-based bonus modifiers.

**Source:** `src/world/goals/`
**API Base:** `/api/goals/`

---

## Enums (constants.py)

```python
from world.goals.constants import GoalStatus
# ACTIVE    - Currently pursuing
# INACTIVE  - Paused
# COMPLETED - Successfully achieved
# FAILED    - Did not achieve
# ABANDONED - Gave up
```

---

## Types (types.py)

```python
from world.goals.types import GoalInputData, GoalBonusBreakdown

# GoalInputData (TypedDict) - Input shape for a single goal allocation
#   domain: int (ModifierType PK), points: int, notes: NotRequired[str]

# GoalBonusBreakdown (dataclass) - Breakdown of goal bonus calculation
#   base_points: int, percent_modifier: int, final_bonus: int
```

---

## Models

### Character Goals

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterGoal` | Character's point allocation in a goal domain | `character` (ObjectDB), `domain` (ModifierType with category='goal'), `points`, `notes`, `status` (GoalStatus), `completed_at`, `updated_at` |
| `GoalRevision` | Tracks when goals were last revised (weekly limit) | `character` (OneToOne ObjectDB), `last_revised_at` |
| `GoalInstance` | Records each time a goal was applied to a roll | `goal` (CharacterGoal), `roll_story`, `created_at` |

### Journals

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `GoalJournal` | Journal entries about goal progress that award XP | `character` (ObjectDB), `domain` (ModifierType, nullable), `title`, `content`, `is_public`, `xp_awarded`, `created_at` |

**Design note:** Goal domains are stored as `ModifierType` entries with `category='goal'`, not as a separate model. The `OPTIONAL_GOAL_DOMAINS` set (currently `{"Drives"}`) identifies domains that do not require point allocation.

Characters distribute 30 points (`MAX_GOAL_POINTS`) across domains. Points in a domain add as a situational bonus when making checks that align with the goal.

---

## Key Methods

### GoalRevision

```python
from world.goals.models import GoalRevision

revision, _ = GoalRevision.objects.get_or_create(character=character)

# Check if a week has passed since last revision
if revision.can_revise():
    # ... update goals ...
    revision.mark_revised()  # Sets last_revised_at to now
```

### Service Functions (services.py)

```python
from world.goals.services import (
    get_goal_bonus,
    get_total_goal_points,
    get_goal_bonuses_breakdown,
)

# Get final goal bonus for a domain (base * percentage modifiers)
bonus = get_goal_bonus(character_sheet, "Standing")
# Formula: base_points * (1 + percent_modifiers/100)

# Get total distributable points (base 30 + modifier bonuses)
total = get_total_goal_points(character_sheet)

# Get full breakdown for all domains
breakdown = get_goal_bonuses_breakdown(character_sheet)
# Returns dict[str, GoalBonusBreakdown] mapping domain name to breakdown
# Each GoalBonusBreakdown has: base_points, percent_modifier, final_bonus
```

**Percentage modifiers** come from `CharacterModifier` entries linked to distinction effects:
- `goal_percent/all` - applies to all goal bonuses
- `goal_percent/<domain_name>` - applies to a specific domain

**Point modifiers** come from:
- `goal_points/total_points` - adds to the base 30 distributable points

---

## API Endpoints

### Domains
- `GET /api/goals/domains/` - List goal domains (ModifierType with category='goal')
- `GET /api/goals/domains/{id}/` - Get domain detail

Response includes `is_optional` flag for domains that don't require point allocation.

### Character Goals
- `GET /api/goals/my-goals/` - Get character's goals, total points, and revision status
- `POST /api/goals/my-goals/update/` - Update all goals at once (bulk replace)

Requires `X-Character-ID` header. Weekly revision limit enforced (first-time setting is exempt).

**Update request body:**
```json
{
    "goals": [
        {"domain": 1, "points": 15, "notes": "Become Count"},
        {"domain": 5, "points": 10, "notes": "Protect my family"}
    ]
}
```

**Validation:**
- Total points cannot exceed `MAX_GOAL_POINTS` (30)
- No duplicate domains allowed
- Domain IDs must be valid ModifierType entries with category='goal'

### Journals
- `GET /api/goals/journals/` - List character's journal entries
- `POST /api/goals/journals/` - Create journal entry (awards 1 XP)
- `GET /api/goals/journals/public/` - List public journal entries (paginated)

**Public journals query params:**
- `character_id` - Filter by character (for roster viewing)
- `page`, `page_size` - Pagination (default 20, max 100)

**Create request body:**
```json
{
    "domain": 1,
    "title": "My journey to power",
    "content": "Today I made progress...",
    "is_public": false
}
```

---

## Admin

Goal domains are managed through the `mechanics.ModifierTypeAdmin` (not in the goals app).

- `CharacterGoalAdmin` - Goal allocations with `list_select_related` for performance, filterable by domain
- `GoalJournalAdmin` - Journal entries with date hierarchy, filterable by public/domain/date
- `GoalRevisionAdmin` - Revision tracking with boolean `can_revise` display column
