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
Rows are written by migration `0333` in every migrated database, by `ensure_maneuver_effect_rows()`
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
(`MANEUVER_EFFECT_CATEGORY_NAME`, created by migration `0333`, and by `ensure_maneuver_effects` for a schema built
without migrations; the seeder never writes it, since a category is content,
and listed in `EQUIPMENT_RELEVANT_CATEGORIES` so the equipment walk reaches it: the vow stat
scaling row and the crossing-choice conditions of worn facets and mantles; distinctions, crafted
recipe modifiers and active conditions reach it without that entry), `clean()` requires exactly
one of the two; no other category may set either. A target with neither set matches nothing.
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

**Rules and limits.** Each effect kind fixes the unit of every modifier that targets it. A
modifier on an effect is a flat amount: a distinction effect with a size on a maneuver-effect
target is refused by `DistinctionEffect.clean()` ("Maneuver effects take flat amounts only; clear
the size."), as is a `DistinctionEffectRankSize` row on one. Derived amounts, sized modifiers on effects, and scopes for a technique, a
damage type, a resonance and the opponent are not built. "Damage, any maneuver" reaches only
Charge today, so author damage targets as "Charge: damage". The battle Rally
(`world/battles`, `RALLY_MORALE_PER_LEVEL`) is a different action and is untouched.

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
