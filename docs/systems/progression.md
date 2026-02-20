# Progression System

XP, kudos, development points, character-level XP, path history, and unlock system for character advancement.

**Source:** `src/world/progression/`
**API Base:** `/api/progression/`

---

## Enums (types.py)

```python
from world.progression.types import (
    UnlockType,          # LEVEL, SKILL_RATING, STAT_RATING, ABILITY, OTHER
    DevelopmentSource,   # SCENE, TRAINING, PRACTICE, TEACHING, QUEST, EXPLORATION, CRAFTING, COMBAT, SOCIAL, OTHER
    ProgressionReason,   # XP_PURCHASE, CG_CONVERSION, SCENE_AWARD, GM_AWARD, SYSTEM_AWARD, REFUND, CORRECTION, KUDOS_CLAIM, OTHER
)

# Typed data structures
from world.progression.types import (
    AwardResult,   # Dataclass: points_data (KudosPointsData), transaction (KudosTransaction)
    ClaimResult,   # Dataclass: points_data (KudosPointsData), transaction (KudosTransaction), reward_amount (int)
)
```

---

## Models

### Account-Level Rewards (XP)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ExperiencePointsData` | Account XP balance (one per account) | `account` (PK, OneToOne AccountDB), `total_earned`, `total_spent` |
| `XPTransaction` | Audit trail for all account XP changes | `account`, `amount`, `reason` (ProgressionReason), `description`, `character`, `gm`, `transaction_date` |

### Character-Level XP

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterXP` | Per-character XP balance, partitioned by transferability | `character`, `total_earned`, `total_spent`, `transferable` |
| `CharacterXPTransaction` | Audit trail for character-level XP changes | `character`, `amount`, `reason` (ProgressionReason), `description`, `transferable`, `transaction_date` |

### Development Points (Auto-Applied Trait Growth)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DevelopmentPoints` | Per-character, per-trait development tracker | `character`, `trait`, `total_earned` |
| `DevelopmentTransaction` | Audit trail for all development point awards | `character`, `trait`, `source` (DevelopmentSource), `amount`, `reason`, `description`, `scene`, `gm`, `transaction_date` |

### Kudos ("Good Sport" Currency)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `KudosSourceCategory` | Staff-configurable award categories (SharedMemoryModel) | `name`, `display_name`, `description`, `default_amount`, `is_active`, `staff_only` |
| `KudosClaimCategory` | Staff-configurable claim/conversion types (SharedMemoryModel) | `name`, `display_name`, `description`, `kudos_cost`, `reward_amount`, `is_active` |
| `KudosPointsData` | Account kudos balance (one per account) | `account` (PK, OneToOne AccountDB), `total_earned`, `total_claimed` |
| `KudosTransaction` | Audit trail for all kudos awards and claims | `account`, `amount`, `source_category`, `claim_category`, `description`, `awarded_by`, `character`, `transaction_date` |

### XP Cost System (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `XPCostChart` | Reusable cost curves for classes/traits | `name`, `description`, `is_active` |
| `XPCostEntry` | Individual level/cost entries within a chart | `chart`, `level`, `xp_cost` |
| `ClassXPCost` | Links classes to cost charts with optional modifier | `character_class`, `cost_chart`, `cost_modifier` (percentage, 100 = normal) |
| `TraitXPCost` | Links traits to cost charts with optional modifier | `trait`, `cost_chart`, `cost_modifier` (percentage) |

### Unlock Types

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ClassLevelUnlock` | Unlocking a new level in a character class | `character_class`, `target_level` |
| `TraitRatingUnlock` | Unlocking a major trait rating threshold | `trait`, `target_rating` (divisible by 10) |
| `CharacterUnlock` | Records what class levels a character has unlocked | `character`, `character_class`, `target_level`, `unlocked_date`, `xp_spent` |

### Requirements (Abstract Hierarchy)

All requirements inherit from `AbstractClassLevelRequirement` which provides `description`, `is_active`, and FK to `ClassLevelUnlock`. Each implements `is_met_by_character(character)` returning `(bool, str)`.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TraitRequirement` | Minimum trait value required | `trait`, `minimum_value` |
| `LevelRequirement` | Minimum character level in any class | `minimum_level` |
| `ClassLevelRequirement` | Minimum level in a specific class | `character_class`, `minimum_level` |
| `MultiClassRequirement` | Multiple classes at specific levels (via `MultiClassLevel` through model) | `required_classes`, `description_override` |
| `TierRequirement` | Character has reached a specific tier | `minimum_tier` (1 for levels 1-5, 2 for 6-10) |
| `AchievementRequirement` | Story progress/achievement flag | `achievement_key` |
| `RelationshipRequirement` | Character relationship level | `relationship_target`, `minimum_level` |

### Path History

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterPathHistory` | Tracks which path a character selected at each stage milestone | `character`, `path`, `selected_at` |

---

## Key Methods

### ExperiencePointsData / CharacterXP

```python
from world.progression.models import ExperiencePointsData, CharacterXP

# Account-level XP
xp_data = ExperiencePointsData.objects.get(account=account)
xp_data.current_available  # Property: total_earned - total_spent
xp_data.can_spend(100)     # Check if enough XP
xp_data.spend_xp(100)      # Spend XP (returns bool)
xp_data.award_xp(50)       # Award XP

# Character-level XP (partitioned by transferable flag)
char_xp = CharacterXP.objects.get(character=character, transferable=True)
char_xp.current_available  # Property: total_earned - total_spent
char_xp.spend_xp(50)       # Returns bool
char_xp.award_xp(25)       # Awards XP
```

### DevelopmentPoints

```python
from world.progression.models import DevelopmentPoints

dev = DevelopmentPoints.objects.get(character=character, trait=trait)
# Awards points AND automatically applies them to CharacterTraitValue
# Caps at major thresholds (multiples of 10) if unlock not present
dev.award_points(5)
```

### KudosClaimCategory

```python
from world.progression.models import KudosClaimCategory

claim_cat = KudosClaimCategory.objects.get(name="xp")
claim_cat.calculate_reward(kudos_amount=20)       # How much reward for 20 kudos
claim_cat.calculate_kudos_needed(reward_amount=5)  # How many kudos for 5 reward units
```

### XP Cost Lookups

```python
from world.progression.models import XPCostChart, ClassXPCost, TraitXPCost

chart = XPCostChart.objects.get(name="Standard")
chart.get_cost_for_level(3)  # Base XP cost for level 3

class_cost = ClassXPCost.objects.get(character_class=my_class)
class_cost.get_cost_for_level(3)  # Modified cost (applies cost_modifier percentage)

trait_cost = TraitXPCost.objects.get(trait=my_trait)
trait_cost.get_cost_for_rating(20)  # Modified cost for rating threshold
```

### Unlock / Requirement Checking

```python
from world.progression.models import ClassLevelUnlock

unlock = ClassLevelUnlock.objects.get(character_class=my_class, target_level=5)
xp_cost = unlock.get_xp_cost_for_character(character)
```

---

## Service Functions

### Awards (`services.awards`)

```python
from world.progression.services import award_xp, award_development_points, get_or_create_xp_tracker
from world.progression.types import DevelopmentSource, ProgressionReason

# Award account-level XP (atomic, creates transaction)
transaction = award_xp(account, 50, reason=ProgressionReason.GM_AWARD, description="Quest reward", gm=gm_account)

# Award development points (auto-applies rate modifiers from distinctions)
transaction = award_development_points(
    character=character,
    trait=trait,
    source=DevelopmentSource.COMBAT,
    amount=5,
    scene=scene,
    reason="Combat training",
    description="Earned during sparring scene",
    gm=gm_account,
)

# Get or create XP tracker
xp_tracker = get_or_create_xp_tracker(account)
```

### Spends (`services.spends`)

```python
from world.progression.services import spend_xp_on_unlock, check_requirements_for_unlock, get_available_unlocks_for_character

# Spend XP on an unlock (checks requirements, spends XP, creates records)
success, message, unlock = spend_xp_on_unlock(character, unlock_target, gm=None)

# Check requirements only
all_met, failed_messages = check_requirements_for_unlock(character, unlock_target)

# Get categorized unlocks for a character
result = get_available_unlocks_for_character(character)
# Returns: {"available": [...], "locked": [...], "already_unlocked": [...]}
```

### CG Conversion (`services.cg_conversion`)

```python
from world.progression.services import award_cg_conversion_xp

# Award locked (non-transferable) XP for unspent CG points
award_cg_conversion_xp(character, remaining_cg_points=10, conversion_rate=2)
# Creates CharacterXP with transferable=False and CharacterXPTransaction
```

### Kudos (`services.kudos`)

```python
from world.progression.services import award_kudos, claim_kudos, InsufficientKudosError

# Award kudos (atomic: updates balance + creates transaction)
result = award_kudos(
    account=account,
    amount=5,
    source_category=source_cat,
    description="Great roleplay during scene",
    awarded_by=gm_account,
    character=character,  # optional: associate with specific character
)
# Returns AwardResult(points_data, transaction)

# Claim kudos for conversion (atomic: updates balance + creates transaction)
result = claim_kudos(
    account=account,
    amount=10,
    claim_category=claim_cat,
    description="Converting to XP",
)
# Returns ClaimResult(points_data, transaction, reward_amount)
# Raises InsufficientKudosError if not enough kudos
```

### Scene Integration (`services.scene_integration`)

```python
from world.progression.services import award_scene_development_points, calculate_automatic_scene_awards

# Calculate automatic awards based on scene content
awards = calculate_automatic_scene_awards(scene, participants)

# Award development points to scene participants
transactions = award_scene_development_points(scene, participants, awards)
```

---

## API Endpoints

### Account Progression Dashboard
- `GET /api/progression/account/` - Current user's XP balance, kudos balance, recent transactions, and claim options

**Query Parameters:**
- `limit` (int) - Max transactions per type (default: 50, max: 200)
- `offset` (int) - Pagination offset (default: 0)

**Response shape:**
```json
{
    "xp": {"total_earned": 100, "total_spent": 20, "current_available": 80},
    "kudos": {"total_earned": 50, "total_claimed": 10, "current_available": 40},
    "xp_transactions": [...],
    "kudos_transactions": [...],
    "claim_categories": [...]
}
```

---

## Integration Points

- **Mechanics**: Development rate modifiers from distinctions (e.g., Spoiled reduces physical skill development by 20%) are applied via `get_modifier_for_character(character, "development", modifier_name)`.
- **Traits**: `DevelopmentPoints.award_points()` auto-applies to `CharacterTraitValue`.
- **Classes**: `ClassLevelUnlock`, `ClassXPCost`, and requirements reference `CharacterClass` and class levels.
- **Scenes**: Scene completion triggers `award_scene_development_points()` for trait-specific development.
- **Character Creation**: CG-to-XP conversion via `award_cg_conversion_xp()` creates locked (non-transferable) `CharacterXP`.

---

## Admin

All models are registered with appropriate filters, search, and inline editing:

- **Rewards**: `ExperiencePointsDataAdmin`, `XPTransactionAdmin`, `DevelopmentPointsAdmin`, `DevelopmentTransactionAdmin`
- **Kudos**: `KudosSourceCategoryAdmin`, `KudosClaimCategoryAdmin`, `KudosPointsDataAdmin` (with transaction link), `KudosTransactionAdmin`
- **Unlocks**: `XPCostChartAdmin` (with `XPCostEntryInline`), `ClassXPCostAdmin`, `TraitXPCostAdmin`, `ClassLevelUnlockAdmin`, `TraitRatingUnlockAdmin`, `CharacterUnlockAdmin`
- **Requirements**: Individual admin classes for each requirement type, `MultiClassRequirementAdmin` (with `MultiClassLevelInline`)
- **Paths**: `CharacterPathHistoryAdmin` with `list_select_related` for performance
