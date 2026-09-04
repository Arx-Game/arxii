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
| `CapabilityType` | Actions that conditions can restrict/enhance | `name`, `description`, `innate_baseline` (int, default 0 — the ladder position every character starts from before modifiers/conditions; #2704, ADR-0164) |
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
| `ConditionCapabilityEffect` | How a condition affects a capability | `capability`, `value` (additive integer; negative reduces, positive enhances), `scales_with_severity` (inherited from `ConditionOrStageEffect`; honoured by all three readers as of #2708 — see "Capability magnitude curve" below) |
| `ConditionCheckModifier` | How a condition modifies checks | `check_type` OR `check_category` (exactly one; category targets all checks in a category, including per-character magic checks — #2697), `modifier_value`, `scales_with_severity` |
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
| `ConditionInstance` | Active condition on a target | `target` (FK to ObjectDB), `condition`, `current_stage`, `stacks`, `severity`, `applied_at`, `expires_at`, `rounds_remaining`, `stage_rounds_remaining`, `source_character`, `source_technique`, `source_vow` (#2643: nullable FK → `covenants.CovenantRole`, `SET_NULL` — the applier's engaged-vow anchor at apply time; drives vow-keyed diminishing returns on the bounded team-damage-percent lane, see `docs/systems/magic.md`), `source_description` (#3554: rendered to the bearer in `ConditionDetailModal` and in the `ConditionBadge` tooltip; `gm_apply_condition` broadcasts a GM's note as a Narrator OUTCOME line, target-only when the template is not `is_visible_to_others`), `is_suppressed`, `suppressed_until`, `resolved_at`, `abandoned_since_round` (#1479: round at which a downed bearer's acute peril was held/abandoned; cleared when a hostile party drives again) |
| `HazardResponseState` | Player-response tracking for an environmental-hazard condition (#2846, ADR-0179) | `condition_instance` (O2O, CASCADE — lifecycle rides the instance), `prompted_at`, `last_health_snapshot`, `damage_observations`, `responded_at`, `endured_until`. Service layer: `world.conditions.hazard_prompt` — `ensure_hazard_prompt` (prompt once: `hazard_prompt` websocket message + telnet text), `observe_hazard` (count sweep-observed health drops; fire the per-hazard `flee` callback after the configured unanswered count — never the first), `mark_endured`/`mark_responded`. Hazard-generic: sunlight supplies its refuge logic from `world.species.sun_refuge`; player answers are the `hazard_endure`/`hazard_retreat` actions. |

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

### Capability value ladder (#2704, ADR-0164)

Every `CapabilityType.innate_baseline` and every effective capability value share
**one deliberately uncapped ladder**:

| Value | Meaning |
|-------|---------|
| 0 | Blocked |
| 1-3 | Impaired |
| 5 | Unimpaired mortal |
| 8-12 | Gifted |
| 25+ | Greater supernatural |
| 100+ | Mythic |

Uncapped above 100 on purpose — a high enough value must let a being do what is
flatly impossible for a mortal; an upper cap would foreclose that on principle.
**The ladder itself is a code-independent design ruling (ADR-0164 D1)** — it is
true regardless of what any given `CapabilityType` row currently holds. The
*baseline value* for a specific capability, by contrast, is **authored content**
(a `CapabilityType.innate_baseline` row maintained as a fixture in the content
repo, not a code constant), and its current state varies by environment:

- The three capacities code actually references —
  `FoundationalCapability.AWARENESS`/`MOVEMENT`/`LIMB_USE`
  (`world/conditions/constants.py`) — are *intended* to sit at 5 (the ladder's
  unimpaired-mortal anchor) once their content rows are rescaled, but as of this
  change most environments still carry `innate_baseline = 1` for them: the
  rescale to 5 is a separate content-repo fixture commit, not something this
  arxii change performs. `world.vitals.seeds.ensure_foundational_capabilities()`
  seeds a *freshly created* row at 5, but for a pre-existing row only ever
  *raises* it when it's below 1 (to 1, never to 5) — a safety net against an
  unset baseline incapacitating everyone, not a normalizer onto the ladder.
- `sight` and `hearing` are **not** existing `FoundationalCapability` constants,
  and no code *logic* reads them — they are new `CapabilityType` rows being
  authored as content alongside this change (content-repo fixture, not this
  codebase), not existing foundational capacities on par with the three above.
  The only mention of either name anywhere in `src/` is the authoring guidance
  in `CapabilityType.innate_baseline`'s `help_text` (`world/conditions/models.py`,
  copied verbatim into migration `0025_alter_capabilitytype_innate_baseline_and_more`)
  — an instruction telling a content author what value to use when the rows are
  authored, not an assertion that the rows already exist.
- Granted/specialty capabilities (magic-adjacent, techniques-only — e.g.
  `perception`, `at_will_shifting`) default `innate_baseline` to 0, per the
  model field's own default (`world/conditions/models.py`).

**Blocking a capability is emergent arithmetic, never a boolean flag (D2).** A
`ConditionCapabilityEffect.value` sized to the tier it must beat drives the sum
toward (and `get_effective_capability_value`'s `max(0, …)` floor catches it at) 0:

| Tier | Magnitude | Beats |
|------|-----------|-------|
| Mundane | `-20` | Mortal and gifted (a greater supernatural walks out of it) |
| Potent | `-100` | Everything below mythic |
| Absolute | `-1000` (reserved) | Mythic-defeating effects only |

E.g. Grappled (mundane, `-20`) stops a mortal or gifted character but not a
greater-supernatural one; Frozen/Unconscious (potent, `-100`) stops everything
short of mythic. See `docs/adr/0164-capability-value-ladder-and-emergent-blocking.md`
for the full rationale and the rejected alternatives (a `blocks` boolean column;
rescaling to a 0-100 percentage).

The `world.checks` app's `CheckTypeCapabilityModifier` reads this ladder through a
different lens for check-roll contribution — see `docs/systems/checks.md`'s
"Authoring guardrail" and "Weight calibration" sections for the deviation-from-
baseline scoring (D3) and the weight-calibration rule (D4).

### Capability magnitude curve — geometric scaling with contextual power (#2708, ADR-0169) [BUILT & WIRED]

Two independent things changed on top of the ADR-0164 ladder above: (1) condition
capability effects now honour a severity flag that previously existed but was silently
ignored, and (2) both the technique-grant and thread-passive-grant magnitude formulas
became power-driven curves instead of flat/linear arithmetic. See
`docs/adr/0169-capability-magnitude-curves-geometrically-with-contextual-power.md` for
the full decision record, the rejected alternatives, and the stark-power design intent.

**Severity now honoured (fix, not a new feature).** `ConditionCapabilityEffect
.scales_with_severity` (inherited from the shared `ConditionOrStageEffect` abstract
base, migration `conditions/0007`) always existed as a column, but before #2708 every
reader of `ConditionCapabilityEffect` ignored it. Now all three value-aggregating
readers honour it identically — `effect.value * instance.effective_severity` when the
flag is set, else the pre-existing `effect.value * current_stage.severity_multiplier`
fallback for a staged condition (never both — `effective_severity` already folds the
stage multiplier in):

- `get_capability_status` (single-capability read, `condition_contributions` breakdown)
- `get_all_capability_values` (bulk read; the availability oracle's source-enumeration
  consumer)
- `conditions.views._aggregate_capability_effects` (the character-summary API endpoint)

**Technique capability grants curve geometrically.**
`TechniqueCapabilityGrant.calculate_value(*, effective_power=None, config=_UNSET)`
(`world/magic/models/techniques.py`) computes:

```
value = round(base_value * 2 ** (intensity_multiplier * power / power_per_doubling))
```

when a `CapabilityPowerConfig` singleton (`world/magic/models/power_config.py`, pk=1,
`power_per_doubling` default 10) exists, via
`world.magic.services.capability_curve.apply_capability_curve`. With **no config row**,
`calculate_value` falls back unchanged to the pre-#2708 additive shape (`base_value +
intensity_multiplier * power`) — the feature is turned on by staff tuning a config row
into existence, not by this code deploying. `intensity_multiplier` is **retired as an
additive term** and repurposed as the curve's exponent sensitivity; a grant authored at
the default `0` is inert under the curve (`2**0 == 1`) and stays byte-identical to its
pre-#2708 value. `apply_capability_curve` never returns less than `base_value` — power
is a pure empowerment axis; impairment stays the conditions layer's job (a negative
`ConditionCapabilityEffect`), never this curve's.

**Thread-passive tier-0 CAPABILITY_GRANT rows curve the same way**, via
`ThreadPullEffect.capability_grant_value` (new field, #2708; default `1` reproduces the
pre-#2708 flat grant) and `CharacterThreadHandler._passive_capability_grants_cache`
(`world/magic/handlers.py`), sensitivity = `thread_level_multiplier(thread.level)`. When
several owned threads grant the same capability, the fold is **MAX**, matching the
technique-grant fold (ADR-0034 individuation) — stacking never sums. **This is a
different mechanism from the paid-pull CAPABILITY_GRANT path** (`resolve_pull_effects`,
tiers 0-3, feeding `CombatPull`) — see `docs/architecture/resonance-threads.md`'s §5.4
step 3 note for the disambiguation; that path still treats CAPABILITY_GRANT as binary,
gated only by `min_thread_level`.

**Where the `power` figure comes from.** For technique grants,
`world.conditions.services._technique_capability_values` derives power as
`technique.intensity + context_free_power + contextual_thread_power(...)` —
`CharacterThreadHandler.context_free_power` (character-level + globally-scoped
condition/character modifiers, `technique=None`) plus
`CharacterThreadHandler.contextual_thread_power(ctx)` (batched tier-0 `INTENSITY_BUMP`
from threads `_anchor_ambiently_active` confirms are genuinely engaged). **Deliberately
excludes combat's `eff_intensity`** (spec decision 9) — a character's capability
standing must not flicker based on whether combat happens to be running right now.

**Ambient activation — the passive sibling of the pull predicate.**
`world.magic.services.resonance._anchor_ambiently_active` is the demonstrable-activation
gate for a thread's contextual power contribution — the passive counterpart to
`_anchor_in_action` (the paid-pull predicate). The two are deliberately **separate
functions**, not one function with an `ambient=` flag: `_anchor_in_action` lets a player
*assert* involvement for anchor kinds with no anchor in the action graph (GIFT,
RELATIONSHIP_*) because a pull is paid for; a free passive contribution costs nothing,
so assertion is not enough — every arm of `_anchor_ambiently_active` tests real state.
Nine arms: COVENANT_ROLE (delegates to `_anchor_in_action` — engagement is already
demonstrable), TECHNIQUE, GIFT (via `_gift_in_action`, narrowed per-call to
`ctx.involved_techniques`), TRAIT, SANCTUM (character's actual current room),
RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE (`_relationship_target_present`), FACET
(actually-worn items via `character.equipped_items.item_facets_for`), and MANTLE
(`_mantle_worn`). **ORGANIZATION deliberately returns `False`** — its ratified rule
("tied to organization missions or activities") needs a marker `PullActionContext` does
not carry; a needs-design follow-up off #2708, not a gap. The canonical failure this
predicate prevents: a pyromancer's fire-gift thread must never raise their ability to
climb a wall.

**`action_ctx` on the agency oracle (Task 8).** `get_effective_capability_value(sheet,
capability, *, action_ctx=None)` threads an optional real `PullActionContext` down to
`_technique_capability_values`. Every one of the ~13 pre-#2708 call sites is unaffected
(keyword-only, `None` default). When omitted, an **ambient default** is built from
`character_sheet.character.location` alone (no traits, no techniques) —
**`TRAIT`-kind threads stay dark under this default**: a bare capability read has no way
to know which trait, if any, the character is exercising right now, so a TRAIT thread's
tier-0 `INTENSITY_BUMP` only contributes when a supplied `action_ctx` names the trait in
`involved_traits`. This is a known, deliberate limitation, not a gap.

**A thread may move a capability's value only if it GRANTS that specific capability** —
the curved contribution is keyed to `ThreadPullEffect.capability_grant_id`, so a
fire-gift thread can never inflate an unrelated capability's number.

### Querying Modifiers

```python
from world.conditions.services import (
    get_check_modifier,
    opponent_condition_opposition,
    get_capability_status,
    get_capability_value,
    get_all_capability_values,
)

# Check modifier from all conditions
result = get_check_modifier(character, stealth_check_type)
result.total_modifier   # -20
result.breakdown        # [(frozen_instance, -10), (wounded_instance, -10)]

# Same query, but keyed directly on an ObjectDB with no CharacterSheet (#3384) --
# an ephemeral CombatOpponent. Returns the total_modifier int alone; no sign
# flip, so a penalty condition still lowers the number.
opponent_condition_opposition(opponent.objectdb, combat_attack_check_type)  # -20

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

**GM fiat apply/remove (#2118, #3431)** rides the REGISTRY action dispatch seam instead
of a ViewSet: `GMApplyConditionAction`/`GMRemoveConditionAction`
(`actions/definitions/gm_adjudication.py`, keys `gm_apply_condition`/
`gm_remove_condition`) apply/remove an authored `ConditionTemplate` by fiat, gated
`IsSceneGMPrerequisite` + JUNIOR GM trust. `GMListConditionsAction` (key
`gm_list_conditions`) is the read counterpart that feeds the web removal picker —
`CharacterConditionsViewSet.observed` above is self-only and filters to
`is_visible_to_others=True`, which would hide a fiat-applied hidden condition from the
GM who applied it, so this reads the target's full active-instance set instead. Web:
`GMAdjudicationPanel`'s Condition tab (apply + Remove mode). Telnet: `gm condition
<char> condition=<name> ...` / `gm condition remove <char> condition=<name>
reason=<text>` on `CmdGMDashboard`.

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
