# Conditions System

Persistent states on targets (characters, objects, rooms) that modify capabilities, checks, and resistances. Supports progression through stages, damage-over-time, stacking, and condition-condition/damage interactions.

**Source:** `src/world/conditions/`
**API Base:** `/api/conditions/`

---

## Enums (constants.py)

```python
from world.conditions.constants import (
    DurationType,                  # ROUNDS, UNTIL_CURED, UNTIL_USED, UNTIL_END_OF_COMBAT, PERMANENT
    StackBehavior,                 # INTENSITY, DURATION, BOTH
    CapabilityEffectType,          # BLOCKED, REDUCED, ENHANCED
    DamageTickTiming,              # START_OF_ROUND, END_OF_ROUND, ON_ACTION
    ConditionInteractionTrigger,   # ON_OTHER_APPLIED, ON_SELF_APPLIED, WHILE_BOTH_PRESENT
    ConditionInteractionOutcome,   # REMOVE_SELF, REMOVE_OTHER, REMOVE_BOTH, PREVENT_OTHER,
                                   # PREVENT_SELF, TRANSFORM_SELF, MERGE
)
```

## Types (types.py)

```python
from world.conditions.types import (
    ApplyConditionResult,        # success, instance, message, stacks_added, was_prevented, ...
    DamageInteractionResult,     # damage_modifier_percent, removed_conditions, applied_conditions
    CapabilityStatus,            # is_blocked, modifier_percent, blocking_conditions
    CheckModifierResult,         # total_modifier, breakdown
    ResistanceModifierResult,    # total_modifier, breakdown
    RoundTickResult,             # damage_dealt, progressed_conditions, expired/removed_conditions
    InteractionResult,           # removed, applied
    CapabilitySummary,           # blocked (list[str]), modifiers (dict[str, int])
    EffectLookups,               # effect_filter, instance_by_condition, instance_by_stage
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionCategory` | High-level groupings (damage-over-time, buff, debuff, etc.) | `name`, `description`, `display_order`, `is_negative` |
| `CapabilityType` | Actions that conditions can restrict/enhance | `name`, `description` |
| `CheckType` | Check types that receive bonuses/penalties | `name`, `description` |
| `DamageType` | Damage types for dealing/resisting | `name`, `description`, `resonance` (OneToOne to `mechanics.ModifierType`), `color_hex`, `icon` |

### Condition Templates (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionTemplate` | Condition definition (e.g., Burning, Frozen) | `name`, `category`, `description`, `player_description`, `observer_description`, duration settings, stacking settings, progression flag, removal settings, combat settings (`affects_turn_order`, `draws_aggro`), display settings |
| `ConditionStage` | Stage in a progressive condition | `condition`, `stage_order`, `name`, `rounds_to_next`, `resist_check_type`, `resist_difficulty`, `severity_multiplier` |

### Condition Effects (Abstract base: `ConditionOrStageEffect`)

Effects use mutually exclusive FKs: `condition` (all stages) OR `stage` (stage-specific). Exactly one must be set.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionCapabilityEffect` | How a condition affects a capability | `capability`, `effect_type` (BLOCKED/REDUCED/ENHANCED), `modifier_percent` |
| `ConditionCheckModifier` | How a condition modifies checks | `check_type`, `modifier_value`, `scales_with_severity` |
| `ConditionResistanceModifier` | How a condition modifies damage resistance | `damage_type` (null = ALL), `modifier_value` |
| `ConditionDamageOverTime` | Periodic damage from a condition | `damage_type`, `base_damage`, `scales_with_severity`, `scales_with_stacks`, `tick_timing` |

### Condition Interactions

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionDamageInteraction` | What happens when a conditioned target takes damage | `condition`, `damage_type`, `damage_modifier_percent`, `removes_condition`, `applies_condition`, `applied_condition_severity` |
| `ConditionConditionInteraction` | How two conditions interact | `condition`, `other_condition`, `trigger`, `outcome`, `result_condition`, `priority` |

### Runtime State (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionInstance` | Active condition on a target | `target` (FK to ObjectDB), `condition`, `current_stage`, `stacks`, `severity`, `applied_at`, `expires_at`, `rounds_remaining`, `stage_rounds_remaining`, `source_character`, `source_technique`, `source_description`, `is_suppressed`, `suppressed_until` |

---

## Key Methods

### Service Functions

```python
from world.conditions.services import (
    # Core operations
    apply_condition,               # Apply with stacking/interaction handling (atomic)
    remove_condition,              # Remove condition (optionally just one stack)
    remove_conditions_by_category, # Remove all in a category
    clear_all_conditions,          # Bulk removal with filters

    # Queries
    get_active_conditions,         # QuerySet of active instances on target
    has_condition,                 # Bool check for specific condition
    get_condition_instance,        # Get single instance or None

    # Modifier queries
    get_capability_status,         # CapabilityStatus (blocked/modified)
    get_check_modifier,            # CheckModifierResult (total + breakdown)
    get_resistance_modifier,       # ResistanceModifierResult (total + breakdown)
    get_turn_order_modifier,       # Int modifier to initiative
    get_aggro_priority,            # Int priority for targeting

    # Round processing
    process_round_start,           # Start-of-round DoT and effects
    process_round_end,             # End-of-round DoT, duration countdown, progression
    process_action_tick,           # On-action DoT

    # Damage interactions
    process_damage_interactions,   # Handle condition reactions to damage

    # Suppression
    suppress_condition,            # Temporarily disable effects
    unsuppress_condition,          # Re-enable effects

    # Distinction-based percentage modifiers
    get_condition_control_percent_modifier,    # Control loss rate modifier
    get_condition_intensity_percent_modifier,  # Intensity gain modifier
    get_condition_penalty_percent_modifier,    # Check penalty modifier
)
```

### Applying a Condition

```python
from world.conditions.services import apply_condition

result = apply_condition(
    target=character,
    condition=burning_template,
    severity=2,
    duration_rounds=5,
    source_character=attacker,
    source_technique=fire_bolt,
)
# result.success, result.instance, result.was_prevented, result.removed_conditions
```

### Querying Modifiers

```python
from world.conditions.services import get_check_modifier, get_capability_status

# Check modifier from all conditions
result = get_check_modifier(character, stealth_check_type)
result.total_modifier   # -20
result.breakdown        # [(frozen_instance, -10), (wounded_instance, -10)]

# Capability status
status = get_capability_status(character, movement_capability)
status.is_blocked          # True if any condition blocks it
status.modifier_percent    # Net percentage modifier
```

### ConditionInstance Properties

```python
instance.is_expired         # True if rounds_remaining <= 0
instance.effective_severity # severity * stage.severity_multiplier
```

---

## API Endpoints

### Lookup Data (Read-Only)
- `GET /api/conditions/categories/` - Condition categories
- `GET /api/conditions/capabilities/` - Capability types
- `GET /api/conditions/check-types/` - Check types
- `GET /api/conditions/damage-types/` - Damage types

### Templates (Read-Only)
- `GET /api/conditions/templates/` - List condition templates
- `GET /api/conditions/templates/{id}/` - Template detail with stages/effects
- `GET /api/conditions/templates/by_category/` - Grouped by category

### Character Conditions (Requires X-Character-ID header)
- `GET /api/conditions/character/` - Active conditions on character
- `GET /api/conditions/character/summary/` - Conditions with aggregated effects (capabilities, checks, resistances, turn order, aggro)
- `GET /api/conditions/character/observed/?target_id=X` - Conditions visible to observers

Note: Conditions are applied through game logic, not directly through the API.

---

## Design Principles

- **Everything is math**: No binary immunity. Intensity - Resistance = Net Value.
- **Bidirectional modifiers**: Conditions can be good or bad depending on context.
- **Abstract base effects**: `ConditionOrStageEffect` uses mutually exclusive FKs for condition-level vs stage-specific effects.
- **Batch queries**: Views aggregate effects in 3 queries instead of N per condition type.

---

## Admin

All models registered with comprehensive admin interfaces:

- `ConditionTemplateAdmin` - Full editing with 7 inlines (stages, capability effects, check modifiers, resistance modifiers, DoT, damage interactions, condition interactions)
- `ConditionStageAdmin` - Stage management with autocomplete
- `ConditionInstanceAdmin` - Runtime debugging with state/timing/source fieldsets
- Lookup table admins for categories, capabilities, check types, damage types
- Standalone interaction admins for damage and condition interactions
