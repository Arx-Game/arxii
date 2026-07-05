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
| `ModifierTarget` | Unified registry of all things that can be modified; replaces separate Affinity, Resonance, GoalDomain models | `name`, `category` (FK ModifierCategory), `description`, `display_order`, `is_active`, `target_trait` (FK Trait, nullable), `affiliated_affinity` (self FK), `opposite` (self OneToOne), `resonance_affinity` (ResonanceAffinity) |

### Per-Character Data

| Model | Purpose | Key Fields |
|-------|---------|------------|
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
  staff-only, in-scene verb mirroring `SetTheStageAction`/`CmdSetStage`. No
  duplicate-instantiation guard (intentional — see ADR-0091).
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

---

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
