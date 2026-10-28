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
    Allegiance,                    # ENEMY, ALLY_OF_CASTER, NEUTRAL, TURNED
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
| `ConditionCategory` | High-level groupings (damage-over-time, buff, debuff, etc.) | `name`, `description`, `display_order`, `is_negative`, `alters_behavior`, `self_shakeable` |
| `CapabilityType` | Actions that conditions can restrict/enhance | `name`, `description`, `innate_baseline` (int, default 0 — the ladder position every character starts from before modifiers/conditions; #2704, ADR-0164) |
| `CheckType` | Check types that receive bonuses/penalties | `name`, `description` |
| `DamageType` | Damage types for dealing/resisting | `name`, `description`, `resonance` (OneToOne to `mechanics.ModifierTarget`), `color_hex`, `icon` |

### Condition Templates (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionTemplate` | Condition definition (e.g., Burning, Frozen) | `name`, `category`, `description`, `player_description`, `observer_description`, duration settings, stacking settings, progression flag, removal settings (`cure_check_type`/`cure_difficulty`), apply-time resist-check (`resist_check_type`/`resist_difficulty`, #1738), combat settings (`affects_turn_order`, `draws_aggro`, and the #4584 reactive fields `forces_attack_on_source`, `source_guards_bearer`, `prevents_knockout`), reactive-effect settings (`reactive_anima_cost`, and the strike-back trio `retaliation_damage`, `retaliation_damage_type`, `retaliation_condition`, #4584), display settings, allegiance settings (`sets_allegiance`, `allegiance_break_check_type`, `settle_consequence_pool`, #4091, see below) |
| `ConditionStage` | Stage in a progressive condition | `condition`, `stage_order`, `name`, `rounds_to_next`, `resist_check_type`, `resist_difficulty`, `severity_multiplier`, `settle_consequence_pool` (#4091, overrides the template's pool at this stage), `intensity_per_round` (#4739, intensity this stage adds to the bearer's combat engagement each round; default 0. `clean()` refuses a positive value when a `SurgeDegreeBand` with an outcome below success level 1 carries the template - emotional conditions come only from a success or a choice; the Required content row `emotional-condition-on-failure-band` lists stored violations, and `world.combat.surge_bands.validate_surge_bands` refuses the band side in the admin; combat feeds it at each round opening through `world.combat.condition_surges.apply_condition_intensity_surges`, one `CONDITION_FED` surge per player character for the plain sum over active, unsuppressed, unresolved instances, ADR-4737 amendment) |

**Charm / Calm content (#1590).** The `Charm` `ConditionCategory` (`alters_behavior=True`) and
`Charmed` / `Calm` templates are seeded idempotently by `ensure_charm_content()` in
`world.conditions.charm_content`, aggregated via `ensure_conditions_content()`.
`alters_behavior` is the PC-consent gate (ADR-0024's PC consent gate does not apply to an NPC
target, since charm on an NPC alters a non-player's behavior). See ADR-0058 for the two-tier
NPC disposition model.

**Allegiance fields (#4091, ADR-4091, amending ADR-0059).** `ConditionTemplate.sets_allegiance`
(blank, or an `Allegiance` value other than `ENEMY`) names the effective allegiance a condition
puts its bearer on while it holds; it is read by this field, never by the condition's name, so
a renamed row changes nothing. A condition that sets it must also carry
`allegiance_break_check_type` (the check a PC rolls to break the hold by harming its bearer,
`clean()`-enforced) and may carry `settle_consequence_pool` (graded results when the hold is
settled or broken; a stage's own `settle_consequence_pool` replaces it at that stage). The
`Allegiance` enum derived from these fields (`world.npc_services.allegiance
.effective_allegiances`) feeds NPC targeting and the victory check; see the Combat system doc's
Allegiance entries and ADR-4091 for the full decision. **Authoring note:** an allegiance
condition's `observer_description`, same as any other condition's, surfaces on telnet `look`
(`CharacterState.get_display_allegiance`, #4091) alongside the hold's stage, source and
time-to-fade, so filling it in changes what a bystander sees of a charmed/turned/calmed NPC's
Status line, not only its own sheet. `CHARM_CONDITION_NAME`/
`CALM_CONDITION_NAME` remain as historical-snapshot literals (the data migration and the
sample-content seeder); no runtime code reads them. Parley's decisive calm picks the
`sets_allegiance = neutral` template with the lowest pk (REQUIRED dashboard row
`allegiance-calm-condition`). A hold whose condition has no `allegiance_break_check_type`
(missing content; `clean()` blocks it in admin) skips the break roll and logs one warning: the
hold persists rather than the round erroring, and the REQUIRED `allegiance-break-check` row
names the condition. Batched allegiance reads (`allegiance_instances_for`) ignore a hold past
its `expires_at` before the lapse sweep removes it.

**Settled round effects (#4120, ADR-4120) [BUILT & WIRED].** Rounds tick only inside combat, so a
`DurationType.ROUNDS` condition that outlived its fight used to freeze (and a ROUNDS charm never
carried an `expires_at` for the lapse sweep to see). Now `cleanup_completed_encounter` calls
`settle_round_effects(targets)` right after `expire_end_of_combat_conditions`: every other unresolved
`ROUNDS` instance with a round count on the encounter's participants and opponents (players and
persistent NPCs alike) gets `expires_at = now + rounds * SettleConfig.settled_seconds_per_round`,
`last_settled_tick_at = now` and `rounds_remaining = None` (idempotent: a converted row has no
round count), except the acute perils (Bleeding Out, Plummeting; the templates
`VitalsConsequenceConfig` designates, listed by `acute_peril_hand_off_condition_ids`, #4739), which keep their scene-round hand-off and stay ROUNDS rows.
That is a **settled round**. Then:

- **Tick and expiry (`settled_effects_tick`, cron `conditions.settled_effects`, one minute,
  `CronPhase.CLEANUP`).** Converted rows past `expires_at` come off through `remove_condition`
  (full teardown); allegiance rows are left to `lapsed_allegiance_sweep`. Each survivor with a
  full `settled_seconds_per_round` elapsed deals one tick of its template's non-long-term
  `ConditionDamageOverTime` (same `_round_dot_damage` as the combat tick, any `tick_timing`),
  one tick per run, later runs catch up. A target owned by an active round is skipped (the round
  tick advances it).
- **Edges.** The settled tick skips a target with no character sheet, so a persistent NPC without
  a sheet converts and expires but never takes settled damage (nothing lethal can happen to it).
  If combat restarts on a converted row, `rounds_remaining` is None so the duration countdown
  skips it and the wall clock keeps running; the combat DoT ticks it during the fight and the
  settled tick skips that target. A converted row stays active and keeps applying modifiers for
  up to one tick (a minute) past `expires_at`, until `settled_effects_tick` removes it. The hourly
  `batch_condition_expiration_cleanup` excludes ROUNDS templates, so only the settled tick (and the
  lapse sweep for allegiance rows) removes a converted row. Applying the condition again
  (stacking or refresh) returns the row to round-based accounting like a fresh application:
  `expires_at`, `last_settled_tick_at` and `lapse_warned_at` clear and `rounds_remaining` takes the
  incoming rounds.
- **Never lethal.** Settled damage goes only through `apply_clamped_chronic_damage`, never
  `process_damage_consequences`: health stays strictly above the knockout floor, so a settled
  effect cannot wound, down or kill, present or AFK. The clamp is unconditional; no `is_afk`
  helper exists because nothing consumes one. Acute perils (Bleeding Out, Plummeting) are not
  part of this lane and keep their scene-round hand-off.
- **Allegiance lapse (`lapsed_allegiance_sweep`).** A hold with a played charmer
  (`source_character` with an account) gets one "is fading" line when it enters the last
  `SettleConfig.lapse_warning_seconds` before `expires_at` (stamped in `lapse_warned_at`). At
  lapse the sweep auto-rolls the template's `allegiance_break_check_type` for the charmer
  (`perform_check` at `charm_strength_points` difficulty, a PLACEHOLDER) and ends the hold
  through `end_allegiance_with_pool`. A hold with no played charmer, or no check type (logged),
  is removed plainly. No encounter opens and nothing attacks (ADR-4091 Decision 21 stands;
  whether a lapsed NPC turns hostile is #4121). This supersedes Decisions 17/18 and the "no roll
  at lapse" clause of 21 only for a PC charmer.
- **`SettleConfig` (singleton pk=1, `get_settle_config()`, admin, REQUIRED dashboard row
  `settle-config`).** `settled_seconds_per_round` (default 300, paced in minutes because player
  turns take minutes) and `lapse_warning_seconds` (default 300, the warning lead window before
  expiry). Both are untuned defaults until staff author them.

### Condition Effects (Abstract base: `ConditionOrStageEffect`)

Effects use mutually exclusive FKs: `condition` (all stages) OR `stage` (stage-specific). Exactly one must be set.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConditionCapabilityEffect` | How a condition affects a capability | `capability`, `value` (additive integer; negative reduces, positive enhances), `scales_with_severity` (inherited from `ConditionOrStageEffect`; honoured by all three readers as of #2708 — see "Capability magnitude curve" below) |
| `ConditionCheckModifier` | How a condition modifies checks | `check_type` OR `check_category` (exactly one; category targets all checks in a category, including per-character magic checks — #2697), `modifier_value`, `scales_with_severity` |
| `ConditionResistanceModifier` | How a condition modifies damage resistance | `damage_type` (null = ALL), `modifier_value`, `scales_with_severity` (#4728: multiplies by the instance's `effective_severity`; unset rows are flat, with no stage-multiplier fallback, because stage rows are authored per stage. One rule, `scaled_resistance_value`, read by the damage seam through `CharacterConditionHandler.resistance_modifier` and by `get_resistance_modifier`) |
| `BreathHoldConfig` / `BreathHoldDurationAward` | The breath check, and held-breath rounds per check outcome tier (#4741) | singleton `check_type`, `target_difficulty`; award `outcome_tier` (one-to-one), `rounds`. Read by `breath_hold_rounds` |
| `ConditionDamageDealtModifier` | How a condition changes its bearer's OUTGOING damage of one type (#4742) | `damage_type` (required; a type with no row is unchanged), `modifier_percent` (-75 = a quarter), `scales_with_severity` (same rule as resistance, `scaled_damage_dealt_percent`). Read by `scaled_outgoing_damage` (PC technique profiles, combo riders, joust, NPC attacks) through `ConditionHandler.damage_dealt_percent` |
| `ConditionDamageOverTime` | Periodic damage from a condition | `damage_type`, `base_damage`, `scales_with_severity`, `scales_with_stacks`, `tick_timing` (after combat, a settled ROUNDS row ticks these through the non-lethal clamp, see "Settled round effects") |

#### DoT tick timing (`DamageTickTiming`) — #1762

`tick_timing` decides *when in a round* a `ConditionDamageOverTime` fires. **`END_OF_ROUND`
is the convention and the model/factory default** (poison, sunlight) — use it unless you
have a specific reason not to.

| Value | When it fires | Notes |
|-------|---------------|-------|
| `END_OF_ROUND` | After the round's actions resolve (`status == RESOLVING` in combat; the only tick scene rounds fire) | **Default.** Shieldable by Succor/Interpose; ticks in both combat and non-combat scene rounds. |
| `START_OF_ROUND` | Top of the round, during `DECLARING`, *before any action resolves* | Deliberate "unpreventable top-of-round damage" opt-in. **Intentionally un-shieldable** by Succor/Interpose (no ally has acted yet). **Inert in non-combat scene rounds** — the scene-round lifecycle only ever ticks `timing="end"` (`scenes/round_services.py`); no `timing="start"` path exists outside `combat/services/:begin_declaration_phase`. A hazard that needs to actually damage in scene rounds would have to build that scene-round START tick first. |
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
| `ConditionInstance` | Active condition on a target | `target` (FK to ObjectDB), `condition`, `current_stage`, `stacks`, `severity`, `applied_at`, `expires_at`, `rounds_remaining`, `stage_rounds_remaining`, `source_character` (FK to ObjectDB, a keeper per #4217: the body that applied it, and an ephemeral combat mook has no sheet yet is a real, death-permitting source), `source_technique`, `source_vow` (#2643: nullable FK → `covenants.CovenantRole`, `SET_NULL`: the applier's engaged-vow anchor at apply time; drives vow-keyed diminishing returns on the bounded team-damage-percent lane, see `docs/systems/magic.md`), `source_description` (#3554: rendered to the bearer in `ConditionDetailModal` and to every viewer of a visible condition in the `ConditionBadge` tooltip; `gm_apply_condition` broadcasts a GM's note as a Narrator OUTCOME line, target-only when the template is not `is_visible_to_others`; the WebSocket payload goes to the room, or to the target alone when hidden or when the GM has no location, and the text send is the telnet companion; a sheetless target is named by its key and a hidden condition on one records nothing), `is_suppressed`, `suppressed_until`, `resolved_at`, `abandoned_since_round` (#1479: round at which a downed bearer's acute peril was held/abandoned; cleared when a hostile party drives again), `last_settled_tick_at` (#4120: set when a ROUNDS row is settled, advanced by `settled_effects_tick`), `lapse_warned_at` (#4120: once-only fading warning stamp), `modifier_level` / `modifier_size` (#4594: nullable; stamped by a cast from a sized `TechniqueAppliedCondition` through `BulkConditionApplication`; with both set, the instance's check modifiers read the value table, see "Sized check modifiers" below), `modifier_vow_level` / `modifier_vow_tenths` (#4747: nullable; the caster's vow thread shown level and her matching specialty's share in tenths, stamped at cast when her engaged vow specializes in the technique's function; each sized modifier adds one size step at that level times tenths / 10, untapered; null or 0 tenths means no step) |
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
    settle_round_effects,          # Convert ROUNDS rows to real-time expires_at after combat (#4120)
    settled_effects_tick,          # Cron: clamped non-lethal DoT + expiry of settled rows (#4120)
    get_settle_config,             # SettleConfig singleton (#4120)

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
    get_turn_order_modifier,       # Int modifier to initiative (one sheet)
    get_aggro_priority,            # Int priority for targeting (one sheet)
    turn_order_modifier_by_target, # {ObjectDB pk: total} for many targets in one query (#4572)
    aggro_priority_by_target,      # {ObjectDB pk: total} for many targets in one query (#4572)
    get_condition_modifier_vow_contributions, # Per-instance (source_vow_id, name, value) rows for a ModifierTarget (#2643)
    priced_percent_severity,       # Apply-time percent severity priced vs the landing target's level (#2643)
    scaled_condition_effect_value, # One ConditionModifierEffect's contribution on one active instance (#4090)
    active_condition_instances_by_sheet, # Pure-read get_active_conditions sibling, many sheets at once (#4090)
    condition_modifier_totals_by_sheet, # Batched get_condition_modifier_total across many sheets (#4090)

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

### Held breath (#4741, ADR-4741-A) [BUILT & WIRED]

A condition that lasts only while its bearer holds her breath: a smoke form, being underwater.
Three fields on `ConditionTemplate` (admin fieldset "Held Breath"):

- **`holds_breath`** - on application (single and bulk, new or refreshed) the bearer rolls
  `BreathHoldConfig.check_type` at `target_difficulty` (`breath_hold_rounds`), and the outcome
  tier's `BreathHoldDurationAward.rounds` replaces the authored or technique-supplied rounds
  (`_rounds_for_application`). No configured check, no outcome, or no row for that tier falls
  back to the condition's own rounds. `clean()` requires a Rounds duration. The countdown is the
  ordinary ROUNDS one, in combat and settled out of combat.
- **`breath_runs_out_condition`** - applied when the hold expires on its own, in combat
  (`_process_duration_and_progression`) or settled (`settled_effects_tick`), through
  `_breath_ran_out`. Never applied when she breathes. Underwater -> Drowning.
- **`breaks_held_breath`** - when this condition lands (its resist roll failed or absent), the
  bearer breathes: `take_breath` ends every held-breath condition on her. A Coughing condition
  with a resist check is a coughing fit she can roll to avoid.

`take_breath(target)` is the one way a hold ends early; `TakeBreathAction` (key `take_breath`,
always succeeds, no roll), telnet `breathe`, and the web Status panel's "Take a breath" button
(the vitals payload's `held_breath` list) all reach it.

**Cough after casting is authored, not coded.** A permanent condition on her (her mage scar)
carries a reactive trigger on `TECHNIQUE_CAST` filtered `{"path": "caster", "op": "==",
"value": "self"}`, whose flow calls `flow_apply_condition` with `target="@payload.caster"` and
`condition_name="Coughing"`. Any other event works the same way.

### Incorporeal and untyped damage (#4742, ADR-4742-A) [BUILT & WIRED]

- **Untyped damage is Physical.** `resolved_damage_type(damage_type)` returns the given type, or
  `VitalsConsequenceConfig.physical_damage_type` when it is empty (set by migration 0311 and the
  survivability seeder; code never looks Physical up by name). Every damage seam calls it at
  entry: `apply_damage_to_participant`, `apply_damage_to_opponent`, `apply_resolved_damage`,
  `process_damage_consequences`, `resolve_damage_type_resistance` and
  `CombatTechniqueResolver._profile_damage`. So Physical and all-types resistance rows, cover,
  property bonuses, damage interactions and Physical's consequence pools all meet weapon hits.
  With no Physical row configured (an empty database) untyped damage stays untyped.
- **Incorporeal is resistance, never untargetability.** `ConditionCategory.grants_intangibility`
  (`is_intangible`) is read only by held ground: an incorporeal PC blocks nobody. NPC picks and
  area casts include her. Her protection is a severity-scaled Physical
  `ConditionResistanceModifier` on the form's condition, so a hit below it does nothing and an
  overwhelming hit lands the difference.
- **Riders need a hit that survives resistance.** In `apply_damage_to_participant` the on-hit
  pool (knockback) fires only when damage remains after thread damage reduction and resistance;
  armor soak and cover still allow it. Sent flying already needs `damage_dealt > 0`. Grapples
  and grips are resisted by degrees through the condition's own resist roll
  (`_check_application_resist`) plus the form's check modifiers on that roll.
- **Her own strikes.** `ConditionDamageDealtModifier` rows change the bearer's outgoing damage
  of one type by a percent, through one seam, `scaled_outgoing_damage(attacker, amount, type)`:
  PC technique profiles (end of `_profile_damage`), PC combo riders and joust strikes, and NPC
  attacks (`npc_attack`, `npc_action`) all call it. Battle failure damage and falls are not
  strikes and do not. A smoke form with
  Physical -75 and no Fire row hits a quarter as hard with plain steel and at full strength with
  a Fire profile.

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

### Condition effects combat reads (#4572) [BUILT & WIRED]

Every condition effect a technique can apply is read by combat for both sides of a fight,
by its field and never by the condition's name:

| Field(s) on `ConditionTemplate` | Read by | Effect |
|---|---|---|
| `draws_aggro`, `aggro_priority` | `select_npc_actions` (`_apply_aggro_conditions`), through `aggro_priority_by_target` | A PC carrying the condition has its summed priority added to its threat with every opponent when an NPC picks a target, and joins the `SPECIFIC_ROLE` preferred set beside shield-role PCs. Read at selection time only: no `ThreatRecord` is written, and an active `EngagementLock` still narrows the pool afterwards. `RANDOM`, `LOWEST_HEALTH` and `ALL` stay as authored. |
| `affects_turn_order`, `turn_order_modifier` | `effective_speed_ranks` (`world/combat/services/combos/resolution_order.py`), through `turn_order_modifier_by_target` | Round order sorts on the combatant's base speed rank (covenant role `speed_rank`, `NO_ROLE_SPEED_RANK`, or `NPC_SPEED_RANK`) minus its summed modifier, so a positive modifier acts earlier. PCs and NPC opponents both shift. `get_resolution_order` and the encounter payload's `resolution_order` (the initiative chips) sort on the same ranks. |
| `ConditionDamageOverTime` | `tick_round_for_targets` -> `_apply_round_tick_damage` (`world/vitals/services.py`) | An NPC opponent has no sheet or vitals, so its tick damage goes through `apply_damage_to_opponent` with damage-type resistance netted once, no armor soak and no `DAMAGE_PRE_APPLY` (the same as PC DoT); defeat follows as from a hit. |
| `absorb_remaining`, a reactive trigger calling `reflect_damage` | `absorb_pool`, `reflect_damage` (`world/magic/services/effect_handlers.py`) | The barrier handlers designate their condition by field: `absorb_pool` takes the bearer's oldest active instance holding a buffer, `reflect_damage` takes an instance whose template carries a reactive trigger calling the handler. A barrier staff name anything else works. The "Aegis Field" / "Mirror Ward" name constants remain for seed content only. |
| `forces_attack_on_source` | `select_npc_actions` (`_provoking_participant_ids`, `_narrow_to_locked_or_provoker`), through `provoking_source_by_target` (#4584) | **Provoke.** An NPC opponent carrying the condition attacks only the condition's `source_character` (the newest active instance with a source wins). An active `EngagementLock` that narrowed the pool wins over it. A source who is down, out of the fight or not a PC falls back to the opponent's normal target choice, never a skipped turn. Charmed, turned and summoned opponents ignore it (they do not target the PC side) and so does a PC bearer (PCs choose their own targets). |
| `source_guards_bearer` | `_ensure_interpose_challenges` and `_try_interpose` (`world/combat/services/damage/`), through `guardians_by_target` (#4584, ADR-4584-A) | **Standing guard.** The condition's source tries the mundane interpose on every hit on the bearer, through the shared tail `_attempt_guardian_interpose`. It counts as one of her reactions this round (no cap; a harder roll each time, #4676) and against `ABSORPTION_CAP_PER_MOMENT`, and pays interpose fatigue at very low effort, but she still takes her own turn. A guardian who declared any Interpose that round acts only through her declaration. A guardian who cannot act (`can_act`: knocked unconscious, though still ACTIVE) does not step in. A self-cast guard never interposes. PC wards in combat only. |
| `prevents_knockout` | `_process_knockout_tier` (`world/vitals/services.py`), through `knockout_preventing_instance` (#4584) | **Grace.** The knockout roll is skipped (looked up only after the difficulty and check-type guards, so it is used only when a roll would happen). An `UNTIL_USED` grace stops one knockout and ends; a `ROUNDS` grace stops every knockout while it lasts. `CHARACTER_INCAPACITATED` still fires on entering the band. PCs only: NPC opponents have no knockout roll. |
| `retaliation_damage`, `retaliation_damage_type`, `retaliation_condition` | `_answer_with_strike_backs` in `_emit_post_damage_events` (`world/combat/services/damage/damage.py`) calls `strike_back` for each instance `retaliating_instances` finds (#4584) | **Strike-back.** After a hit lands on a PC bearer, each ward answers the NPC that dealt it: `retaliation_damage` (typed by `retaliation_damage_type`) through `apply_damage_to_opponent`, and `retaliation_condition` laid with the ward's source as its source (not on an NPC the damage defeated). It is a hard-coded read at the damage seam, not a flow, trigger or seeded row. It answers hits on PC bearers only and strikes `CombatOpponent` attackers only (never a PC, ADR-0023). It pays `reactive_anima_cost` (a fizzle speaks, a success is not narrated: known gap), counts as the caster's threat, as duel interference and as probing, as rampart retaliation does. |
| `default_duration_type = UNTIL_USED` | `spend_condition_use`, `spend_contributing_conditions`, `spend_conditions_by_id` (`world/conditions/services.py`) (#4584) | **Once-only.** Spending is a full removal through `_teardown_removed_condition_instance` plus a synchronous trigger-cache refresh, so a ward spent on the first hit of a round is gone for the second. See "Until used" below. |

The two batched helpers share `_active_template_sum_by_target`: one query for all targets,
keyed by ObjectDB pk, suppressed and expired rows skipped, zero totals omitted. The
single-sheet `get_turn_order_modifier` / `get_aggro_priority` are thin wrappers over them.
A new condition field or handler that combat reads must be read for both sides and by field;
the `condition-effect-reach-reviewer` agent (`tools/agents/`) checks a diff for that. The
journeys in `src/integration_tests/test_conditions_that_reach_the_fight_journeys.py` operate
all of it through a combat round. The #4584 effects have their own journey set in
`src/integration_tests/test_holding_the_line_journeys.py` (provoke, thorn ward, standing
guard, grace, once-only blessing).

**Timing: round N to N+1 (#4584).** `forces_attack_on_source` is read when an opponent
chooses its target, so a provoke applied by an action in round N first steers round N+1,
and a 1-round provoke ends before it is ever read. `source_guards_bearer` is bound before
the round resolves (`_ensure_interpose_challenges`), so a guard holds from the round after
it lands. Give either at least 2 rounds.

**Until used (#4584).** `UNTIL_USED` conditions end when used, through `spend_condition_use`
(which returns False and touches nothing for an already-gone instance or a non-`UNTIL_USED`
template, so a lasting condition is never spent by use):

- **A blessing's check term** is spent after a real roll it fed: every roll site calls
  `spend_contributing_conditions(breakdown)` after the roll (`perform_check_with_modifiers`
  does it itself), and a paused resolution carries `contributing_condition_ids` on its
  `PendingActionResolution` and spends them when its resume rolls. A zero term is not a
  use. `collect_check_modifiers` and previews never spend (the consider check and the
  standoff grade view call it), and an NPC's `opponent_condition_opposition` term is not
  spent by a PC's roll. `condition_contributions` records each term's
  `condition_instance_id` for this. A mechanical guard test
  (`world/checks/tests/test_spend_contributing_conditions.py`) checks that every function
  that collects condition modifiers also spends.
- **A reactive ward** (`absorb_pool`, `reflect_damage`, `blink_dodge`, `strike_back`) is
  spent after a successful fire; a fizzle (cannot pay) is not a use. An `UNTIL_USED` absorb
  barrier soaks one blow and ends through the full teardown, whatever buffer is left.
- **A knockout grace** (`prevents_knockout`) stops one knockout, PCs only.
- **A marker** (the `*_on_condition` adapters: Summoning, Phase Jump, Barricade, Force
  Grip, the Ramparts, and a zone-hazard marker through `create_zone_hazard_on_condition`) is
  spent when its `CONDITION_APPLIED` flow has run, on normal exit of
  the effect only (early returns count; an error does not spend, the apply rolls back).

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

**Sized check modifiers (#4594, ADR-4594-A).** `_check_modifier_for_target` (behind
`get_check_modifier`, `condition_contributions` and `opponent_condition_opposition`) values a
`ConditionCheckModifier` row on an instance carrying both `modifier_level` and `modifier_size`
from the check lane's value table (`world.checks.modifier_values.load_value_table`, loaded once
per call and only when some active instance is sized): the table's magnitude at that level and
size, with the authored row's sign, and no severity or stage scaling. An unsized instance, a zero
authored value, or a level below every value row keeps the flat authored path. Nothing about the
bearer is read. `condition_contributions` puts the level and size on each CONDITION
`ModifierContribution`. `bulk_apply_conditions` stamps them through `_stamp_modifier_sizing`
(after apply, before `CONDITION_APPLIED`); a re-application keeps the higher level and takes the
new size. `opponent_condition_opposition` applies the check lane's CONDITION `ModifierTaper` row
to the opponent's own pile, so a debuff pile on an NPC tapers like a buff pile on a PC.
A vow-stepped instance (`modifier_vow_level`, `modifier_vow_tenths`, #4747, ADR-4747-A) adds
(value(L, size + 1) minus value(L, size)) x tenths / 10, rounded half up, to each sized
modifier, priced by the shared `_priced_sized_modifier` and carried
as the contribution's untapered `vow_part`; `CheckModifierResult.breakdown` rows are
`(instance, value, vow_part)` so all three read paths (check, opponent, stat lane) carry it.

**Batched reads for many sheets at once (#4090).** `active_condition_instances_by_sheet
(sheet_ids)` is the pure-read sibling of `get_active_conditions`: the same canonical active
predicate plus skipping an in-game-time instance whose `expires_at` has passed, but across many
sheets in one query and with no teardown of an expired instance (a reader must not write).
`condition_modifier_totals_by_sheet(sheet_ids, modifier_target)` is the batched sibling of
`get_condition_modifier_total`: two queries regardless of how many sheets (the active instances,
then the matching template-/stage-level `ConditionModifierEffect` rows), returning
`dict[int, int]` keyed on each sheet's pk (CharacterSheet shares ObjectDB's pk, so a
`ConditionInstance.target_id` is already the sheet pk). Both share the one scaling rule,
`scaled_condition_effect_value(effect, instance)`: `scales_with_severity` multiplies by the
instance's `effective_severity`, else a staged instance scales by its current stage's
`severity_multiplier`. `world.species.language_services.comprehension_values` is the first
caller: a listener's language comprehension is trained fluency plus
`condition_modifier_totals_by_sheet`'s bonus toward that language's `ModifierTarget`.

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

### When the treated condition goes away (#4475)

A treat request points at the `ConditionInstance` it offered to treat, and play deletes
instances (healing to nothing, expiry, decay, waking, a successful removal check, a
bulk clear, combat upkeep). The FK is `SET_NULL`, and the request snapshots
`target_condition_template` and `target_condition_name` the first time it is saved
with an instance, so the scene's treatment history still says what was treated.
`ConditionInstance.delete()` calls
`world.scenes.action_services.settle_treatment_requests_for_condition` first, so every
removal path is covered: a request still `PENDING` or `ACCEPTED` becomes `EXPIRED`
(the wound is gone, nothing left to treat), a `RESOLVED` one keeps its status, and any
request without a snapshot (written by the previous release during a deploy) gets one.
Queryset `.delete()` and parent cascades skip the override; they still pass (SET_NULL)
but leave an open request unsettled. `SceneActionRequest.treatment` stays PROTECT
(staff-authored template); `thread_used` (threads are retired with `retired_at`, never
deleted) and `target_pending_alteration` (status-driven, never deleted by play) stay
PROTECT.

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

## Self-shakeable categories (#4732)

`ConditionCategory.self_shakeable` (default False) marks conditions the character may shake
off herself with `breakfree` (and an ally may help with `rally`) without them altering her
behaviour. Resonance Conflict is the first. It is deliberately not `alters_behavior`, which
drives `in_control`, consent and form revert. `breakable_condition_filter()` in
`world/conditions/services.py` is `alters_behavior OR self_shakeable` and is used by
`BreakFreeAction`, `RallyAction` and `process_break_free_tick`; `RevealConditionAction` stays on
`alters_behavior`. Conditions still need a `break_free_mode` other than NONE.

---

## Designated conditions (#4739) [BUILT & WIRED]

Conditions the code has to find are designated on a config singleton by a nullable
`ForeignKey(PROTECT, related_name="+")`, never matched by name, so renaming the
template in admin changes nothing. Each has a lookup and a Required content row that
lists it while unset. No migration sets any of them; staff do. An unset designation
means the mechanic does nothing (no crash, no fallback to a name). Guard on `None` before
filtering a nullable column by a lookup (`filter(x_id=None)` is `IS NULL` and matches every
unset row); an `__in` list drops `None` safely. Seeds and test factories point an unset
designation at the row they just made and never overwrite one staff set; the names they make
rows under are `*_SEED_TEMPLATE_NAME` constants that game code never imports.

| Condition | Field | Lookup |
|---|---|---|
| Soulfray | `SoulfrayConfig.condition` (#4122) | `world.magic.services.soulfray.soulfray_condition_id()` |
| Audere | `AudereThreshold.audere_condition` | `world.magic.audere.audere_condition_id()` (eligibility, offer, `end_audere`, `_character_is_in_audere`, `active_ceremony`, encounter cleanup, participant `audere_state`) |
| Audere Majora | `AudereThreshold.audere_majora_condition` | `world.magic.audere.audere_majora_condition_id()` (crossing, `end_audere_majora`, mid-crossing check, check-level bonus) |
| Berserk | `FuryConfig.berserk_condition` | `world.magic.services.fury.get_berserk_template()` / `berserk_condition_id()` (fury, moon control, `is_berserk`, fury serializer, combat status line) |
| Bleeding Out | `VitalsConsequenceConfig.bleed_out_condition` | `world.vitals.peril_designations.bleed_out_condition_id()` (dying status, death tier, `advance_bleed_out`, `acute_peril_condition_ids()`, ally-peril surge) |
| Plummeting | `VitalsConsequenceConfig.plummeting_condition` | `world.vitals.peril_designations.plummeting_condition_id()` / `plummeting_template()` (plummet begin/advance/end, scene-round danger) |
| Surrounded | `VitalsConsequenceConfig.surrounded_condition` | `world.vitals.peril_designations.surrounded_condition_id()` / `surrounded_template()` (battle entry, RESCUE, escalation, `advance_surrounded`) |

`acute_peril_hand_off_condition_ids()` (`conditions/services.py`, Bleeding Out + Plummeting)
and `acute_peril_condition_ids()` (`vitals/peril_resolution.py`, Bleeding Out) replace the
old `*_names()` lists with the same membership. `_advance_staged_peril_condition(sheet,
condition_id, terminal_resolver)` takes the designated id. Seed helpers:
`designate_unset_peril_conditions(...)` (vitals), `ensure_audere_designations` /
`designate_audere_conditions` (magic test factories), and the Berserk seed / factory, which
make `FuryConfig` pk=1 when absent.
| Inspired (Rally success) | `SocialManeuverConfig.rally_success_condition` | `world.combat.services.encounter.config.get_social_maneuver_config()` |

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
