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
| `CheckType` | Named check definition with trait/aspect composition | `name`, `category` (FK CheckCategory), `description`, `is_active`, `display_order`, `owner_sheet` (nullable FK `character_sheets.CharacterSheet`, related_name `owned_check_types` — NULL = staff/lore-authored; set on the per-character check `ensure_character_magic_check_type` synthesizes, #2724) |
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

### Weight calibration (#2704, ADR-0164 D4)

`CheckTypeCapabilityModifier` is **authored content** — every row is a deliberate,
curated (check_type, capability) pairing, never auto-derived. `weight` is calibrated
from the intended full-impairment penalty, not picked freely: `weight = intended
full-impairment penalty ÷ 5`, because 5 is the unimpaired-mortal rung on the
capability ladder (ADR-0164 D1) and the contribution is scored as deviation from
`innate_baseline` (D3) — a fully-impaired capability (value 0, baseline 5) deviates
by −5, so `weight × -5` must equal the intended penalty. E.g. a row meant to cost a
character −30 points on `Melee Attack` when `movement`-style impairment zeroes out a
baseline-5 capability is authored with `weight = 6` (`30 ÷ 5`).

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
result.level_points    # LEVEL_POINTS_PER_LEVEL x class level, on every check (#2707)
result.total_points    # Final total
```

### get_rollmod (public helper)

```python
from world.checks.services import get_rollmod

# Sum of character.sheet_data.rollmod + character.account.player_data.rollmod
# Returns 0 for missing relations
rollmod = get_rollmod(character)
```

### Opposed checks — two mutually exclusive answers for the opposing side (#2707, ADR-0166)

`compute_check_rating(character, check_type, extra_modifiers=0) -> int` is the one
answer for "what does this character bring to this check, with no dice roll" — it
wraps `_compute_check_breakdown` (the same pipeline `perform_check` uses) and
returns `total_points`.

Two callers build opposed-check difficulty on top of it, and are deliberately
**exclusive** — a call site uses one or the other, never both, because an active
resistance rating already contains the defender's level points:

```python
from world.checks.services import compute_resist_increment, level_opposition

# ACTIVE: the defender spends a defence check of their own (e.g. Composure).
# Routes through compute_check_rating, so it carries the defender's full
# rating — trait, specialization, aspect, and capability points (NOT perk
# points: compute_check_rating takes no situation_ctx, so
# _situational_perk_check_bonus short-circuits to 0 rather than firing its
# announcement side effect) — plus the effort-level modifier. Clamped >= 0.
increment = compute_resist_increment(defender_character, resist_effort_level="high")

# level_override (whole-branch-review fix, #2707): compute_check_rating /
# compute_resist_increment resolve level from the defender's own objectdb by
# default (get_character_path_level's CharacterClassLevel rows) -- a gap for an
# ephemeral CombatOpponent, which has none. level_override SUBSTITUTES for that
# resolved level (never adds to it) in both the level_points term and the
# aspect-bonus level scaling. None (the default) is byte-identical to before.
increment = compute_resist_increment(
    target.objectdb, effort_level, level_override=target.level
)

# PASSIVE: the defender contributes nothing beyond existing. LEVEL_POINTS_PER_LEVEL
# * level always; plus, when a character is given, the acting check's aspects
# scored against the DEFENDER's Path (their wheelhouse protects them). A
# character=None (an ephemeral NPC with no sheet) contributes level alone.
difficulty = level_opposition(check_type, level=defender_level, character=defender_character)
```

`_social_combat_difficulty` (`world/combat/services.py`, backing the Demoralize/Taunt/
Parley combat verbs) is the one caller of `compute_resist_increment` that passes
`level_override` — it opposes a `CombatOpponent`, whose authored `level` field isn't
reachable through its `objectdb`'s class-level rows (an ephemeral NPC has none). Without
the override, a boss's morale defense always floored at level 1 even though the same
opponent's offense already opposed PC checks at its real level via `level_opposition`.

`resolve_target_difficulty` (`actions/effects/base.py`) also uses
`compute_check_rating` directly to get a target's resistance rating for
`target_difficulty` — replacing an earlier version that rolled a throwaway
`perform_check` and discarded the outcome, which had the side effect of
silently burning the target's rollmod.

Combat wires `level_opposition` at three call sites — offense (`focused_opponent_target
.level`), penetration (`target.level`, additive on top of the authored `barrier_strength`,
never replacing it), and NPC-attack defense (`opponent_action.opponent.level`, the
inverse direction: the attacking NPC's level sets the defending PC's difficulty). See
`docs/systems/COMBAT_DEFENSES.md`.

**Clash is the deliberate exception.** `world/combat/clash.py`'s clash-contribution roll
still passes `target_difficulty=0` — a clash is a symmetric contest (both sides roll their
own check and the results are compared, the same shape as `_resolve_joust_pass`'s
`success_level` gap), so each side's level already rides its own roll and an opposition
term would double-count it. See ADR-0166.

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

2.4. Level points (#2707): LEVEL_POINTS_PER_LEVEL x character_level, on EVERY check.
   Level was previously only reachable through the aspect bonus above, which is zero
   unless the CheckType has an authored CheckTypeAspect matching the character's Path
   -- so on most checks level did nothing. This is a guaranteed floor, additive with
   (not a replacement for) the aspect bonus.

2.5. Capability points from authored CheckTypeCapabilityModifier rows (#2505)
   No authored rows on check_type -> 0, capability oracle never called (curated gate).
   character.sheet_data missing -> 0, never raises.
   capability_points = int(sum(
       row.weight * (get_effective_capability_value(sheet, row.capability) - row.capability.innate_baseline)
       for row in check_type.capability_modifiers.all()
   ))  # truncated toward zero ONCE, after summing every row -- never per-row
   # Scored as DEVIATION from innate_baseline (#2704, ADR-0164 D3), not the raw
   # value -- an unimpaired character (effective value == baseline) contributes
   # exactly 0 to every check that reads the capability, so authoring a
   # capability across many checks never inflates them. Arithmetically a no-op
   # for capabilities whose innate_baseline is 0 (most of them).
   # `_capability_point_allocation` is the ONE place this arithmetic is computed;
   # collect_check_modifiers's CAPABILITY provenance calls the same helper and
   # allocates the same truncated total back across rows by largest remainder
   # (now handling mixed-sign rows), so recorded contributions always sum to
   # exactly capability_points (#2505 fix).

3. Total = trait_points + specialization_points + aspect_bonus + level_points + capability_points
   + extra_modifiers

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

# Shared arithmetic (#2505): raw per-row `weight * (value - innate_baseline)` products
# (#2704, ADR-0164 D3 -- deviation from baseline, not the raw value), truncated-toward-zero
# total, and largest-remainder allocation of that total back across rows (mixed-sign safe).
# The ONE place either _calculate_capability_points (roll path) or _capability_contributions
# (provenance path, in collect_check_modifiers) computes this, so the two paths cannot drift.
_capability_point_allocation(character_sheet, capability_modifiers) -> tuple[int, list[int]]

# Get character's primary class level (or highest, or default 1) — shared with
# progression (#2707); world.checks.services no longer declares its own copy
world.progression.services.skill_development.get_character_path_level(character) -> int

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
- **Classes app**: Uses `Aspect` and `PathAspect` for aspect bonus calculation
- **Progression app**: Uses `CharacterPathHistory` for current path lookup; `get_character_path_level`
  (`world.progression.services.skill_development`) is the sole source of a character's class level (#2707)
  -- both the level-points term and the aspect bonus's level scaling read it
- **Combat app** (#2707): `CombatOpponent.level` is the authority for how sturdy an opponent is on BOTH
  sides — read directly by `level_opposition` at the offense/penetration/NPC-attack-defense sites, and
  passed as `compute_resist_increment(..., level_override=opponent.level)` for the social verbs, so an
  ephemeral NPC (which has no `CharacterClassLevel` rows behind its `objectdb`) no longer resists at
  level 1 while opposing a stab at its authored level
- **Conditions app** (#2505): `get_effective_capability_value(sheet, capability)` (the agency oracle —
  innate baseline + CharacterModifier total + condition contributions + passive-grant floor + best
  (MAX) technique-grant value, floored at 0) is the sole source `_capability_point_allocation` reads
  on behalf of both `_calculate_capability_points` (roll path) and `collect_check_modifiers`'s
  CAPABILITY contributions (provenance path) — so a technique-granted capability reaches the check
  bridge the same as an innate/condition-derived one; lazily imported to avoid a module cycle
  (`world.conditions.services` already imports `world.checks.services` at module scope)
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

Gated by `MinimumGMLevelPrerequisite(GMLevel.SENIOR)` (#2857 — staff bypass, else
SENIOR-tier GM trust). JUNIOR/STARTING player GMs are funneled to
`SetSituationAction` (`setsituation`) and `PlaceChallengeAction` (below), where
checks emerge from authored content with pre-set outcomes. The ad-hoc check is a
staff/senior stopgap for impromptu moments no authored challenge covers — it
returns a bare graded result with no consequences. Telnet: `gm check [find
<term>]` / `gm check <character> <check-type>=<band> [edge=<reason>|setback=<reason>]`
(`commands/gm_ops.py`). Sibling actions `GMAwardAction` (`gm_award_progression`) and
`GMApplyConditionAction` (`gm_apply_condition`) round out the GM adjudication toolkit — see
`docs/systems/INDEX.md` and `docs/roadmap/gm-system.md`.

---

## Quick-Placing an Authored Challenge (#2865)

The JUNIOR-tier path the SENIOR gate above left missing. `PlaceChallengeAction`
(`actions/definitions/situations.py`, registry key `place_challenge`) places **one**
authored `ChallengeTemplate` against a thing the GM names, without a
pre-authored `SituationTemplate` to wrap it. Still catalog-only per ADR-0110: the
GM picks an authored challenge and names what embodies it; the approaches offered,
the consequences, and the discovery type are the template's own.

- **Mints** a standalone `ChallengeInstance` with `situation_instance=None`, via the
  pre-existing `instantiate_challenge` — the same shape the reactive combat
  challenges (Interpose, Succor, Catch the Faller) have always used. The target
  prop comes from `create_challenge_target_object`, shared with
  `instantiate_situation` so the two paths cannot drift.
- **Adaptation** is one band, with a required reason: `edge_reason` / `setback_reason`
  (mutually exclusive) persist as `ChallengeInstance.severity_adjustment`
  (±`DIFFICULTY_BAND_STEP`) and `adjustment_reason`. Two DB `CheckConstraint`s
  enforce the pair — an arbitrary offset or an unreasoned shift cannot be stored.
  Out of bounds refuses rather than clamping. `adjustment_reason` is GM-facing only
  and never reaches `ChallengeInstanceSerializer`.
- **Difficulty** is read through `ChallengeInstance.effective_severity`
  (`template.severity + severity_adjustment`) by every resolution path in
  `challenge_resolution.py`.
- **Discovery** rides the same `FindSituationAction` (`setsituation find <term>`),
  which searches `ChallengeTemplate` alongside `SituationTemplate` and
  `SituationKind`.
- Gated `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`, matching `SetSituationAction`
  — it mints the same class of live row (ADR-0091). Telnet:
  `setsituation challenge <template>=<target name> [edge=<why>|setback=<why>]`.

### `ChallengeTemplate.severity` is in difficulty points

`resolve_challenge` passes `severity` straight into `perform_check`'s
`target_difficulty`, which every other caller feeds from `DIFFICULTY_VALUES` (15
Trivial … 90 Harrowing). The field's default was `1`, so authored challenges
resolved at the bottom rank and a ±15 band shift had no coherent unit against
them. Since #2865 the default is `DIFFICULTY_VALUES[NORMAL]` and the field is
documented as points, not a 1–5 rating. Authored rows in the lore repo are
re-expressed on that scale as content work.

---

## Seeded Compositions

Check compositions are authored as seed data (the design tenet: **stat + skill (+ specialization)**, rarely stat+stat). The seed clusters live in `world/seeds/`.

**`CheckCategory`/`CheckType`/`CheckTypeTrait` (+ `skills.Skill`/`traits.Trait`/`classes.Aspect`/`classes.PathAspect`) are content-repo-owned (#2698, ADR-0168)** — every cluster below looks its rows up via `world.seeds.sample_content.authored_or_sample()` rather than inventing them; a row is only invented when `SEED_SAMPLE_CONTENT` is on (a third-party clone with no content repo). Maintainers author these in the content repo, and the composition table below describes what the content repo is expected to carry, not what a bare Big Button press creates. `skills.Specialization`/`checks.CheckTypeSpecialization`/`checks.CheckTypeAspect` are NOT content-repo-owned and keep seeding unconditionally. A reseed no longer wipes and rewrites a CheckType's composition (the pre-#2698 "authoritative rewrite" idiom silently reverted any content-repo/staff-tuned weight on every Big Button press) — `get_or_create`/`authored_or_sample` converge instead, so an edited weight survives.

**Code-required `CheckType`/`CheckCategory` rows are declared, not assumed (#2724, ADR-0171).** A handful of check types are named by string literal deep in service code — fatigue's `"fatigue_willpower"`/endurance rows (`world.fatigue.services`), the fury control-retention check, the vitals survival category/endurance/death checks. These still live in `CONTENT_MODELS` and are still content-repo-exportable, but the dependency is now declared in `world.seeds.config_prerequisites.CONFIG_PREREQUISITES` and runs **before** the content load (`world.seeds.database.load_content_first`) — so an authored fixture always upserts over the code default, and a staff member editing `checktype.json` can see, in one place, which rows are load-bearing rather than discovering it by deleting one and breaking fatigue checks. See ADR-0171.

**Per-character `CheckType` rows are excluded from export by `owner_sheet`, not a name pattern (#2724, ADR-0171).** `ensure_character_magic_check_type` (`world.magic.seeds_checks`) synthesizes one `CheckType` per `CharacterSheet` — a player's personal magic check, named `f"Magic Check — sheet {pk}"`. Because `checks.checktype` stays in `CONTENT_MODELS` (staff-authored check types must keep exporting), these synthesized rows would otherwise ship in the content corpus as if authored. `core_management.content_export.EXPORT_FILTERS` filters `checks.checktype` on `owner_sheet__isnull=True` and `checks.checktypetrait` on `check_type__owner_sheet__isnull=True` at export time — the row-level boundary sits on top of the model-level `CONTENT_MODELS` allowlist. See ADR-0171 for why this is a real FK column and not a name-prefix check.

| Cluster | Checks | Composition |
|---------|--------|-------------|
| `combat_checks` (#1706, #2757, #2858, #2879) | `Melee Combat` | Melee Combat (skill) + situational stat (default: strength; combat system passes `stat_override` from weapon — `ItemTemplate.weapon_class` blend (str/agi weighted by `strength_tenths`) first, `gear_archetype` name as fallback) |
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
| `security` (#2180, #2757) | `Athletics` | Athletics (skill) + situational stat (default: strength; `resolve_security_check` passes `stat_override` from `SecurityCheckKind`) |
| `security` | `Lockpick` / `Guard Detection` | wits+Skulduggery / perception+Investigation |

**Resist checks** (Reflexes, Escalation Pace, Endurance, Mortal Resolve) are the tenet-permitted single-stat exception — they seed exactly one `CheckTypeTrait`. The `Melee Combat` skill catalog (with weapon-class specializations aligned to `progression.services.scene_integration`'s `weapon_map`) is seeded by the `combat_checks` cluster; the penetration/flee retrofits depend on it.

**Technique routing (#1706):** `resolve_cast_action_template` reads `Technique.action_category` — a `PHYSICAL` technique with no chosen consequence-pool flavor resolves to the combat `Melee Attack` `ActionTemplate` (so physical attacks roll a combat check, not the magic fallback); non-physical techniques resolve to the magic standalone cast template.

---

## Security Checks (#2180, #2757)

Security-domain check types seeded via the `"security"` cluster
(`world/seeds/security_checks.py`):

| CheckType | Category | Composition | Used by |
|---|---|---|---|
| Stealth | Physical | agility + Stealth | Sneaking past guards (reuses #1464 seed) |
| Lockpick | Physical | wits + Skulduggery (+ Lockpicking) | Picking locks (#2176, renamed from Larceny #1825) |
| Athletics | Physical | Athletics (skill) + situational stat (default: strength) | Forcing barriers / fleeing via window (#2757 merge) |
| Guard Detection | Exploration | perception + Investigation | Guard NPC spotting intruders (#2178) |

**`SecurityCheckKind`** (`world/checks/constants.py`) maps each kind to its
CheckType name via `SECURITY_CHECK_TYPE_NAMES`, and to its stat override via
`SECURITY_CHECK_STAT_OVERRIDE` (#2757). Both `BREAK_AND_ENTER` and
`ESCAPE_THROUGH_WINDOW` resolve to the "Athletics" CheckType — the former
passes `stat_override="strength"`, the latter `stat_override="agility"`.

**`resolve_security_check(kind, actor, *, target_difficulty, extra_modifiers)`**
(`world/checks/security_services.py`) is the helper entry point. It looks up the
CheckType by name, resolves the stat_override from the kind, and delegates to
`perform_check`. The caller computes `target_difficulty` from domain context
(lock level, guard level, window height).

Two skills: **Larceny** (fine manipulation — locks, pockets) and **Athletics**
(running, climbing, force). Specializations: **Lockpicking** (under Larceny) and
**Climbing** (under Athletics). All weights PLACEHOLDER (1.0).
