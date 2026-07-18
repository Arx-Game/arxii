# Checks System

Database-defined check types with weighted trait and aspect composition, resolved through the rank/chart/outcome pipeline.

**Source:** `src/world/checks/`

---

## Types (types.py)

```python
from world.checks.types import (
    CheckResult,  # Dataclass returned by perform_check (no roll numbers exposed)
)
```

### CheckResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `check_type` | `CheckType` | The check type that was resolved |
| `outcome` | `CheckOutcome \| None` | The resolved outcome |
| `chart` | `ResultChart \| None` | The result chart used |
| `roller_rank` | `CheckRank \| None` | Roller's rank |
| `target_rank` | `CheckRank \| None` | Target's rank |
| `rank_difference` | `int` | roller_rank - target_rank |
| `trait_points` | `int` | Points from weighted traits |
| `aspect_bonus` | `int` | Bonus from path aspects |
| `specialization_points` | `int` | Points from owned specializations (default 0, #1688) |
| `capability_points` | `int` | Weighted authored `CheckTypeCapabilityModifier` points (default 0, #2505) |
| `total_points` | `int` | trait_points + specialization_points + aspect_bonus + capability_points + extra_modifiers |

### CheckResult Properties

```python
result.outcome_name   # str: outcome name or "Unknown"
result.success_level  # int: outcome success_level or 0
result.chart_name     # str: chart name or "No Chart Found"
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CheckCategory` | Groups check types (Social, Combat, Exploration, Magic) | `name` (unique), `description`, `display_order` |
| `CheckType` | Named check definition with trait/aspect composition | `name`, `category` (FK CheckCategory), `description`, `is_active`, `display_order` |
| `CheckTypeTrait` | Weighted trait contribution to a check type | `check_type` (FK CheckType), `trait` (FK Trait), `weight` (Decimal, default 1.0) |
| `CheckTypeAspect` | Weighted aspect relevance for a check type | `check_type` (FK CheckType), `aspect` (FK Aspect), `weight` (Decimal, default 1.0) |
| `CheckTypeCapabilityModifier` (#2505) | Weighted capability contribution to a check type — curated gate: only listed (check_type, capability) pairs ever move points | `check_type` (FK CheckType, related_name `capability_modifiers`), `capability` (FK `conditions.CapabilityType`), `weight` (Decimal, default 1.0) |

**Rule: a `CheckType.name` must never be duplicated across categories.** The DB
constraint is only `unique_together = ["name", "category"]`, but several call sites
look a `CheckType` up by bare name with no category filter — e.g.
`CheckType.objects.get(name="Stealth")` (`world/npc_services/guard_services.py:83`)
and `CheckType.objects.get_or_create(name=ENDURANCE_CHECK_NAME, ...)`
(`world/vitals/services.py:255`). A second same-named `CheckType` in a different
category makes those lookups raise `MultipleObjectsReturned` (or silently return the
wrong row for `get_or_create`) — treat every `CheckType.name` as globally unique in
practice, even though the schema doesn't enforce it (#2501 content-pipeline audit).

### Authoring guardrail: one channel per condition/check pair (#2505)

A condition can reach the same check through **two independent channels**, and
authoring both for the same (condition, check_type) pair silently double-counts
the condition's effect:

1. **Direct**: a `ConditionCheckModifier` (`world/conditions/models.py`) applies a flat
   value straight to `check_type` while the condition is active.
2. **Indirect**: a `ConditionCapabilityEffect` boosts a `CapabilityType`'s value (folded
   in by `get_effective_capability_value`, the agency oracle), and that same
   `CapabilityType` is also linked to `check_type` via a weighted
   `CheckTypeCapabilityModifier`.

If both exist for the same condition/check pair, the condition's effect lands on the
roll twice. **Author exactly one channel per condition/check pair** — pick the direct
`ConditionCheckModifier` when the effect is check-specific and shouldn't ripple to
anything else that reads the capability, or route it through the capability
(`ConditionCapabilityEffect` + `CheckTypeCapabilityModifier`) when the effect should
also show up anywhere else that capability is read (available actions, other checks).
This is the same curated-never-invented discipline as the rest of the modifier
seam — nothing here is enforced by a DB constraint; it is a review-time authoring
rule. This is independent of, and does not change, the existing `CheckType`
`(name, category)` natural-key uniqueness rule.

---

## Key Methods

### perform_check (main resolution function)

```python
from world.checks.services import perform_check

# Perform a check against a flat difficulty
result = perform_check(
    character=character,           # ObjectDB instance
    check_type=check_type,         # CheckType instance
    target_difficulty=0,           # Target points to beat (default 0)
    extra_modifiers=0,             # Bonus/penalty from caller (goals, magic, combat, conditions)
)

# Use the result
result.outcome_name    # "Success", "Catastrophic Failure", etc.
result.success_level   # -10 to +10
result.trait_points    # Points from character's traits
result.aspect_bonus    # Bonus from path aspects
result.total_points    # Final total
```

### get_rollmod (public helper)

```python
from world.checks.services import get_rollmod

# Sum of character.sheet_data.rollmod + character.account.player_data.rollmod
# Returns 0 for missing relations
rollmod = get_rollmod(character)
```

---

## Resolution Pipeline

```
1. Weighted trait points
   For each CheckTypeTrait:
     raw_value = handler.get_trait_value(trait.name)
     weighted_value = int(raw_value * weight)
     points += PointConversionRange.calculate_points(trait_type, weighted_value)

2. Aspect bonus from path
   latest_path = CharacterPathHistory (most recent)
   For each CheckTypeAspect with matching PathAspect:
     bonus += int(check_aspect_weight * path_aspect_weight * character_level)

2.5. Capability points from authored CheckTypeCapabilityModifier rows (#2505)
   No authored rows on check_type -> 0, capability oracle never called (curated gate).
   character.sheet_data missing -> 0, never raises.
   capability_points = int(sum(
       row.weight * get_effective_capability_value(sheet, row.capability)
       for row in check_type.capability_modifiers.all()
   ))  # truncated toward zero ONCE, after summing every row -- never per-row
   # `_capability_point_allocation` is the ONE place this arithmetic is computed;
   # collect_check_modifiers's CAPABILITY provenance calls the same helper and
   # allocates the same truncated total back across rows by largest remainder,
   # so recorded contributions always sum to exactly capability_points (#2505 fix).

3. Total = trait_points + specialization_points + aspect_bonus + capability_points + extra_modifiers

4. Total points -> CheckRank.get_rank_for_points()
   Target difficulty -> CheckRank.get_rank_for_points()
   rank_difference = roller_rank - target_rank

5. ResultChart.get_chart_for_difference(rank_difference)

6. Roll 1-100 (random.randint)
   rollmod = get_rollmod(character)
   effective_roll = clamp(roll + rollmod, 1, 100)

7. Query ResultChartOutcome for matching range -> CheckOutcome

8. Return CheckResult dataclass
```

---

## Internal Service Functions

```python
# These are private (_prefixed) and called by perform_check internally:

# Calculate weighted trait points from CheckTypeTrait entries
_calculate_trait_points(handler, check_type) -> int

# Calculate aspect bonus from character's most recent path
_calculate_aspect_bonus(character, check_type, level) -> int

# Calculate weighted capability points from authored CheckTypeCapabilityModifier rows (#2505)
# 0 with no authored rows (curated gate, never calls the capability oracle) or no sheet_data
_calculate_capability_points(character, check_type) -> int

# Shared arithmetic (#2505): raw per-row weight x value products, truncated-toward-zero
# total, and largest-remainder allocation of that total back across rows. The ONE place
# either _calculate_capability_points (roll path) or _capability_contributions (provenance
# path, in collect_check_modifiers) computes this, so the two paths cannot drift.
_capability_point_allocation(character_sheet, capability_modifiers) -> tuple[int, list[int]]

# Get character's primary class level (or highest, or default 1)
_get_character_level(character) -> int

# Look up ResultChartOutcome for a roll value on a chart
_get_outcome_for_roll(chart, roll) -> CheckOutcome | None
```

---

## Admin

All models registered with appropriate admin interfaces:

- `CheckCategoryAdmin` - List with editable `display_order`, inline `CheckType` editing, search by name
- `CheckTypeAdmin` - List/filter by `category` and `is_active`, editable `is_active` and `display_order`, inline `CheckTypeTrait` and `CheckTypeAspect` editing with autocomplete fields

---

## Design Principles

- **No check persistence** -- results are transient, consumed by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals, magic, combat, and conditions compute their own `extra_modifiers` before calling `perform_check`
- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect, CheckTypeCapabilityModifier)
- **No API endpoints** -- check types are staff-defined via admin; resolution is called programmatically by other systems

---

## Integration Points

- **Traits app**: Uses `PointConversionRange`, `CheckRank`, `ResultChart`, `CheckOutcome` for the resolution pipeline
- **Classes app**: Uses `Aspect` and `PathAspect` for aspect bonus calculation, `CharacterClassLevel` for character level
- **Progression app**: Uses `CharacterPathHistory` for current path lookup
- **Conditions app** (#2505): `get_effective_capability_value(sheet, capability)` (the agency oracle — innate
  baseline + CharacterModifier + condition contributions + passive grants) is the sole source
  `_capability_point_allocation` reads on behalf of both `_calculate_capability_points` (roll path) and
  `collect_check_modifiers`'s CAPABILITY contributions (provenance path); lazily imported to avoid a module
  cycle (`world.conditions.services` already imports `world.checks.services` at module scope)
- **Attempts app**: Calls `perform_check()` for resolution; provides roulette display content via `ConsequenceDisplay`
- **Callers** (goals, magic, combat, conditions, GM adjudication): Compute `extra_modifiers` before calling `perform_check()`
- **Mechanics app**: `resolve_challenge()` folds its `capability_source.value` (a `CapabilitySource`, e.g. from a
  technique) into `extra_modifiers` before calling `perform_check()`

---

## GM Ad-Hoc Catalog Invocation (#2118)

The one GM-invocable caller of `perform_check` for moments no pre-authored system covers.
**Governing invariant (ADR-0110): catalog-only invocation — GMs can never invent checks or
select/compose/fire a consequence pool.** `InvokeCatalogCheckAction`
(`actions/definitions/gm_adjudication.py`, registry key `gm_invoke_check`) is the sole entry
point:

- **Check reference**: an authored `CheckType`, resolved pk-or-name against the shared catalog
  only (`resolve_model_by_pk_or_name`, scoped to `is_active=True`); unresolvable refuses with a
  hint back to the discovery surface (`gm check find <term>`) rather than accepting free text.
- **Difficulty**: a `DifficultyChoice` band member only — no integer parameter exists on any
  code path.
- **Situational modifier**: at most one band of `edge` (easier) or `setback` (harder) shift, each
  requiring a free-text reason that is echoed into the result. Never an integer offset.
- **Result**: number-free — only `CheckResult.outcome_name` reaches the message (never
  `total_points`/`trait_points`/`success_level`/the roll), and it goes to the invoking GM only
  (ADR-0031). No audit model records the invocation; the GM narrates the outcome via pose.
- **Discovery**: `find`/list mode (no target) searches the catalog by name, stat+skill trait, or
  description snippet — the paved road to finding the right check instead of inventing one.

Gated by `IsSceneGMPrerequisite` (`actions/prerequisites.py` — staff bypass, else
`Scene.is_gm(actor.active_account)` on the actor's active scene). Telnet: `gm check [find
<term>]` / `gm check <character> <check-type>=<band> [edge=<reason>|setback=<reason>]`
(`commands/gm_ops.py`). Sibling actions `GMAwardAction` (`gm_award_progression`) and
`GMApplyConditionAction` (`gm_apply_condition`) round out the GM adjudication toolkit — see
`docs/systems/INDEX.md` and `docs/roadmap/gm-system.md`.

---

## Seeded Compositions

Check compositions are authored as seed data (the design tenet: **stat + skill (+ specialization)**, rarely stat+stat). The seed clusters live in `world/seeds/`:

| Cluster | Checks | Composition |
|---------|--------|-------------|
| `combat_checks` (#1706) | `Melee Attack` | strength + Melee Combat (+ Small/Medium/Heavy Weapons spec) |
| `combat` | `penetration` | willpower + intellect + Melee Combat |
| `combat` | `flee` | agility + wits + Melee Combat |
| `combat` | `Escalation Pace` | wits (single-stat resist) |
| `vitals` | `Endurance` | stamina (single-stat resist — KO/wound) |
| `vitals` | `Mortal Resolve` | willpower (single-stat resist — death) |
| `positioning` | `Reflexes` | wits (single-stat resist — plummet-catch/interpose) |
| `social` (#1689) | Intimidation/Persuasion/etc. | stat + skill (+ spec) |
| `magic` | cast/ritual checks | willpower + ritualism/occult/theology |
| `investigation` (#1705) | `Search` | perception + Investigation |
| `governance` (#930) | Tax/Investment checks | stat + Scholarship/Economics |
| `stealth` (#1464) | `Stealth` | agility + Stealth |
| `security` (#2180) | `Lockpick` / `Break and Enter` / `Escape Through Window` / `Guard Detection` | wits+Larceny / strength+Athletics / agility+Athletics / perception+Investigation |

**Resist checks** (Reflexes, Escalation Pace, Endurance, Mortal Resolve) are the tenet-permitted single-stat exception — they seed exactly one `CheckTypeTrait`. The `Melee Combat` skill catalog (with weapon-class specializations aligned to `progression.services.scene_integration`'s `weapon_map`) is seeded by the `combat_checks` cluster; the penetration/flee retrofits depend on it.

**Technique routing (#1706):** `resolve_cast_action_template` reads `Technique.action_category` — a `PHYSICAL` technique with no chosen consequence-pool flavor resolves to the combat `Melee Attack` `ActionTemplate` (so physical attacks roll a combat check, not the magic fallback); non-physical techniques resolve to the magic standalone cast template.

---

## Security Checks (#2180)

Five security-domain check types seeded via the `"security"` cluster
(`world/seeds/security_checks.py`):

| CheckType | Category | Composition | Used by |
|---|---|---|---|
| Stealth | Physical | agility + Stealth | Sneaking past guards (reuses #1464 seed) |
| Lockpick | Physical | wits + Larceny (+ Lockpicking) | Picking locks (#2176) |
| Break and Enter | Physical | strength + Athletics | Forcing barriers (#2176) |
| Escape Through Window | Physical | agility + Athletics (+ Climbing) | Fleeing via window (#2175) |
| Guard Detection | Exploration | perception + Investigation | Guard NPC spotting intruders (#2178) |

**`SecurityCheckKind`** (`world/checks/constants.py`) maps each kind to its
CheckType name via `SECURITY_CHECK_TYPE_NAMES`.

**`resolve_security_check(kind, actor, *, target_difficulty, extra_modifiers)`**
(`world/checks/security_services.py`) is the helper entry point. It looks up the
CheckType by name and delegates to `perform_check`. The caller computes
`target_difficulty` from domain context (lock level, guard level, window height).

Two new skills: **Larceny** (fine manipulation — locks, pockets) and **Athletics**
(running, climbing, force). Specializations: **Lockpicking** (under Larceny) and
**Climbing** (under Athletics). All weights PLACEHOLDER (1.0).
