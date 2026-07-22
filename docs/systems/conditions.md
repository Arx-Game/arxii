# Conditions System

Persistent states on targets (characters, objects, rooms) that modify capabilities, checks, and resistances. Supports progression through stages, damage-over-time, stacking, and condition-condition/damage interactions.

**Source:** `src/world/conditions/`
**API Base:** `/api/conditions/`

---

## Enums (constants.py)

```python
from world.conditions.constants import (
    DurationType,                  # ROUNDS, UNTIL_CURED, UNTIL_USED, UNTIL_END_OF_COMBAT, SCENE, INGAME_TIME, PERMANENT
    StackBehavior,                 # INTENSITY, DURATION, BOTH
    DamageTickTiming,              # START_OF_ROUND, END_OF_ROUND, ON_ACTION
    ConditionInteractionTrigger,   # ON_OTHER_APPLIED, ON_SELF_APPLIED, WHILE_BOTH_PRESENT
    ConditionInteractionOutcome,   # REMOVE_SELF, REMOVE_OTHER, REMOVE_BOTH, PREVENT_OTHER,
                                   # PREVENT_SELF, TRANSFORM_SELF, MERGE
    Allegiance,                    # ENEMY, ALLY_OF_CASTER, NEUTRAL
    CHARM_CONDITION_NAME,          # "Charmed"
    CALM_CONDITION_NAME,           # "Calm"
)
```

## Types (types.py)

```python
from world.conditions.types import (
    ApplyConditionResult,        # success, instance, message, stacks_added, was_prevented, ...
    DamageInteractionResult,     # damage_modifier_percent, removed_conditions, applied_conditions
    CapabilityStatus,            # value, condition_contributions
    CheckModifierResult,         # total_modifier, breakdown
    ResistanceModifierResult,    # total_modifier, breakdown
    RoundTickResult,             # damage_dealt, progressed_conditions, expired/removed_conditions
    InteractionResult,           # removed, applied
    CapabilitySummary,           # values (dict[str, int])
    EffectLookups,               # effect_filter, instance_by_condition, instance_by_stage
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionCategory` | High-level groupings (damage-over-time, buff, debuff, etc.) | `name`, `description`, `display_order`, `is_negative`, `alters_behavior` |
| `CapabilityType` | Actions that conditions can restrict/enhance | `name`, `description` |
| `CheckType` | Check types that receive bonuses/penalties | `name`, `description` |
| `DamageType` | Damage types for dealing/resisting | `name`, `description`, `resonance` (OneToOne to `mechanics.ModifierTarget`), `color_hex`, `icon` |

### Condition Templates (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionTemplate` | Condition definition (e.g., Burning, Frozen) | `name`, `category`, `description`, `player_description`, `observer_description`, duration settings, stacking settings, progression flag, removal settings (`cure_check_type`/`cure_difficulty`), apply-time resist-check (`resist_check_type`/`resist_difficulty`, #1738), combat settings (`affects_turn_order`, `draws_aggro`), display settings |
| `ConditionStage` | Stage in a progressive condition | `condition`, `stage_order`, `name`, `rounds_to_next`, `resist_check_type`, `resist_difficulty`, `severity_multiplier` |

**Charm / Calm content (#1590).** The `Charm` `ConditionCategory` (`alters_behavior=True`) and
`Charmed` / `Calm` templates are seeded idempotently by `ensure_charm_content()` in
`world.conditions.charm_content`, aggregated via `ensure_conditions_content()`. The
`Allegiance` enum is derived from active `alters_behavior` conditions on an NPC. Charm on an
NPC alters a non-player's behavior; ADR-0024's PC consent gate does not apply. See ADR-0058 for
the two-tier NPC disposition model.

### Condition Effects (Abstract base: `ConditionOrStageEffect`)

Effects use mutually exclusive FKs: `condition` (all stages) OR `stage` (stage-specific). Exactly one must be set.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionCapabilityEffect` | How a condition affects a capability | `capability`, `value` (additive integer; negative reduces, positive enhances) |
| `ConditionCheckModifier` | How a condition modifies checks | `check_type`, `modifier_value`, `scales_with_severity` |
| `ConditionResistanceModifier` | How a condition modifies damage resistance | `damage_type` (null = ALL), `modifier_value` |
| `ConditionDamageOverTime` | Periodic damage from a condition | `damage_type`, `base_damage`, `scales_with_severity`, `scales_with_stacks`, `tick_timing` |

#### DoT tick timing (`DamageTickTiming`) — #1762

`tick_timing` decides *when in a round* a `ConditionDamageOverTime` fires. **`END_OF_ROUND`
is the convention and the model/factory default** (poison, sunlight) — use it unless you
have a specific reason not to.

| Value | When it fires | Notes |
|-------|---------------|-------|
| `END_OF_ROUND` | After the round's actions resolve (`status == RESOLVING` in combat; the only tick scene rounds fire) | **Default.** Shieldable by Succor/Interpose; ticks in both combat and non-combat scene rounds. |
| `START_OF_ROUND` | Top of the round, during `DECLARING`, *before any action resolves* | Deliberate "unpreventable top-of-round damage" opt-in. **Intentionally un-shieldable** by Succor/Interpose (no ally has acted yet). **Inert in non-combat scene rounds** — the scene-round lifecycle only ever ticks `timing="end"` (`scenes/round_services.py`); no `timing="start"` path exists outside `combat/services.py:begin_declaration_phase`. A hazard that needs to actually damage in scene rounds would have to build that scene-round START tick first. |
| `ON_ACTION` | When the bearer takes an action (`process_action_tick`) | — |

Choosing `START_OF_ROUND` is guarded: `world/conditions/tests/test_tick_timing_guard.py`
locks the `END_OF_ROUND` defaults and fails if authored DoT content ships `START_OF_ROUND`
without being listed (with justification) in that test's `ACKNOWLEDGED_START_OF_ROUND_HAZARDS`.

### Condition Interactions

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionDamageInteraction` | What happens when a conditioned target takes damage | `condition`, `damage_type`, `damage_modifier_percent`, `removes_condition`, `applies_condition`, `applied_condition_severity` |
| `ConditionConditionInteraction` | How two conditions interact | `condition`, `other_condition`, `trigger`, `outcome`, `result_condition`, `priority` |

### Runtime State (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionInstance` | Active condition on a target | `target` (FK to ObjectDB), `condition`, `current_stage`, `stacks`, `severity`, `applied_at`, `expires_at`, `rounds_remaining`, `stage_rounds_remaining`, `source_character`, `source_technique`, `source_vow` (#2643: nullable FK → `covenants.CovenantRole`, `SET_NULL` — the applier's engaged-vow anchor at apply time; drives vow-keyed diminishing returns on the bounded team-damage-percent lane, see `docs/systems/magic.md`), `source_description`, `is_suppressed`, `suppressed_until`, `resolved_at`, `abandoned_since_round` (#1479: round at which a downed bearer's acute peril was held/abandoned; cleared when a hostile party drives again) |

---

## Key Methods

### Service Functions

```python
from world.conditions.services import (
    # Core operations
    apply_condition,               # Apply with stacking/interaction handling (atomic)
    remove_condition,              # Remove condition (optionally just one stack / incl. suppressed)
    remove_conditions_by_category, # Remove all in a category
    clear_all_conditions,          # Bulk removal with filters
    expire_end_of_combat_conditions, # Sweep UNTIL_END_OF_COMBAT conds on targets at combat end
    expire_scene_scoped_conditions,  # Sweep SCENE-duration conds on targets at scene end (#2514)

    # Queries
    get_active_conditions,         # QuerySet of active instances on target
    has_condition,                 # Bool check for specific condition
    get_condition_instance,        # Get single instance or None

    # Modifier queries
    get_capability_status,         # CapabilityStatus (value + breakdown)
    get_capability_value,          # Int value for a single capability
    get_all_capability_values,     # dict[str, int] for all capabilities
    get_check_modifier,            # CheckModifierResult (total + breakdown)
    get_resistance_modifier,       # ResistanceModifierResult (total + breakdown)
    get_turn_order_modifier,       # Int modifier to initiative
    get_aggro_priority,            # Int priority for targeting
    get_condition_modifier_vow_contributions, # Per-instance (source_vow_id, name, value) rows for a ModifierTarget (#2643)
    priced_percent_severity,       # Apply-time percent severity priced vs the landing target's level (#2643)

    # Round processing
    process_round_start,           # Start-of-round DoT and effects
    process_round_end,             # End-of-round DoT, duration countdown, progression
    process_action_tick,           # On-action DoT

    # Damage interactions
    process_damage_interactions,   # Handle condition reactions to damage (wired into combat #2018)

    # Suppression
    suppress_condition,            # Temporarily disable effects
    unsuppress_condition,          # Re-enable effects

    # Distinction-based percentage modifiers
    get_condition_control_percent_modifier,    # Control loss rate modifier
    get_condition_intensity_percent_modifier,  # Intensity gain modifier
    get_condition_penalty_percent_modifier,    # Check penalty modifier

    # Treatment (player surface)
    get_treatment_candidates,    # Discover which treatments can target which effects
    perform_treatment,             # Apply a treatment to reduce severity/tier
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

### Resisting Application (#1738)

When `condition.resist_check_type` is set, `apply_condition`/`bulk_apply_conditions`
roll the *target's* check against `resist_difficulty` before creating the instance.
Success (SL > 0) means the target resisted — no instance is created, and the result
carries `message="resisted"`. `resist_check_type=None` (the default) means
unconditional application. Resistance strength comes from the existing check-modifier
seam: a permanent condition (e.g. a species benefit condition, see
`SpeciesGiftGrant.benefit_condition` in the species system doc) carrying a
`ConditionCheckModifier` for the resist check type raises the target's roll —
"math, not a boolean," per ADR-0073's tenet extended to the condition-application
axis.

### Damage Interactions (#2018)

`process_damage_interactions(target, damage_type)` is called from
`apply_damage_to_opponent` and `apply_damage_to_participant` after all
soak, resistance, and armor reductions. It applies the `damage_modifier_percent`
as a final multiplier on net damage, and may consume (`removes_condition=True`)
or transform (`applies_condition` set) the condition.

**Narration rule:** The synergy beat fires only on condition transitions
(removal or application). A pure damage-modifier interaction with no
transition is silent math — this prevents spam while keeping dramatic
moments visible. Authored `narration_snippet` text is used when present;
otherwise a deterministic fallback is composed.

**Enemy-side bound (#2643):** the summed `damage_modifier_percent` across every
matching `ConditionDamageInteraction` row is clamped to
`±combat.constants.ENEMY_LANE_CAP_PERCENT` (default 50) in
`world.combat.services._apply_condition_damage_interactions` before it multiplies net
damage — the clamp bounds only the live application; the unclamped sum still reports
on the returned `DamageInteractionResult`. See `docs/systems/magic.md`'s "The Damage
Identity" section for the sibling bounded percent lane (the ally-buff side) and
ADR-0158.

### Bounded-Percent Lane Pricing (#2643)

`priced_percent_severity(*, eff_intensity, target)` computes an apply-time severity
for a percent-lane condition (authored `value=1` + `scales_with_severity=True`),
priced inversely against the landing target's level:
`clamp(round(eff_intensity * PCT_PER_POWER_TENTHS / 10 / max(1, target_level)), 1,
TEAM_BUFF_LANE_CAP_PERCENT)`. `target_level` resolves generically — a PC target reads
`CharacterSheet.current_level`; a `CombatOpponent` target reads its pseudo-level from
`combat.constants.OPPONENT_TIER_LEVEL`. Wired into the shared
`world.magic.services.condition_application.apply_technique_conditions` seam — see
`docs/systems/magic.md`'s "The Damage Identity" section for the full lane composition
(vow-keyed stacking, the clamp, the execute ramp) and ADR-0158.

### Querying Modifiers

```python
from world.conditions.services import (
    get_check_modifier,
    get_capability_status,
    get_capability_value,
    get_all_capability_values,
)

# Check modifier from all conditions
result = get_check_modifier(character, stealth_check_type)
result.total_modifier   # -20
result.breakdown        # [(frozen_instance, -10), (wounded_instance, -10)]

# Capability value (additive, floor at 0)
status = get_capability_status(character, movement_capability)
status.value                    # 5 (sum of all condition effects, floored at 0)
status.condition_contributions  # [(slowed_instance, -5), (hasted_instance, 10)]

# Convenience: just the value
value = get_capability_value(character, flight_capability)  # 0 = can't fly

# Bulk: all capabilities at once (used by obstacle system)
caps = get_all_capability_values(character)  # {"movement": 5, "flight": 0}
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

## Treatment (player surface)

A character can treat another PC's open `ConditionInstance` or pending
`PendingAlteration` through the standard scene consent seam, using either the
telnet `treat` command (`src/commands/conditions.py`) or the web Treat panel
(`TreatActionPanel`). Both paths converge on the same backend: telnet calls
`action.run("treat_condition")`, the web endpoint dispatches the same action
key, and both create a `SceneActionRequest` that is resolved when the target
player accepts.

### Discovery

`get_treatment_candidates(helper_sheet, target_sheet, scene)` returns the list
of treatments the helper can apply to the target right now. Each candidate is a
dict carrying `treatment`, `target_effect`, `target_effect_type`
(`TARGET_EFFECT_CONDITION` or `TARGET_EFFECT_ALTERATION` from
`world.conditions.constants`), and `bond_thread`. The same scene/engagement/bond
gates used by `perform_treatment` are applied during discovery, so the candidate
list is authoritative.

The web discovery endpoint `GET /api/conditions/treatments/?target_persona_id=N`
returns a `TreatmentCandidateResponse` envelope (`candidates` + `scene_id`).
Telnet uses the same query to prompt the helper.

### Consent flow

Treatment targets another PC and therefore flows through
`create_action_request` → `respond_to_action_request`. Treatment is not
behavior-altering, so it uses the default-allow consent model: the helper sees
the target among candidates, the request is sent, and the target player chooses
ACCEPT or DENY.

### Resolution seam

Treatment requests bypass the `ActionTemplate`/`_resolve_standard_action`
chain because treatment carries its own check/cost/reduction logic. They are
resolved by the **custom-action-resolver registry** in
`world.scenes.action_services` (`CUSTOM_ACTION_RESOLVERS`), registered for the
action key `"treat_condition"`. On ACCEPT the dispatcher checks the registry
before the standard path; the resolver calls `perform_treatment` plus
`create_interaction` and returns `None` (no `PendingActionResolution` is handed
back to the SCENE_ADAPTIVE pipeline).

The web execution path re-validates the chosen candidate pair server-side via
`get_treatment_candidates`, so a client cannot fabricate a treatment/effect
pair that evades scene, engagement, or bond gating.

See ADR-0048 for the rationale behind the custom-action-resolver registry.

---

## Design Principles

- **Everything is math**: No binary immunity. Intensity - Resistance = Net Value.
- **Bidirectional modifiers**: Conditions can be good or bad depending on context.
- **Abstract base effects**: `ConditionOrStageEffect` uses mutually exclusive FKs for condition-level vs stage-specific effects.
- **Batch queries**: Views aggregate effects in 3 queries instead of N per condition type.

## Behavior-altering categories

`ConditionCategory.alters_behavior` marks conditions that change how a character
*behaves* (compulsion, charm, fear, rage) rather than only their capabilities or
stats. It is the consent signal used by cast targeting and by
`CharacterSheet.in_control`. The canonical seeded behavior-altering category is
`Control` (`alters_behavior=True`), and the `Berserk` condition created by the fury
system belongs to it.

---

## Admin

All models registered with comprehensive admin interfaces:

- `ConditionTemplateAdmin` - Full editing with 7 inlines (stages, capability effects, check modifiers, resistance modifiers, DoT, damage interactions, condition interactions)
- `ConditionStageAdmin` - Stage management with autocomplete
- `ConditionInstanceAdmin` - Runtime debugging with state/timing/source fieldsets
- Lookup table admins for categories, capabilities, check types, damage types
- Standalone interaction admins for damage and condition interactions

---

## Dynamic Thumbnails (#2196)

`ConditionTemplate`, `ConditionStage`, and `AlternateSelf` each have an optional
`thumbnail` FK to `Media` (renamed from `PlayerMedia`, #2408). When set, the thumbnail overrides the persona's
default in all serialization surfaces (room state, combat, character sheet).

Resolution is handled by `world.conditions.thumbnail_services.resolve_thumbnail()`,
which checks in priority order:
1. Active condition's stage thumbnail (highest `display_priority` visible condition)
2. Active condition's template thumbnail
3. Active alternate self's thumbnail
4. Persona's `thumbnail` FK
5. `ObjectDisplayData.thumbnail` fallback
6. `fallback_media` (e.g. `CombatOpponent.portrait` for persona-less NPCs)

Hidden conditions (`is_visible_to_others=False`) do not override the thumbnail
for non-privileged viewers — the same visibility gate as condition serialization.
