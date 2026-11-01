# Mechanics System

Game engine for modifier collection, stacking, amplification, immunity, and source tracking from distinctions (and future sources like equipment and spells).

**Source:** `src/world/mechanics/`
**API Base:** `/api/mechanics/`

---

## Enums (constants.py)

```python
from world.mechanics.constants import (
    ResonanceAffinity,          # CELESTIAL, ABYSSAL, PRIMAL
    STAT_CATEGORY_NAME,         # "stat"
    GOAL_CATEGORY_NAME,         # "goal"
    GOAL_PERCENT_CATEGORY_NAME, # "goal_percent"
    GOAL_POINTS_CATEGORY_NAME,  # "goal_points"
    RESONANCE_CATEGORY_NAME,    # "resonance"
    INCOME_CATEGORY_NAME,       # "income" (#4394, the five levers; see "Levers" below)
    REPUTATION_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_CATEGORY_NAME,
    COMFORT_CATEGORY_NAME, FATIGUE_COST_CATEGORY_NAME,
)
```

## Types (types.py)

```python
from world.mechanics.types import (
    ModifierSourceDetail,  # Dataclass: source_name, base_value, amplification, final_value, is_amplifier, blocked_by_immunity
    ModifierBreakdown,     # Dataclass: modifier_target_name, sources (list[ModifierSourceDetail]), total, has_immunity, negatives_blocked
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ModifierCategory` | Broad groupings for modifier targets (stat, magic, affinity, resonance, goal, etc.) | `name` (unique), `description`, `display_order` |
| `ModifierTarget` | Unified registry of all things that can be modified; replaces separate Affinity, Resonance, GoalDomain models | `name`, `category` (FK ModifierCategory), `description`, `display_order`, `is_active`, `target_trait` (FK Trait, nullable), `target_being` (FK WorshippedBeing, nullable, #4333 favor categories), `affiliated_affinity` (self FK), `opposite` (self OneToOne), `resonance_affinity` (ResonanceAffinity) |

### Per-Character Data

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ManeuverEffect` | One named part of a combat maneuver and its base value (#4783); eight fixed rows, admin edit-only | `key` (unique), `base_value`, `notes` |
| `ModifierSource` | Encapsulates where a modifier originated; links effect template to character instance | `distinction_effect` (FK DistinctionEffect), `character_distinction` (FK CharacterDistinction, CASCADE), `residence_comfort` (bool), `form_combat_profile` (FK forms.FormCombatProfile, SET_NULL) |
| `CharacterModifier` | Materialized modifier value on a character for fast lookup (SharedMemoryModel) | `character` (FK CharacterSheet), `value` (int, can be negative), `source` (FK ModifierSource, CASCADE), `expires_at` (nullable datetime), `created_at` |

### Key Model Properties

```python
# ModifierSource
source.source_type     # "distinction", "residence_comfort", "form", or "unknown"
source.modifier_target   # ModifierTarget from source.distinction_effect.target
source.source_display  # "Distinction: Strong", "Residence comfort", "Form: ...", or "Unknown"

# CharacterModifier
modifier.modifier_target  # Derived from source.modifier_target (not stored directly)
```

### Stacking Rules

- All modifiers for a given `modifier_target` stack (values are summed).
- Modifiers with `value == 0` are hidden from display.
- `modifier_target` is derived from `source.distinction_effect.target` -- never stored directly on `CharacterModifier`.

### Situation System
Reusable authored scenarios (`SituationTemplate`) composed of Challenges and
Traps, instantiated at a location by a staff-triggered Action.

- **Models:** `SituationTemplate`, `SituationChallengeLink` (#1895 — carries
  `target_object_name`, the authored display name for the ChallengeInstance's
  auto-created target object), `SituationTrapLink` (#1625 — authored trap
  blueprint), `SituationInstance`, `ChallengeInstance`
- **Key Functions:**
  - `instantiate_situation(template, location) -> SituationInstance` (#1625,
    extended #1895, `world/mechanics/situation_services.py`) — mints a
    `SituationInstance`, materializes `SituationTrapLink` rows into
    `room_features.Trap` rows, and materializes `SituationChallengeLink` rows
    into `ChallengeInstance`s (auto-creating a bare `ObjectDB` per link named
    from `target_object_name`, then delegating to the existing
    `instantiate_challenge()`). All wrapped in one `transaction.atomic()` block.
- **Trigger:** `SetSituationAction` (`actions/definitions/situations.py`) +
  `CmdSetSituation` (`commands/setsituation.py`, telnet key `setsituation`) —
  gated on `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` (staff bypass
  preserved, #2117), in-scene verb mirroring `SetTheStageAction`/`CmdSetStage`
  (STARTING tier). No duplicate-instantiation guard (intentional — see
  ADR-0091).
- **Admin:** `SituationTemplateAdmin` has `SituationChallengeLinkInline` and
  `SituationTrapLinkInline` for authoring.
- **Integrates with:** room_features (`Trap` model, `check_room_traps_on_entry`),
  actions (`SetSituationAction`), evennia (`ObjectDB` auto-creation for
  challenge targets)

---

## Key Methods

### Service Functions (`services.py`)

```python
from world.mechanics.services import (
    get_modifier_total,
    get_modifier_breakdown,
    create_distinction_modifiers,
    delete_distinction_modifiers,
    update_distinction_rank,
)

# Get total for a specific ModifierTarget (requires CharacterSheet + ModifierTarget instances)
total = get_modifier_total(character, modifier_target)

# Get detailed breakdown with amplification/immunity calculations
breakdown = get_modifier_breakdown(character, modifier_target)
# Returns ModifierBreakdown with sources, total, has_immunity, negatives_blocked
```

### Aspect targets (#4827)

```python
from world.mechanics.services import ensure_aspect_target

# The aspect-category target an Aspect's bonuses land on (target_aspect = the Aspect row),
# created if missing; None when another category already owns the name (resolve by hand).
target = ensure_aspect_target(aspect)   # AspectAdmin.save_model and ensure_aspect_targets() call this
```

`ModifierTarget.target_aspect` is a nullable one-to-one onto `classes.Aspect`, the sibling of
`target_check_type`; the check seam reads it through `aspect.modifier_target`
(`docs/systems/checks.md`, "The aspect lever").

### Skill targets (#4820)

```python
from world.mechanics.services import ensure_skill_target, skill_modifiers_for_sheet

# The stat-category target a skill's bonuses land on (target_trait = the skill's trait),
# created if missing; None when another category already owns the name (retarget by hand).
target = ensure_skill_target(skill.trait)   # SkillAdmin.save_model and the paste call this

# skill.pk -> the modifier a roll on that skill gets, for the sheet: card and condition
# rows in three queries, worn crafted pieces and the equipment walk from cached handlers.
modifiers = skill_modifiers_for_sheet(sheet, skills)
```

### Amplification and Immunity

```python
# get_modifier_breakdown applies these rules:
# 1. Amplifying sources: add their amplifies_sources_by bonus to all OTHER sources
# 2. Immunity: if any source grants_immunity_to_negative, all negative final values are blocked
# 3. Orphaned rows (source.distinction_effect is null — SET_NULL after the effect template
#    is deleted, or a future non-distinction source type) are skipped: they contribute
#    nothing and are not listed in sources, since their amplifier/immunity/label semantics
#    are gone.

breakdown = get_modifier_breakdown(character, modifier_target)
breakdown.total            # Final stacked value after amplification/immunity
breakdown.has_immunity     # True if any source grants negative immunity
breakdown.negatives_blocked  # Count of negative modifiers blocked by immunity
for source in breakdown.sources:
    source.base_value       # Raw modifier value
    source.amplification    # Bonus from other amplifying sources
    source.final_value      # base_value + amplification
    source.is_amplifier     # Whether this source amplifies others
    source.blocked_by_immunity  # Whether this source was blocked
```

### Distinction Lifecycle

```python
from world.mechanics.services import create_distinction_modifiers, delete_distinction_modifiers, update_distinction_rank

# When a CharacterDistinction is granted: create ModifierSource + CharacterModifier per
# non-resonance effect, then reconcile any resonance grants (see below).
modifiers = create_distinction_modifiers(character_distinction)

# When a CharacterDistinction is removed: cascade-delete all modifiers
count = delete_distinction_modifiers(character_distinction)

# When rank changes: recalculate modifier values (and re-reconcile resonance grants)
update_distinction_rank(character_distinction)
```

**Resonance-targeting distinction effects are handled separately (#1834).** A
`DistinctionEffect` whose `target.category.name == "resonance"` is skipped entirely by
the loop above — it never gets a `ModifierSource`/`CharacterModifier` row. Instead,
`create_distinction_modifiers` and `update_distinction_rank` both call
`reconcile_distinction_resonance_grants(character_distinction)`
(`world.magic.services.distinction_resonance`), which reads the `DistinctionResonanceGrant`
authoring sidecar on the distinction and grants real, rank-scaled `CharacterResonance`
currency (idempotent — a second call at the same rank grants nothing further). The `resonance`
`ModifierCategory` itself is not deprecated: non-distinction sources (facet/mantle/motif
passive bonuses, walked via `equipment_walk_total`) still read/write resonance-category
`CharacterModifier` rows normally. The aura percentage calculation
(`magic.services.recompute_aura()`) reads `CharacterResonance.lifetime_earned` grouped by
affinity and was never coupled to either path. The legacy `CharacterResonanceTotal`
denormalized aggregate was removed in the Spec A pivot — there is no sync step to keep in
lockstep.

**POWER-category distinction effects (potency, #1834 Task 7) are unaffected by the skip
above** — a `DistinctionEffect` on a POWER-category `ModifierTarget` (optionally gated by
`target_resonance`) still writes a normal `CharacterModifier` row through the loop. Two
consumers read it: a technique cast (`_derive_power`'s FLAT stage, already wired) and a
standalone thread pull, via `power_flat_bonus_for_resonance(sheet, resonance_id)` — mirrors
cast scope semantics exactly: sums matching POWER-category modifiers whose
`target_resonance` is either null (unscoped — applies to every resonance) or equals the
pull's resonance (excluding the unscoped `power_multiplier` target) via `get_modifier_total`.
See `world/magic/CLAUDE.md` "Distinction Potency (POWER axis)" for the pull-side wiring
(`world.magic.services.resonance._fold_distinction_pull_bonus`). The pull path is **not**
full parity with a cast: `_derive_power`'s FLAT stage also sums condition-sourced POWER
contributions (`get_condition_modifier_breakdown`), which the pull fold does not include —
that gap is real and remains.

**Favor categories (#4333).** `favor_invocation` (difficulty points eased on an invocation
check) and `favor_earning` (percentage points added to the earning rate) are scoped to a
worshipped being by `ModifierTarget.target_being` (a plain FK: one target per (category,
being), unique when set; null is the single "any being" target per category, held by
`ModifierTarget.clean()`, which also refuses a being outside the two favor categories). `world.worship.favor_services.ensure_being_modifier_targets` creates
them and `favor_modifier_total(sheet, being, category)` is the one reader (eager rows,
crafted items, the equipment walk, conditions). Both categories are in
`EQUIPMENT_RELEVANT_CATEGORIES`; for them `equipment_walk_total` adds the covenant role
bonus once (`covenant_role_base_total`) instead of once per equipped item. See
`docs/systems/worship.md`.

---

## Modifier Target Naming Conventions

| Category | Naming Pattern | Examples |
|----------|---------------|----------|
| `stat` | Lowercase stat name | `strength`, `dexterity`, `charm` |
| `action_points` | `ap_` prefix + descriptor | `ap_daily_regen`, `ap_weekly_regen`, `ap_maximum` |
| `development` | Category + `_skill_development_rate` | `physical_skill_development_rate`, `all_skill_development_rate` |
| `height_band` | Descriptive name | `max_height_band_bonus` |
| `resonance` | Resonance name | Uses `affiliated_affinity`, `opposite`, `resonance_affinity` fields |
| `goal` / `goal_percent` / `goal_points` | Goal domain names | Standing, Wealth, Knowledge, etc. |
| `favor_invocation` / `favor_earning` | `<being> favor invocation` / `<being> favor earning`; one `Any being ...` target each | `target_being` names the being; null = any being (#4333) |
| `income` / `reputation_gain` / `relationship_gain` / `comfort` / `fatigue_cost` | The category's own name; `reputation_gain` also `reputation_gain_society` and `reputation_gain_organization` | The five levers (#4394); see "Levers" |
| `disguise_sight` | `mundane`, `magical` (one per `DisguiseKind` value) | Sight through a mask (#4396); see "Levers" |

## Levers (#4394)

The five IC levers ApostateCD ruled a distinction may pull (2026-09-07; XP and Kudos never):
one `ModifierCategory` each, read at exactly one seam through `get_modifier_total`
(ADR-0278), by `world/mechanics/levers.py` (`lever_total`, `scale_by_percent`). A percent
lever is integer percentage points on the amount being gained or charged (the
`favor_earning` convention): `amount * (100 + total) // 100`, whole units, floored. A loss is
never scaled. An unauthored target reads as 0 and the seam is byte for byte what it was.

| Lever | Category / target | Reader (the one seam) | Semantics |
|---|---|---|---|
| Income | `income` / `income` | `currency.services._income_for`: the house allowance a member collects (`distribute_allowance`) and an asset collection's landed net (`collect_asset_income`) | percent, floor 0; the house's even split (`per_member`) is unchanged, only what reaches the purse. The pool stays the ceiling and it is the bonus that bends to it, never a plain share: every member is paid up to their split first, then what the split left on the table (a Gambler's shortfall, the whole-copper remainder) tops up the members whose lever asked for more, in membership order, until the pool is spent; the treasury is never overdrawn |
| Reputation gain | `reputation_gain` / `reputation_gain`, plus `reputation_gain_society`, `reputation_gain_organization` | `societies.renown._reputation_gain_for` at `bump_society_reputation` and `bump_organization_reputation`, the chokepoints every regard write goes through (renown awards, stakes, crime) | percent on a positive delta only; the general target and the leg's target add; legend untouched (ADR-0249). The award loops read the percent once (`reputation_gain_percent`) and pass `scale_gain=False` so a deed records what each society actually moved by; creation's connection and enemy seeds pass `scale_gain=False` too, since a starting seed is where the character begins, not regard gained in play |
| Relationship gain | `relationship_gain` / `relationship_gain` | `relationships.services._relationship_gain_for` in `apply_affection_shift`, for the sheet whose regard moves | percent on a positive amount; conflict is not a gain. The SHIFT_AFFECTION consequence handler reports the scaled shift and names a gain scaled to nothing `no_gain`, not a repeat |
| Comfort | `comfort` / `comfort` | `locations.comfort_effect.comfort_level_for_character`, the residence read behind the AP-regen comfort modifier | flat shift in comfort levels, clamped to 1-10. Read when the residence modifier is re-materialized: on a residence or room-comfort change, and (`refresh_comfort_lever`) when a distinction carrying a comfort effect is granted, ranked up or removed, and once at the end of finalize, after the picks (before #4394 a new character's residence modifier was never computed at all: finalize assigns the home directly, so the tenancy grant's residence default saw a chosen residence and skipped the recompute) |
| Fatigue cost | `fatigue_cost` / `fatigue_cost` | `fatigue.services.apply_fatigue` | percent on the charged cost, floor `MIN_FATIGUE_COST`. Covers every action charged through `apply_fatigue` (actions, moves under load, combat); technique fatigue (`apply_technique_fatigue`, magic's own charge) is not a lever seam |
| Disguise sight (#4396) | `disguise_sight` / `mundane`, `magical` | `forms.services.identification.pierced_disguise_kinds`, read by the persona reveal rule (`scenes.persona_display`: `resolve_display_for_viewer`, `build_persona_display_map`, so `identity_revealed_to_viewer`, `look` and the sheet) once per page and only when an undiscovered mask is left on it | a positive total on a kind's target reveals a disguise of that kind as `<mask> (<real>)`, no `PersonaDiscovery` row and no identification check. The kind is the worn overlay's `overlay_kind`, or MUNDANE for a bare false name (`presented_disguise_kind`); a named alt is not a disguise and no sight pierces it. Not a percent: the first point is the whole effect |

The rows are content (#2698): staff author the categories and targets (`world/seeds/levers.py`
`ensure_lever_targets` creates them on a dev or E2E database under `SEED_SAMPLE_CONTENT`), and a
distinction effect on one of the targets is how a Gambler, a Renowned or a Guarded row gets
its teeth. Priced rows carry pluses, awarded rows minuses (the purse rule).

---

## Maneuver effects (#4783, ADR-4783-A)

Each combat maneuver's numbers are a fixed catalog of effects that any modifier source can
target. Maneuvers stay verbs that code fires at set moments; only their numbers moved out of
code. `world/mechanics/maneuver_effects.py` holds the catalog's code side,
`world/mechanics/effect_targets.py` the reader.

**The catalog.** `ManeuverEffect` (`key` unique, a `ManeuverEffectKey`; `base_value`; staff-only
`notes`) has exactly eight rows. The kind of each is derived from the key
(`MANEUVER_EFFECT_KIND`), never stored. Code finds a row by `key`, never by name. The admin
(`ManeuverEffectAdmin`) edits `base_value` and `notes`, with no add, no delete and a read-only key.
Rows are written by migration `0334` in every migrated database, by `ensure_maneuver_effect_rows()`
on the Big Button combat cluster (`world/seeds/clusters.py`), and by `get_maneuver_effect` on a
missing key; an edited base value is kept.

| Key | Kind | Base | Read by |
|---|---|---|---|
| `charge_to_hit` | to hit | 10 | `CombatTechniqueResolver` check modifiers for a CHARGE |
| `charge_damage` | damage | 5 | the same resolver's damage budget for a CHARGE |
| `charge_reach` | reach | 5 | `declare_charge` (hops a charge may cover) |
| `cover_escape_bonus` | escape bonus | 10 | `_resolve_flee`, once per coverer |
| `succor_partial_protection` | partial protection | 50 | `apply_succor_outcome`, combat and scene rounds |
| `interpose_partial_protection` | partial protection | 50 | `interpose_dispatch`, a partial block |
| `rally_morale` | morale | 15 | `_resolve_rally`, per success level of a great success |
| `rally_surge_intensity` | surge intensity | 100 | `_surge_rallied_ally`, as a percentage |

**Targets.** `ModifierTarget` gains `scope_maneuver_effect` (FK to one `ManeuverEffect`,
`CASCADE`) and `scope_effect_kind` (an `EffectKind`). A database constraint
(`modifier_target_one_scope`) stops both being set. In the "maneuver_effect" category
(`MANEUVER_EFFECT_CATEGORY_NAME`, created by migration `0334`, and by `ensure_maneuver_effects` for a schema built
without migrations; the seeder never writes it, since a category is content,
and listed in `EQUIPMENT_RELEVANT_CATEGORIES` so the equipment walk reaches it: the vow stat
scaling row and the crossing-choice conditions of worn facets and mantles; distinctions, crafted
recipe modifiers and active conditions reach it without that entry), `clean()` requires exactly
one of the two (a target with a technique scope names a kind instead, see "Technique effect scopes"); no other category may set either. A target with neither set matches nothing.
Staff author targets after the catalog rows exist, then point a source at the target (an unsized
distinction effect, a crafted recipe modifier, a condition modifier, a facet or mantle
crossing-choice condition, or a vow stat scaling row). A facet's own tier-0 flat bonus does not
reach an effect target: it needs a resonance on the target, and an effect target has none.

**The reader.**
- `effect_value(sheet, key)`: base value plus `effect_modifier_total`, floored at 0, and capped
  at 100 for partial protection. `sheet=None` gives the base value.
- `effect_modifier_total(sheet, key)`: the unclamped sum of `get_modifier_total` and
  `get_condition_modifier_total` over every active target scoped to this effect or its kind.
  For a caller that scales the base itself.

**Wiring (the sheet is the acting character's).**
- **Charge.** To hit and damage are `max(0, base x (2 with a Lance, else 1) + modifier total)`:
  a Lance doubles the base only, so a +3 modifier stays +3 (5 x 2 + 3 = 13). Reach is
  `effect_value(Charge: reach)` hops, checked at declaration. The roll label stays "Charge".
- **Cover.** `_resolve_flee` adds one contribution per coverer, labelled "Covered by <persona
  name>", worth that coverer's own Cover escape bonus. `FleeConfig.cover_bonus` and the
  "Covering allies xN" label are gone.
- **Succor.** `apply_succor_outcome(result, partial_protection)`: clean success 0.0, partial
  `1 - partial_protection / 100`, failure 1.0. Combat and scene rounds both pass the
  succorer's value.
- **Interpose.** A partial block leaves `amount x (100 - value) // 100`; with no interposer
  sheet the base value is used.
- **Rally.** Morale restored is success level x the rallier's Rally morale. The surge intensity
  scale is `value / 100`, and the ally's roll line says "surge +N" when it adds intensity.
- **Vows.** A `VowStatScaling` row on an effect target adds the holder's SHOWN thread level
  (stored // 10) x `bonus_per_level`; every other category keeps the stored level. Rows on an
  engaged role and on its anchor role both count, so a holder graduated to a sub-role keeps
  their scaling (`docs/systems/covenants.md`).

**Rules and limits.** Each effect kind fixes the unit of every modifier that targets it.
Damage, to-hit and partial protection take a size (#4876, the owner's "likely grants only"
ruling on #4824): `EFFECT_KIND_LANE` (`constants.py`) maps each to a `ModifierLane` (damage
points, check points, percentage points), and `ModifierTarget.value_lane` reads it from the
target's kind (`ModifierTarget.effect_kind`). The effect readers' shared sum (`_modifier_total`
in `effect_targets.py`) reads a laned target as the stat read does:
`modifier_target_contributions` and `condition_target_contributions` in that lane, one
`ModifierBreakdown` per lane tapered by its `ModifierTaper` rows, so a sized distinction effect
counts the lane's value at its holder's level and held-rank size, and a sized technique buff at
its own level and size. With no table row it keeps its flat amount. Every other kind takes flat
amounts only: a size there is refused by `DistinctionEffect.clean()` ("Only damage, to-hit and
partial protection effects take a size; clear the size."), as is a `DistinctionEffectRankSize`
row on one. Derived amounts (#4824 part 1) are not built. A maneuver reads only the targets that carry no technique or
opponent scope, so a scoped target never reaches a maneuver (see "Technique effect scopes" and
"Opponent scopes"). A kind-wide "damage" target with no technique scope reaches the
damage of every technique hit, Charge included, and a Charge's own damage effect still counts only
targets scoped to "Charge: damage". The battle Rally
(`world/battles`, `RALLY_MORALE_PER_LEVEL`) is a different action and is untouched.

## Technique effect scopes (#4822, ADR-4783-A)

A modifier can name the technique it changes. Slice 2 of #4783 adds five scope columns to
`ModifierTarget` and two effect kinds, so "+4 fire damage on Pyromancy techniques" or "+2 severity
on the conditions of Ember Veil" is a target a distinction, crafted recipe modifier, condition,
facet or mantle crossing-choice condition or vow stat scaling row points at, like any maneuver
effect.

**Scopes.** `scope_technique` (FK `Technique`), `scope_gift` (FK `Gift`), `scope_technique_function`
(a `TechniqueFunction`), `scope_damage_type` (FK `DamageType`) and `scope_resonance` (FK
`Resonance`). The FKs are `CASCADE`, since clearing one would widen the target. They are new
columns, separate from `target_damage_type` and `target_resonance`, which are one-to-one identity
links for their own categories. Targets stay in the "maneuver_effect" category, which already
reaches every source. Rules, held by `ModifierTarget.clean()` and the
`modifier_target_technique_scope_needs_kind` constraint:
- A technique scope needs `scope_effect_kind` and no `scope_maneuver_effect`; a technique scope on
  any other category is refused.
- `scope_damage_type` is for the damage kind only.
- A technique scope works only with damage, condition severity and condition duration; the admin
  refuses any other kind.
- Scopes combine: every scope a target sets must match. Gift + damage type + damage kind is "fire
  damage of any Pyromancy technique". An unset scope means any.
- A gift scope matches the technique's gift and that gift's parent, so a target scoped to an
  umbrella gift reaches the techniques of its child gifts. A target scoped to a child gift does not
  reach the parent's own techniques.
- Slice 3 adds two more narrowing scopes with the same rules, for the opponent (see "Opponent
  scopes").

**What a kind modifier reaches.** A kind-only damage modifier applies to every damage profile a
cast deals, signature and vow-added profiles included, and a negative one lowers the whole hit
(floored at 0). Severity and duration modifiers apply only to the technique's own condition rows,
not signature or vow-added ones.

**Kinds.** `EffectKind` gains `CONDITION_SEVERITY` and `CONDITION_DURATION` (rounds); `DAMAGE`
already existed. Neither new kind has a catalog effect, so they are reached by a kind scope only.

**The reader** (`world/mechanics/effect_targets.py`):
- `technique_effect_context(sheet, technique, damage_type_id=None)` builds a frozen
  `TechniqueEffectContext` (`world/mechanics/types.py`): the technique id, its gift and parent
  gift ids, the function set from `cached_function_tags`, the resonance ids from
  `gift_resonances_for`, and the resolved damage type id.
- `technique_effect_targets(kind)`: one query for the active maneuver-effect targets of that kind
  that name no one maneuver effect. Kind-wide and technique-scoped targets both come back.
- `technique_effect_total(sheet, context, targets)`: the unclamped sum over the targets that fit
  the context. No sheet gives 0.
- `TechniqueConditionBonus.for_cast(sheet, technique).for_target(target)`: the
  `(severity, duration)` pair for a condition landing on one target (see "Opponent scopes");
  `for_cast` loads both kinds once, and with neither authored anywhere it builds no context.
- `effect_modifier_total(sheet, key, kind_wide=False)` leaves out targets that name only the kind,
  which Charge damage uses so a kind-wide damage target is not counted twice.

Matching uses the technique as authored, not the caster's specialized variant.

**Damage** (combat only; a scene cast has no technique damage step). `_profile_damage` in
`world/combat/services/techniques/technique_resolver.py` adds one flat term per damage profile,
matched on the profile's resolved damage type (untyped counts as Physical), with the other flat
terms and inside the existing floor at 0, so a large negative modifier cannot heal. A technique
with two profiles gains the bonus twice, and an area technique gains it on every opponent.
`TechniqueDamageBonus` is built once per cast and works out the total once per distinct damage
type. In a Charge a kind-only damage target is counted by this term; the Charge damage term counts
only targets scoped to "Charge: damage". Charge to hit is unchanged.

**Conditions.** `TechniqueConditionBonus.for_target` feeds the `target_bonus` argument of
`apply_technique_conditions` on the technique's own condition rows in a combat cast
(`CombatTechniqueResolver`), a scene cast (`scenes.cast_services`) and a passive technique
(`combat/services/damage/passive_techniques.py`); the flat `severity_bonus` and `duration_bonus`
arguments stay for the vow-added path. Signature-motif and vow-added rows keep their own
sources. `bonused_severity` and `bonused_duration` (`world/magic/services/condition_application.py`)
floor a negative bonus at 1; a condition with no duration stays without one; a team-lane row
ignores both bonuses.

**Not built.** Derived and sized amounts (#4824), so technique-scoped and opponent-scoped
modifiers are flat. Opponent scopes on a single maneuver effect and on to hit are not built either
(see "Opponent scopes"). The staff power evaluator values a technique alone, so per-character
modifiers do not show there. Power-category targets that gate on `target_resonance` or `target_damage_type`
raise power, which scales a profile; this term is a flat amount after scaling, and neither counts
the other.

## Opponent scopes (#4823, slice 3 of #4783)

A modifier can name who it lands on: "+5 damage against abyssal opponents", "+2 severity on
conditions that land on a Bleeding target". Two more nullable columns on `ModifierTarget`, in the
same "maneuver_effect" category, reached by every source a technique-scoped target is.

**Scopes.** `scope_opponent_property` (FK `Property`) and `scope_opponent_condition` (FK
`ConditionTemplate`), both `CASCADE`, since clearing one would widen the target to every opponent.
They follow the technique scope rules: they need `scope_effect_kind` and no `scope_maneuver_effect`
(the `modifier_target_technique_scope_needs_kind` constraint, extended in migration `0343`), they
combine with each other and with the technique scopes (every scope set must match), and an unset
scope means any. `ModifierTarget.has_opponent_scope` is true when either is set;
`has_technique_scope` is true for any narrowing scope, opponent side included. They narrow damage,
condition severity and condition duration; the admin refuses any other kind.

**What counts as having a property or condition.** `opponent_facts(target)`
(`world/mechanics/effect_targets.py`) returns an `OpponentFacts` (`world/mechanics/types.py`):
- A property is had when the target has a stored `ObjectProperty` row, when the template or the
  current stage of one of its active conditions grants it (the same route
  `PropertyRequirement._granted_by_condition` reads), or, for a player character, when its primary
  persona carries it as a tag (`CharacterSheet.has_property`).
- A condition is had when the target holds an active instance of the template. Active is the
  conditions app's own meaning: not suppressed and not past an in-game expiry.
- It is four bounded queries however many conditions the target holds, and nothing for no object.

**When it reads.** The facts are read only when an opponent-scoped target exists
(`opponent_targets_exist(targets)`); with none in the game no opponent is looked at.
- Damage: `TechniqueDamageBonus.read_opponent(opponent)` reads once per opponent, before that
  opponent's first damage profile lands, so a condition one profile consumes does not change the
  next profile's bonus. `for_type(damage_type_id, opponent)` caches the total per resolved damage
  type and opponent.
- Conditions: `TechniqueConditionBonus` (built once per cast by `for_cast`) answers
  `for_target(target)` once per target and reuses it for every later row. The facts are read
  before the cast's first condition lands, since the builder works out every row before any is
  applied. `apply_technique_conditions` takes it as `target_bonus`, adds it to the flat bonuses
  per target, and a team-lane row still ignores it. A passive technique's rows read whoever each
  lands on: the actor, the opponents not fighting on the actor's side, or the other participants.
- The signature-motif and vow-added rows keep their own sources and are unchanged.

**Maneuvers.** A maneuver reader never matches an opponent-scoped target
(`_matching_targets` leaves out any target with either scope set), as it never matches a
technique-scoped one.

**Stacking.** An opponent-scoped modifier is the attacker's own term. It is added in the same sum
as the technique's other flat terms and `property_damage_bonus` (the defender-side
`PropertyDamageModifier` rows on the properties the target has), inside the one floor at 0. It does
not replace that lane: a target with the property gets both the staff-authored defender-side amount
and the attacker's modifier. `ConditionDamageInteraction.damage_modifier_percent`, the other
defender-side lane, is a percentage worked out afterward on the finished hit from the conditions the
target is under (`process_damage_interactions`), so it scales the opponent-scoped bonus along with
the rest of the damage.

**Not built.** Opponent scopes on a single maneuver effect, on to hit, and on derived or sized
amounts (#4824).

## API Endpoints

### Modifier Categories
- `GET /api/mechanics/categories/` - List all modifier categories (no pagination, small lookup table)

### Modifier Targets
- `GET /api/mechanics/targets/` - List active modifier targets
- `GET /api/mechanics/targets/{id}/` - Retrieve single modifier target

**Query Parameters:**
- `category` - Filter by category name (case-insensitive)
- `is_active` - Filter by active status

### Character Modifiers
- `GET /api/mechanics/character-modifiers/` - List character modifiers
- `GET /api/mechanics/character-modifiers/{id}/` - Retrieve single modifier

**Query Parameters:**
- `character` - Filter by CharacterSheet ID

---

## Integration Points

- **Distinctions**: Primary modifier source. `create_distinction_modifiers()` is called when a `CharacterDistinction` is created; `delete_distinction_modifiers()` on removal; `update_distinction_rank()` on rank change.
- **Magic**: Aura percentages (`magic.services.recompute_aura()`) read `CharacterResonance.lifetime_earned` grouped by affinity — no denormalized aggregate to sync. Resonance-category `DistinctionEffect`s no longer write a `CharacterModifier` row at all — they flow through `reconcile_distinction_resonance_grants` (the `DistinctionResonanceGrant` sidecar) instead (#1834); see "Distinction Lifecycle" above.
- **Action Points**: `ActionPointPool._get_ap_modifier()` uses string-based lookup for AP modifier targets (pending target FK when AP system is built).
- **Progression**: Development rate modifiers use string-based lookup (pending target FK when progression system is built).
- **Equipment** (future): Will follow the same `ModifierSource` pattern with equipment-specific FK fields.
- **Conditions** (future): Will follow the same pattern for status effect modifiers.

---

## Admin

All models registered with search, filters, and `list_select_related` for performance:

- `ModifierCategoryAdmin` - Editable `display_order`, truncated description display
- `ModifierTargetAdmin` - Filterable by category and active status, editable `display_order` and `is_active`
- `ModifierSourceAdmin` - Shows source type and display, `raw_id_fields` for FKs
- `CharacterModifierAdmin` - Custom display methods for character name and modifier target (since `modifier_target` is a derived property), `list_select_related` through full source chain
