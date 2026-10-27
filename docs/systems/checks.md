# Checks System

Database-defined check types with weighted trait and aspect composition, resolved through the rank/chart/outcome pipeline.

**Source:** `src/world/checks/`

---

## Types (types.py)

```python
from world.checks.types import (
    CheckResult,  # Dataclass returned by perform_check (no roll numbers exposed)
    ExtraTraitTerm,  # (trait, weight) a caller adds to one roll (#4450)
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
| `rank_difference` | `int` | Whole rank difference of the chart the roll used (#4601: the floor of the fractional difference) |
| `trait_points` | `int` | Points from weighted traits |
| `aspect_bonus` | `int` | Bonus from path aspects |
| `specialization_points` | `int` | Points from owned specializations (default 0, #1688) |
| `capability_points` | `int` | Weighted authored `CheckTypeCapabilityModifier` points (default 0, #2505) |
| `total_points` | `int` | trait_points + specialization_points + aspect_bonus + capability_points + extra_modifiers |
| `standing` | `CheckStanding \| None` | #4601: both sides' band positions and the slid chart the roll used. None on hand-built results |

### CheckResult Properties

```python
result.outcome_name   # str: outcome name or "Unknown"
result.success_level  # int: outcome success_level or 0
result.chart_name     # str: chart name or "No Chart Found"
result.rank_text      # str: "Expert (rank 3), 67% toward Master (rank 4)" (#4601)
result.target_rank_text  # str: the target's rank with number and band position
result.standing_text  # str: "<roller> against <target>", each with band position
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

### Modifier value table, level baselines and the taper (#4594, ADR-4594-A)

Staff-tuned rows, all keyed by a `ModifierLane` column (`check`, and `stat` since #4726) so later
lanes add rows, not models. Models live in `modifier_models.py`, readers in `modifier_values.py`, admin
pages in `admin.py`. Example values are in `world/seeds/modifier_values.py` (cluster
`modifier_values`); an empty table leaves behavior unchanged.

| Model | Purpose | Key fields |
|-------|---------|------------|
| `ModifierValue` | The value table: what a modifier of `size` is worth at `level`, in the lane's units. Sparse rows read as steps (highest authored level at or below the modifier's). A magnitude; the authored modifier keeps its sign | `lane`, `level`, `size` (`ModifierSize`), `value`; unique (`lane`, `level`, `size`) |
| `ModifierLevelBaseline` | The typical total at each level in a lane; the value admin and the tuning dashboard read a value as a share of it and of its rank band | `lane`, `level`, `baseline`; unique (`lane`, `level`) |
| `ModifierTaper` | Which source kinds taper in a lane: each further modifier of the kind counts `ratio` of the one before, never below `floor` | `lane`, `source_kind` (`ModifierSourceKind`), `ratio`, `floor`; unique (`lane`, `source_kind`) |

Readers (`modifier_values.py`): `load_value_table(lane) -> ValueTable` (one query;
`ValueTable.value(level, size) -> int | None`), `load_taper_rules(lane) -> dict[str, TaperRule]`
(one query), `level_baseline(level, lane) -> int | None`, `rank_band_share(points, at_total) ->
Decimal | None` (points as a share of the `CheckRank` band `at_total` sits in).

`ModifierContribution` carries `level`, `size` and `vow_part` (the untapered vow share: the
equipment walk's vow terms, #4628, and a vowed caster's size step on a buff, #4747). `ModifierBreakdown(contributions, tapers)` counts each tapered kind's
bonuses and penalties as separate piles, largest first, the k-th at `TaperRule.weight(k-1) =
max(ratio**(k-1), floor)` of `value - vow_part`; `counted()` lists what each contribution counts
for, and `total` / `extra_modifiers_total` round once, half up. `counted_values()` gives whole numbers
summing exactly to `total` (largest remainder); `record_consequence_outcome` stores those as each
`ConsequenceOutcomeModifier.value`, so the recorded rows add up to `modifier_total`. `collect_check_modifiers` loads
the check lane's taper rules into every breakdown it returns, and
`opponent_condition_opposition` tapers an opponent's own CONDITION pile the same way. The first
sized source is a technique buff (see `docs/systems/conditions.md` and `docs/systems/magic.md`).
`ValueTable.signed_value(authored_value, level, size) -> int | None` is the shared valuation every
sized source calls: the row's magnitude with the authored value's sign, or None (keep the flat
value) when the level, the size, the authored value or the row is missing.

**Worn items (#4628, ADR-4628-A).** The EQUIPMENT block is the second sized source. Each worn
`ItemCheckModifier` row is annotated with `item_level`, the highest `QualityTier.modifier_level`
among the instances of its template that let it count (equipped, and attuned when the template
requires it; the annotation shares the filter's join, so a carried spare never counts). A row with
a `modifier_size` and a level reads the value table; any other row keeps its flat value. Either
way the contribution carries `level`/`size` when sized and tapers with the EQUIPMENT pile. What the
EQUIPMENT kind covers on the check lane:

| Item path | Contribution | This slice |
|---|---|---|
| `ItemCheckModifier` (template check bonus) | `Equipped: <template>`, one per template | Sized: level from quality, value table, tapers |
| Crafted recipe modifiers and accents (`crafted_modifier_by_piece`) | `Crafted: <piece>`, one per worn piece | Flat (deferred: a generic `ModifierTarget` source, read by every lane through `get_modifier_total`), tapers per piece |
| Equipment walk (`equipment_walk_parts`): facet, facet crossing, mantle, mantle crossing, motif style | `Equipment & attunement` | Flat (deferred: thread passives scaled by thread level), tapers |
| Equipment walk: covenant role, covenant level, vow stat scaling | same contribution, as its `vow_part` | Never tapered (the character's vow) |
| Fashion (`fashion_outfit_bonus`) | `Fashion`, its own FASHION kind | Unchanged (flat, its own pile) |

The walk only reaches a check whose scoped `ModifierTarget` is in an
`EQUIPMENT_RELEVANT_CATEGORIES` category; the check-scoped targets authored today (category
`check` or `roll_modifier`) are not, so on those checks the walk adds nothing.

**Distinctions and scene surroundings (#4638, ADR-4638-A).** The third and fourth sized sources.

- *Distinctions.* `DistinctionEffect.modifier_size` is authored on the distinction's effect
  inline (Paramount refused). The CHARACTER block calls
  `get_modifier_breakdown(sheet, scoped_target, value_lane=ModifierLane.CHECK)`; a distinction
  row whose effect has a size reads the value table at the holder's `CharacterSheet.current_level`
  and the size its held rank names, signed like the effect's rank-1 value
  (`ValueTable.signed_value`). Rank steps the size and never multiplies the number (#4660,
  ADR-4660-A, superseding ADR-4638-A's rank ratio): `DistinctionEffect.size_at_rank` takes the
  highest authored `DistinctionEffectRankSize` at or below the held rank, else `modifier_size`
  (the rank-1 size), so a sized effect with no rank rows is worth the same at every rank, and
  `value_per_rank`/`scaling_values` scale only unsized effects. The breakdown query prefetches
  the rank rows into `DistinctionEffect.cached_rank_sizes`. Amplification
  (`amplifies_sources_by`) and immunity then apply to the table number exactly as they did to the
  flat one. The detail row, and so the contribution, carries `level`/`size` (the stepped size)
  only when the table priced it. No class level (level 0),
  no value row or no size keeps the flat `CharacterModifier.value`. The stat read passes the
  stat lane (see "The stat lane" below); every other caller of `get_modifier_breakdown` (power,
  soak, levers) passes no lane and reads flat values.
- *Source kind.* Distinction rows stay in the CHARACTER kind and taper in its pile with the other
  `CharacterModifier` rows that can reach a check-scoped target: achievement rewards
  (`ModifierSource.achievement_reward`) and form combat profiles (`form_combat_profile`), both
  flat. Residence comfort targets only the AP-regen targets and never reaches a check.
- *Scene surroundings.* `SceneCheckModifier.modifier_level` and `modifier_size` are authored
  together on the scene admin's surroundings inline (`SceneCheckModifierInline`; a level without
  a size, or the reverse, and Paramount are refused). `_scene_check_contributions` values a
  sized row at its own level, never the roller's; an unsized row keeps its flat value. The SCENE
  pile tapers, though one scene holds at most one row per check type.

**A vowed caster's size step (#4747, ADR-4747-A).** A sized condition instance whose
`modifier_vow_level` (L) and `modifier_vow_tenths` are set (stamped at cast, see
`docs/systems/magic.md`) adds, to each of its modifiers, (value(L, size + 1) minus
value(L, size)) x tenths / 10, rounded half up (`checks.types.round_half_up`) and signed like
the authored modifier, so a debuff's step is a further penalty and lands in the penalty pile.
Only the one-size-up shape is code; the values, the level and the tenths (the vow's
`CovenantRoleTechniqueSpecialty.multiplier_tenths`) are all data. The step is the
contribution's `vow_part` and is never tapered; the buff's own value (at `modifier_level`) still
tapers in its pile. L is the caster's vow thread shown level, never capped by the buff's own
level. No table row for either size means no step. Paramount is reachable only this way. One
helper prices it, `conditions.services._priced_sized_modifier` -> (value, vow_part), shared by
the check lane (`_check_modifier_for_target`, `condition_contributions`), the opponent path
(`opponent_condition_opposition`) and the stat lane (`condition_target_contributions`); it reads
stored columns only, so no read gains a query. Points only: the step adds no outcome floor or
ceiling and never touches `_apply_outcome_guarantees`.

### The stat lane (#4726, ADR-4726-A)

A modifier on a stat target (a `ModifierTarget` whose `target_trait` is a STAT trait) is valued
and tapered in the `stat` lane, in internal stat units (stats are stored x10, so 10 is one shown
point). The lane applies wherever a stat is read: the change is in
`TraitHandler._get_stat_modifier`, so checks (inside trait points), fatigue capacity, stamina's
health term, carrying capacity and scandal all read the same buffed number. The web sheet
shows the stored, unbuffed stats (`_build_stats` in `world/character_sheets/serializers.py`).

- **Contributions.** The stat read builds the stat target's CHARACTER and EQUIPMENT
  contributions with `modifier_target_contributions(sheet, target, lane=ModifierLane.STAT)`
  (`services.py`), the same builder the check seam calls with the check lane (fashion stays in
  the check seam only), and its CONDITION contributions with
  `world.conditions.services.condition_target_contributions(sheet, target, lane=...)`: one per
  matching `ConditionModifierEffect`. A sized condition instance (`modifier_level` and
  `modifier_size` set by the applying cast) reads the stat lane's table and is not scaled again
  by severity or stage; an unsized one keeps `scaled_condition_effect_value`. A sized
  distinction effect on a stat reads the table at its holder's level and held-rank size.
  `get_condition_modifier_total` keeps its flat sum for its other callers.
- **The taper.** The total is a checks `ModifierBreakdown` with `load_taper_rules(ModifierLane.STAT)`:
  CONDITION, CHARACTER and EQUIPMENT piles, bonuses and penalties apart, the walk's vow terms
  untapered as `vow_part`. No stat-lane rows means a plain sum, as before.
- **Hot path (#552).** The value table loads only when a source is sized, and the taper rules
  only when some kind has two or more contributions, so a stat read with nothing sized and no
  pile runs exactly the queries it ran before.
- **Separate piles.** A check reads the buffed stat through its trait points; the stat lane's
  piles and the check lane's piles never share a contribution, so nothing tapers twice.
- **Seed.** `world/seeds/modifier_values.py` adds stat-lane rows. Under the seeded STAT
  `PointConversionRange` (1 point per stored unit across 1-100), a stat buff of N units moves a
  weight-1 check by N points, so the stat lane's values equal the check lane's for each size and
  level (`world/seeds/tests/test_stat_lane_universality.py` holds the relation). The taper is the
  check lane's ratio and floor for the three kinds a stat read gathers.
- **Admin.** A technique whose sized condition changes only a stat no longer gets the "changes
  no check" size warning (`applied_condition_size_warnings`); the warning now reads "changes no
  check or stat".

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

### extra_traits (skills added to one roll, #4450, ADR-4450)

A caller can add skills to a single roll without a check type for the combination:

```python
from world.checks.types import ExtraTraitTerm

result = perform_check(
    character, check_type, target_difficulty=10,
    extra_traits=(ExtraTraitTerm(trait=skill.trait, weight=Decimal("1.00")),),
)
```

`extra_traits` is keyword-only with an empty default (every existing roll is unchanged) on
`perform_check`, `perform_check_with_modifiers`, `select_consequence`, `compute_check_rating`,
`preview_check_difficulty` and `collect_check_modifiers`.

- Each term scores like a `CheckTypeTrait` row: the character's value times `weight`, through the
  skill conversion table. A trait that is on the check type and also a term, or in two terms,
  scores once per occurrence.
- Development: with an `effort_level`, each trait the roll used earns check-based development once
  per roll, however many times it scored.
- Context: the terms' trait ids join the `involved_traits` that capability scoring and TRAIT
  thread matching see.
- A paused (GATED) action pipeline keeps its terms on `PendingActionResolution.extra_traits`.
- Magic is the first caller: see `docs/systems/magic.md` ("Magical skills").

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

`social_target_difficulty` (`world/checks/social_target.py`, #4145) is the one difficulty
function for a character acting socially on a character. It returns a `SocialDifficulty`
(difficulty, actor-side contributions, eased bands), not an int. Scene social actions call
it too (`_graded_scene_difficulty`, passing the defender's increment, which keeps a PC's
resist-effort development award and fatigue at the scene call sites; relationship-gated
Allure stays at scenes' check-modifier time, `perceiver_sheet` is not passed there, and
combat and standoffs do not apply it yet). Combat's
`_social_combat_difficulty` (`world/combat/services/`, backing Demoralize/Taunt/Parley)
and the standoff verbs call it with `level_override`, because a `CombatOpponent`'s authored
`level` isn't reachable through its `objectdb`'s class-level rows (an ephemeral NPC has
none). Without the override, a boss's morale defense always floored at level 1 even though
the same opponent's offense already opposed PC checks at its real level via
`level_opposition`.

**`award_development` (#3066).** `compute_resist_increment` never rolls (ADR-0019
keeps the one dice roll inside `perform_check`/`resolve_challenge`), so it can't
thread `effort_level` into a `perform_check` call the way combat/scene offense
checks do. `award_development: bool = False` opts a call site into awarding the
defender Composure development points directly via the same
`_award_check_development` chokepoint `perform_check` uses internally — #3039's
intent covers both sides of an opposed check. Only the two scene call sites that
charge the defender real resist fatigue for a player-*declared* effort
(`_compute_difficulty_override_for_primary` / `_compute_target_difficulty_override`
in `world/scenes/action_services.py`) pass `True`. Combat, standoffs and the scenes' NPC
passive resist (`_npc_passive_resist_increment`) do not. Their `"medium"` effort is a hardcoded passive-resistance band standing in
for an undeclared resistance, not a real choice, so awarding dp there would be phantom
accrual for an opponent (sometimes a persona-backed PC mirror) or an NPC who spent
nothing.

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
   For each CheckTypeTrait, then each extra_traits term (#4450):
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
   # Counted ONCE (#4453): the roll path owns the points. The aggregator's CAPABILITY
   # contributions are provenance; callers that feed a ModifierBreakdown into
   # extra_modifiers (perform_check_with_modifiers and every direct caller) use
   # ModifierBreakdown.extra_modifiers_total, which excludes CAPABILITY. `.total` is the
   # full recorded shift (provenance), never a roll input.

3. Total = trait_points + specialization_points + aspect_bonus + level_points + capability_points
   + extra_modifiers
   (perform_check_with_modifiers' extra_modifiers is the breakdown's tapered
   extra_modifiers_total, #4594: a pile of one kind counts each extra at 7/8 of the
   previous, never below 2/3, when ModifierTaper rows exist)

4. Band positions and the slide (#4601, world/checks/slide.py resolve_standing):
   each total -> its CheckRank and band position (rank number + share of the band)
   difference = roller position - target position (fractional)
   chart = floor(difference), slid by the remainder toward the next chart
   (both totals count every point, modifiers included; #4723 removed the hopeless pin)

5. The slid chart: each "at least X" chance of the chart's own outcomes moves toward the
   next chart's (its extra outcomes counted as the nearest outcome this chart has)

6. Roll 1-100 (random.randint), plus a fraction inside the face (random.random)
   rollmod = get_rollmod(character)
   effective_roll = clamp(roll + rollmod, 1, 100)
   position = effective_roll - fraction  (an unslid chart reads only the face)

7. The slid chart's band at that position -> CheckOutcome; outcome guarantees after,
   capped at the chart's best outcome

8. Return CheckResult dataclass
```

---

### Resisted rolls: an NPC acts on a PC (#4418, ADR-4418)

When a story NPC uses a contested social template on a player character, the NPC does not
roll. The PC rolls `ActionTemplate.resist_check_type` (a second nullable `CheckType` FK
beside `check_type`) through the same `perform_check` pipeline above:

- **Difficulty.** `scenes.action_services._resisted_difficulty` is
  `compute_check_rating(npc_character, template.check_type)` plus
  `DIFFICULTY_BAND_STEP * template.difficulty_tier_modifier`: the NPC's own rating in the
  action, passed as the PC's difficulty override.
- **Outcome.** `checks.services.mirrored_outcome(outcome)` reads the PC's `CheckOutcome` from
  the NPC's side: the row whose `success_level` is the negation, else the nearest row on the
  same side of zero (milder on a tie); a zero outcome mirrors to itself. The mirrored outcome
  only selects the template's consequence pool; the resolution wheel shows the PC's own
  roll.
- **Content.** A single-target social template with no `resist_check_type` (or no consent
  category) is refused as an NPC action on a PC and listed on the Required content
  dashboard as `npc-resist-checks` (`web/admin/tuning/required_content.py`).

The flow around it (consent, resist-only, effort) is in `docs/systems/scenes.md`.

## Result charts (#2707, #4593)

`ResultChart` rows are keyed by rank difference (`roller_rank - target_rank`, ADR-0165).
Fifteen are seeded, -8 to +6 (`world/seeds/checks.py`); the roll (1 to 100) lands on a
`ResultChartOutcome` band. A difference with no row snaps to the closest chart, so
anything below -8 resolves to chart -8 (there is no clamp).

- **Monotonic.** Every "at least X" chance (Partial Success or better, Success or
  better, and so on) is non-decreasing as the rank difference rises. Data migration
  `0284` made the smallest repair to production, moving only the Failure / Partial
  Success boundary on charts -4 and -2, so Partial Success or better is 55% on every
  chart from -5 to -1.
- **Chip charts.** -6 keeps 1% Success and -5 keeps 5% (#2707).
- **Impossible zone.** Chart -7 (placeholder name "Failure -7"; Critical Failure, Failure
  and a small Partial Success) and chart -8 ("Impossible"; failures only) have no Success
  (1). The odds are example rows for the owner to tune. `chart_has_success_outcomes` is
  False there, `difficulty_indicator_for_rank_difference` returns `IMPOSSIBLE`, and the
  approach is listed to the player labelled Impossible, not dropped from the
  available-actions lists (`world/mechanics/services.py`).
- **Guard.** `world/checks/tests/test_chart_direction.py` (`ImpossibleChartTests`) fails
  if any "at least X" chance falls between neighbouring charts, if an impossible chart sits
  above a winnable one, or if a difference below -8 stops resolving to chart -8.

## The slide (#4601, ADR-4601-A; the pin removed by #4723, ADR-4723-A)

`world/checks/slide.py` is the one implementation; `perform_check`,
`preview_check_difficulty`, the outcome wheel and the tuning dashboard all read it.

- **Band position** (`band_position(points)`): the rank a total reaches and how far it is
  through that rank's band, from the `CheckRank` rows. 40 points is "Competent (rank 2),
  60% toward Expert (rank 3)". The top rank has no next rank (share 0); a total below
  every threshold has no rank and counts as rank number 0, as before.
- **Fractional difference.** Roller position minus target position. The whole part picks
  the chart; the remainder is how far it slides toward the next.
- **The slide** (`slide_chart`): each "at least X" chance of the chart's own outcomes moves
  in a straight line toward the next chart's. An outcome the next chart has and this one
  lacks counts as this chart's nearest outcome by success level (the lower on a tie), so
  no outcome appears early: on chart -1 at 50%, Success or better is 31% (22% sliding
  toward 40%) and Critical Success stays 0% until difference 0. A difference below the
  lowest chart sits at 0% of it; one at or above the highest chart is unslid.
- **One roll.** The d100 face (with rollmod, clamped 1 to 100 as before) plus a fraction
  inside the face. Unslid, every face lands where it always did; slid, every point of a
  modifier moves the odds.
- **No pin (#4723, ADR-4723-A).** The chart comes from both sides' full totals,
  modifiers included, so a big enough buff or pile of buffs lifts a check off charts -7
  and -8 like any other. Buffs that stay short of the next rank leave the roll on its
  chart, and the slide never shows an outcome that chart lacks, so a check on an
  impossible chart has no Success outcome until its total reaches a chart that has one.
  `preview_check_difficulty` grades the same full total, so an approach is listed
  Impossible only while its current total lands on a chart with no Success (1).
- **Guarantees capped.** `_lowest_outcome_at_or_above` returns the chart's best outcome when
  the chart has nothing at the floor (a Success floor on chart -7 gives Partial Success);
  the global outcome table is only the fallback when there is no chart.
- **Result text.** `CheckResult.rank_text` / `standing_text`. The roller's scene check
  message ends "Your standing: ... against ..."; the mission invocation breakdown shows
  both ranks the same way. The room's narration stays number-free.
- **Guard.** `world/checks/tests/test_slide.py` checks that, across every chart in quarter
  steps, no "at least X" chance falls, and that a slide at 0% reproduces the authored chart.
  The journey is `integration_tests/test_every_point_counts_journeys.py`.

Slices (c) and (d) of #4551 (unified modifiers with a taper, the vow size shift) build on
this.

## Resolution theater

`world/checks/theater.py` (#924, extended #3807 Part B) is the dramatic-reveal seam: a
roulette-style wheel pushed to a player's client, sized to feel more dangerous than the
resolved outcome necessarily was. It fires only when the pool is wheel-worthy, and it
never breaks resolution: `maybe_emit_resolution_theater` catches every exception around
delivery and returns `False` rather than raise, since the wheel is garnish and the
outcome underneath it is the meal.

**Existing triggers (pre-#3807):** consequence selection whose tier pool carries a
`character_loss` or an authored `theater`-flagged `Consequence` (`should_emit_theater`),
and mission draws. Both build their faces from the resolved tier's own consequence pool
via `build_roulette_payload` and fire only for the roller.

**Social-check trigger (#3807 Part B):** `_schedule_check_outcome_theater`
(`world/scenes/action_services.py`) schedules a success-level wheel for every resolved
social check, inside `_create_result_interaction`'s `transaction.on_commit` callback so a
rolled-back resolution never spins one. It emits to the roller always, and to the
effective target when the action has one; bystanders never receive it. For action-template
steps with at least two effective consequences, it queues a second wheel immediately after
the chart wheel using authored effective weights; the backend-selected consequence is the
landed face and no client-side selection occurs.

**`check_outcome_faces(check_result)`** (`world/checks/theater.py`) builds the wheel's
faces straight off the check's own `ResultChart` bands, one unsaved `Consequence` per
`ResultChartOutcome` row, weighted by that row's roll-range width, selecting whichever
face matches the check's actual resolved outcome.

**The slide (#4601):** when the roll used a slid chart (`check_result.standing.share >
0`), the faces are the slid chart's bands, weighted in tenths of a face. The slid chart is
built only from the two authored charts and the band positions, so it is the chart the dice
actually faced; the rule below still holds.

**HARD RULE:** faces are read only from the chart's authored bands (or the slid chart built
from them). `check_outcome_faces`
never reads `get_rollmod()`, `effective_roll`, or any outcome-guarantee logic
(`perform_check` step 7 above, ADR-0152): the wheel always shows the raw chart and lands
on whatever actually resolved, never a rollmod-shaped or guarantee-shaped view of the
odds. When the resolved outcome isn't one of the chart's own bands (an outcome guarantee
lifted it off-chart), a weight-1 face for that outcome is appended and selected, so the
wheel still has a face to land on without silently reshaping the real bands. See
ADR-0297.

**Frontend:** the wheel renders as a flat proportional disc (Part C), replacing the
earlier equal-slice prism wheel; slice angles are proportional to each face's `weight`.

**Action-template persistence (#3823):** selected template consequences are recorded in
`ConsequenceOutcome` with `action_interaction` provenance and its partition timestamp. The
existing API exposes the action source id and includes it in scene-scoped visibility. A tier
with one effective consequence is applied directly without a second wheel.

**A deleted pose keeps its outcome (#4464):** a writer may delete their own pose within
`DELETION_WINDOW_DAYS` (`scenes.interaction_services.delete_interaction`). Both Interaction
FKs are `SET_NULL`, so the outcome survives with a null link, and
`consequence_outcome_exactly_one_source` keys the source kind on the
`combat_interaction_timestamp` / `action_interaction_timestamp` companions, which stay. A
second check, `consequence_outcome_interaction_has_timestamp`, requires a timestamp
whenever an Interaction FK is set. Readers that need the source kind read the timestamp, not
the FK.

## Internal Service Functions

```python
# These are private (_prefixed) and called by perform_check internally:

# Calculate weighted trait points from CheckTypeTrait entries
_calculate_trait_points(handler, check_type, *, stat_override=None, extra_traits=()) -> int

# Calculate aspect bonus from character's most recent path
_calculate_aspect_bonus(character, check_type, level) -> int

# Calculate weighted capability points from authored CheckTypeCapabilityModifier rows (#2505)
# 0 with no authored rows (curated gate, never calls the capability oracle) or no sheet_data
_calculate_capability_points(character, check_type, *, extra_traits=()) -> int

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
- **Trial effects and save rules (#4501, spec #4343).** `GRANT_CODEX` with `grants_known` calls `grant_codex_entry` (KNOWN, not a lead); `TECHNIQUE_TRAINING` (`technique`, `training_points`, `training_meter_size`, `grants_technique_outright`) trains or grants a technique; `MAGICAL_SCARS` with `scar_is_cosmetic` queues a reward scar. `Consequence.deliberately_free` + `free_reason` lift the cost rule on purpose. The rules live in `world/checks/trial_rules.py`: `effect_trial_errors` (run by `ConsequenceEffect.clean`: known only at Success+, no technique-gating entry or training on a Failure, outright only at Critical Success, no ultimate, a cosmetic scar only at Success+) and `consequence_trial_errors` / `Consequence.trial_rule_errors` (the whole set: a consequence that opens a technique carries a real cost - a non-cosmetic scar or a condition on the actor - unless deliberately free; training runs after the known-grant). The Consequence page's effect inline (`ConsequenceEffectFormSet`) runs the set rule; the Trial builder (slice 2) reuses it.
- **Trial builder (#4513).** `web/admin/trial_builder/` edits a mission option's whole trial on one page and asks `effect_trial_errors` / `Consequence.trial_rule_errors` over unsaved copies, so the page and the stock admin refuse the same things. `MAGICAL_SCARS` no longer requires `condition_template` (not read by its handler).
- `ConsequenceEffectAdmin` (#4473) - one effect on its own page (the Consequence page lists effects inline and links here). A `LEGEND_AWARD` effect names the organizations the act harmed or helped through the `NamedOrganization` inline (organization, role, base amount, "only if exposed", a staff-only estimate). The `_legend_award` handler sizes each row's base by `_tier_multiplier` of the outcome tier and passes the reactions to `create_legend_event(named_reactions=...)`; see `docs/systems/societies.md`.

---

## Design Principles

- **No check persistence** -- results are transient, consumed by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals, magic, combat, and conditions compute their own `extra_modifiers` before calling `perform_check`
- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect, CheckTypeCapabilityModifier)
- **No API endpoints** -- check types are staff-defined via admin; resolution is called programmatically by other systems
- **Outcome tiers carry verdicts** (#4378) -- code reads `CheckOutcome.success_level` (`> 0` succeeded, `< 0` failed), never the name. The five canonical tiers and their levels live in `CANONICAL_OUTCOME_LEVELS` (`world.traits.constants`); seed code gets a tier from `ensure_canonical_check_outcome` / `ensure_check_outcome` (`world.traits.services`), which creates a missing row at the right level and corrects a drifted one. Never `CheckOutcomeFactory` outside tests: its `success_level` is random, and `tools/lint_seed_factory.py` (`seed-factory` hook) rejects it.

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
- **Mechanics app**: `resolve_challenge()` gathers the character's modifiers with
  `collect_check_modifiers` (the active scene at the challenge's location) once, BEFORE the roll
  (#4629), and rolls `perform_check()` with `extra_modifiers = caller bonus + capability_source.value +
  breakdown.extra_modifiers_total`. Each term counts once:
  the capability source's value (a `CapabilitySource`, e.g. from a technique; ADR-0145's narrower channel)
  is added there, authored `CheckTypeCapabilityModifier` points are added by `perform_check` itself, and
  both appear in the breakdown only as CAPABILITY rows, which `extra_modifiers_total` leaves out. Once-only
  conditions that helped are spent. `_record_challenge_outcome` stores THAT breakdown on the
  `ConsequenceOutcome` (the capability source as a "<capability>: <source>" CAPABILITY row); it no longer
  rebuilds one after the roll, which had stored worn items, buffs and conditions the roll never counted.
  The action-template path (`_resolve_via_template`) feeds the same inputs to the template's main check
  through `start_action_resolution` (gates roll without them), where it had dropped the capability value
  and the caller's bonus; a gate-only resolution stores no modifier rows. A technique source also adds
  that technique's skill as `extra_traits` (#4450), on the direct roll and the action-template path alike.
  The caller's own bonus (the bond bonus on Interpose and Succor) moves the roll but has no stored row.

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
- **The target's own modifiers** (#4629): the roll goes through `perform_check_with_modifiers` with the
  target's active scene, so the target's worn items, buffs, conditions and distinctions count as on any
  other check. They are the character's, not a GM-chosen number, so Decision 3 of #2118 (no integer
  passthrough) is untouched; the band step stays the GM's only lever.
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

**Catalog resolve/find/band-validation core (#3295):** the check-ref resolution,
catalog search/listing, and band validation this action uses were extracted into
`world.checks.catalog_invocation` — `resolve_check_type_ref`/`search_catalog`/
`render_catalog_listing`/`resolve_band`/`catalog_queryset` — so every catalog-check
invocation surface (this SENIOR ad-hoc action, and the player/GM scene surfaces
below) resolves against the exact same code, never a parallel reimplementation.
`InvokeCatalogCheckAction` itself was unchanged behaviorally by that extraction: same
messages, same gate, same result shape.

---

## Scene Check Invocation (#3295)

**Ruling (Tehom, 2026-08-21):** players roll checks at their own discretion, and
GMs call for checks — but every check anyone rolls is an authored `CheckType` at a
`DifficultyChoice` band, never a freeform stat/skill/difficulty invention (the
same #2118 firewall, restated). When the catalog lacks a fitting check, the answer
is a proposal, never an on-the-spot invention.

Three loops, all thin `action.run()` dispatchers over the shared
`world.checks.catalog_invocation` core (`actions/definitions/scene_checks.py`):

- **`SceneSelfCheckAction`** (registry key `scene_self_check`) — any player,
  SELF-target only. Resolves `check_type_ref` against the catalog scoped to the
  actor's own `CharacterSheet` (`catalog_queryset(owner_sheet=actor_sheet)` — sees
  staff-authored rows plus the actor's own synthesized magic `CheckType`, never
  another character's), rolls it through `perform_check_with_modifiers` with the
  room's active scene (#4629: worn items, buffs, conditions, distinctions and scene
  modifiers count; a Call on favor's bonus rides as `extra_modifiers`), and broadcasts a
  Narrator-style OUTCOME line to the room via `world.scenes.interaction_services
  .record_interaction` + `render_challenge_outcome_narration` — the roller's own
  currently-presenting persona names the roll (never the raw character key; the
  #981 alt-leak rule, since OUTCOME-mode interactions render with no
  payload-persona name of their own).
- **`CallForCheckAction`** (`call_for_check`) — JUNIOR+ GM
  (`MinimumGMLevelPrerequisite`), staff-authored catalog only (no `owner_sheet`
  scoping — a GM cannot call for a target's private synthesized check). Requires
  an active scene at the GM's location; creates one `CheckCall` row plus one
  `CheckCallTarget` row per named target, and broadcasts the call itself to the
  room. Never rolls anything.
- **`AnswerCheckCallAction`/`DeclineCheckCallAction`** (`answer_check_call`/
  `decline_check_call`) — a named target's own one-tap response. Answering
  dispatches the SAME self-check core, bound to the call's own `check_type`/
  `band` (the target never picks their own) and marks the `CheckCallTarget` row
  `ANSWERED`. Declining marks it `DECLINED` quietly (no broadcast) — "declining =
  not rolling, no mechanical force." Both refuse if the row isn't `PENDING`
  (already answered/declined, or not this actor's call to answer).

**Models** (`world/checks/models.py`): `CheckCall` (scene FK, `caller_persona`,
`check_type`, `band`) and `CheckCallTarget` (`call` FK, `target_sheet`, `status`
— `CheckCallTargetStatus.PENDING`/`ANSWERED`/`DECLINED`, `unique_together =
["call", "target_sheet"]`). Row existence is the pending prompt; expiry/timeout
polish is an explicitly deferred follow-up.

**Proposal pipeline** (Decision 4 — never auto-creates a catalog row):
`ProposeCheckAction` (`propose_check_type`) routes a structured `CheckProposal`
(`world.player_submissions.models` — `proposed_name`/`intent`/
`suggested_traits_text`/`situation_text`, no JSON) to the staff inbox via
`world.player_submissions.services.submit_check_proposal`
(`SubmissionCategory.CHECK_PROPOSAL`). Staff resolve it
(`CheckProposalViewSet`, `PATCH /api/player-submissions/check-proposals/<id>/`)
with `review_notes`; adoption itself — authoring the real `CheckType` row — is a
separate, manual act through the normal content path.

**Telnet** (`commands/scene_checks.py`): `check` / `check find <term>` (catalog
browse, scoped to the caller's own sheet) / `check <name> [at <band>]` (self-check
— an omitted band defaults to `normal` at the telnet layer only, never inside the
Action) / `check propose <name>=<intent>` / `check answer <call-id>` / `check
decline <call-id>`; `callcheck <name>=<target1>,<target2> [at <band>]` (GM call).

**Web:** `SelfCheckPanel` + `CheckCallPromptCard`
(`frontend/src/scenes/components/`), mounted on the scene detail page for any
active-scene participant; a `Call For Check` tab on `GMAdjudicationPanel` for
GMs. Reads go through `PlayerCheckTypeViewSet`
(`GET /api/checks/player-check-types/`, any authenticated player — unlike the
GM-only `CheckTypeViewSet`) and `CheckCallTargetViewSet`
(`GET /api/checks/check-call-targets/`, the requesting player's own pending
prompts). All mutations dispatch through the generic REGISTRY action-dispatch
seam (`useDispatchPlayerAction`), never a bespoke POST endpoint.

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
- **Discovery** rides one service, `find_situations` (`world/gm/services.py`),
  behind two faces: telnet `setsituation find <term>` (`FindSituationAction`,
  which now only formats the result) and `GET /api/gm/discovery/?q=&risk=`
  (#3564) for the web GM panel and beat-authoring form. Kinds come from
  `SituationKind.objects.cached_all()` filtered server-side to the caller's GM
  tier (staff bypass); `ChallengeTemplate` and `SituationTemplate` are only
  searched once the query is non-empty, each capped at
  `FIND_RESULT_LIMIT = 15`. An empty query is a kind-first cold open: every
  kind within the caller's breadth, no templates or challenges (telnet's own
  empty-query listing changed to match, so it is not a regression). The web
  finder (`SituationFinder.tsx`, `frontend/src/gm-adjudication/`) surfaces the
  same kind cards, fits and difficulty guides, with pool guidance always
  marked advisory, in three hosts: beat-prep's staged-templates editor
  (`BeatFormDialog.tsx`), the scene panel's Situation tab (one-click Stage or
  Place), and its Call Check tab (a fitting check pre-fills the difficulty
  band from the running beat's risk), each behind a "Browse the catalog"
  toggle. A "Suggest an entry" dialog dispatches `gm_submit_catalog_suggestion`
  from the finder when a character is active.
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
| `magic` | cast/ritual checks | a stat only (willpower, presence or stability); the Magic skills are added at roll time from the magic skill settings (#4547) |
| `investigation` (#1705) | `Search` | perception + Investigation |
| `governance` (#930) | Tax/Investment checks | stat + Scholarship/Economics |
| `stealth` (#1464) | `Stealth` | agility + Stealth |
| `security` (#2180, #2757) | `Athletics` | Athletics (skill) + situational stat (default: strength; `resolve_security_check` passes `stat_override` from `SecurityCheckKind`) |
| `security` | `Lockpick` / `Guard Detection` | wits+Skulduggery / perception+Investigation |

**Resist checks** (Reflexes, Escalation Pace, Endurance, Mortal Resolve) are the tenet-permitted single-stat exception — they seed exactly one `CheckTypeTrait`. The `Melee Combat` skill catalog (with weapon-class specializations local to the `combat_checks` seed) is seeded by the `combat_checks` cluster; the penetration/flee retrofits depend on it.

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
