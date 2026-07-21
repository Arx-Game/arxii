# Checks - Check Resolution System

Database-defined check types with weighted trait and aspect composition, resolved through the rank/chart/outcome pipeline.

## Purpose

The checks app defines types of checks (Stealth, Diplomacy, Perception, etc.) and resolves them. Each check type specifies which traits contribute and at what weight, plus which aspects (from the classes system) are relevant. At resolution time, trait points + path-based aspect bonuses + caller-provided modifiers flow through the existing PointConversionRange/CheckRank/ResultChart pipeline.

**Composition guideline (design tenet).** A `CheckType` defaults to **stat + the relevant skill**, plus a **specialization when the character owns one** (e.g. Charm + Persuasion + Seduction). **stat + stat is the rare exception, not the default** — character identity (trained skill, owned specialization) should almost always matter to the roll. Specializations compose as parent-skill + specialization and **cannot participate in a check until the #1688 foundation lands** (`CheckTypeTrait` only references `Trait` today; `Specialization` has no Trait). Auto-scaffolded stat+stat seeds (the social `CheckType`s) are PLACEHOLDER pending a real composition pass. See `docs/roadmap/design-tenets.md` → "Checks are stat + skill (+ specialization)".

## Key Files

### `models.py`
- **`CheckCategory`**: Groups check types (Social, Combat, Exploration, Magic). SharedMemoryModel.
- **`CheckType`**: Named check definition with trait weights and aspect weights. SharedMemoryModel.
- **`CheckTypeTrait`**: Links CheckType to Trait with a weight multiplier. SharedMemoryModel.
- **`CheckTypeAspect`**: Links CheckType to Aspect (from classes app) with a weight multiplier. SharedMemoryModel.
- **`CheckTypeSpecialization`** (#1688): Links CheckType to a `skills.Specialization` with a weight — the third leg of stat + skill + specialization. The parent skill rides a `CheckTypeTrait` (a skill is Trait-backed); this folds in the owned specialization (0 when unowned). Social-check compositions are seeded in `world/seeds/social_checks.py` (authoritative). SharedMemoryModel.
- **`CheckTypeCapabilityModifier`** (#2505): Links CheckType to a `conditions.CapabilityType` with a weight — curated gate: only an authored (check_type, capability) pair can ever move points, however large the character's raw capability value. Per-row contribution is `weight * get_effective_capability_value(sheet, capability)` (the agency oracle in `world.conditions.services`), summed and truncated toward zero once. `related_name="capability_modifiers"` on CheckType. SharedMemoryModel.

### `services.py`
- **`perform_check(character, check_type, target_difficulty, extra_modifiers)`**: Main resolution function. Returns CheckResult.
- **`get_rollmod(character)`**: Public function that sums character and account rollmod values. Used by both checks and attempts apps.

### `consequence_resolution.py`
- **`select_consequence(character, check_type, target_difficulty, consequences)`**: Generic consequence selection. Performs check, selects weighted consequence from pool, applies character loss filtering. Returns `PendingResolution` (not yet applied). Any system can call this.
- **`apply_resolution(pending, context)`**: Apply effects from a selected consequence using `ResolutionContext` for target resolution. Returns list of `AppliedEffect`.

### `types.py`
- **`CheckResult`**: Dataclass returned by perform_check. Contains outcome, chart, ranks, and point breakdowns. No roll numbers exposed.
- **`ResolutionContext`**: Carries typed optional refs to whatever triggered a consequence resolution (challenge_instance, action_context, future fields). Handlers use `context.character` and `context.location`.
- **`PendingResolution`**: Intermediate result holding check_result and selected_consequence. Supports future reroll/negation by separating selection from application.

## Resolution Pipeline

1. Weighted trait points from CheckTypeTrait entries
2. Aspect bonus from PathAspect weights * CheckTypeAspect weights * character level
3. Capability points from authored CheckTypeCapabilityModifier rows (#2505) — curated gate,
   0 with no authored rows (never calls the capability oracle) or no `sheet_data`
4. Extra modifiers from caller (goals, magic, combat, conditions, `resolve_challenge`'s
   `capability_source.value`)
5. Total points -> CheckRank -> ResultChart -> roll 1-100 -> outcome
6. Outcome guarantees (#2536 slice 2, ADR-0152): if a `situation_ctx` was passed, `TIER_FLOOR`/
   `BOTCH_IMMUNITY` covenant perks (`_apply_outcome_guarantees`) may raise the outcome to an
   authored floor — absolute, never thread-scaled; announces only when it actually altered the
   outcome. Applies identically to the test-rig forced-outcome path. `situation_ctx.attacker`
   (#2536 slice 3, ADR-0153) is threaded through too — populated only on a defense-side check
   (currently only `world.combat.services.resolve_npc_attack`), `None` on every offense-side
   call — so an `ATTACKER_AFFINITY`-gated guarantee can fire on a defender's roll (#2623,
   ADR-0154 — parameterized to any `AffinityType` axis, renamed from its original Abyssal-only
   form).
   Both `_situational_perk_check_bonus` (step 5's CHECK_BONUS) and this step also make a
   DORMANT pass right after their live `applicable_perks` call (#2536 slice 3, Task 7, ruling
   2): a covenant role the checking character holds but has left DISENGAGED, that would have
   fired here if engaged, announces `"your vow lies dormant — {perk.name} would have answered
   here"` to the checker alone (never the room) — see `world.covenants.perks.services
   .dormant_perk_firings`/`announce_dormant_perks`.

## The modifier seam — `collect_check_modifiers(sheet, check_type, *, scene=None, ...)`

Central aggregator (`services.py`) that gathers condition / rollmod / scene /
equipment / CHARACTER / equipment-walk / **fashion** / **CAPABILITY** contributions
into one `ModifierBreakdown`. The CAPABILITY block (#2505) emits one contribution
per authored `CheckTypeCapabilityModifier` row. Both the roll path
(`_calculate_capability_points`) and this provenance path (`_capability_contributions`)
share one arithmetic helper, `_capability_point_allocation` — it computes the raw
`weight x effective-capability-value` product per row, truncates the **summed**
total toward zero ONCE (never per-row — per-row truncation before summing is what a
prior version did and it could silently diverge from the roll path, e.g. two rows of
weight 0.5/value 1 each: roll path truncates `1.0` once to `1`, but summing two
per-row-truncated `int(0.5)==0`s gives `0`), then allocates that single truncated
total back across rows by **largest remainder** (each row floored toward zero, the
leftover units handed to the rows with the largest fractional remainder, tie-broken
by capability name) so the recorded per-row contributions always sum EXACTLY to what
moved `total_points`. Zero-value rows are dropped only after this allocation. Pass
`scene=` to enable the **perception-relative fashion bonus**: `_character_and_equipment_contributions` resolves the perceiving
societies via `world.areas.services.societies_for_scene(scene)`
(`Area.dominant_society`, else all societies sharing the realm) and takes the
**max** `fashion_outfit_bonus` across them. Society-blind callers pass no
`scene` and are unaffected. Combat funnels every participant check (offense,
penetration, flee, environmental, clash, **and defense** via `resolve_npc_attack`)
through this seam with `scene=encounter.scene`, so fashion/covenant/conditions
apply uniformly to attack and defense (#750/#512).

**Social/scene actions** funnel their plain (non-technique) check through the same
seam in `world.scenes.action_services._resolve_action_against_persona`
(`scene=request.scene`), so conditions / rollmod / scene / equipment / CHARACTER /
fashion reach social checks too (#1702). The technique branch collects its own
modifiers downstream and is left untouched. That call also passes
`extra_contributions=` the result of
`world.relationships.services.relationship_gated_contributions(perceiver=target, perceived=initiator)`
— the **directed allure** path (#1696): when the *target* holds a gating relationship-condition
("Attracted To") toward the *initiator*, the initiator's allure rides the roll, once per gating
condition (so "Very Attracted" doubles it). `RELATIONSHIP`-kind contributions; empty until #1697
seeds the conditions.

## Integration Points

- **Traits app**: Uses PointConversionRange, CheckRank, ResultChart, CheckOutcome
- **Classes app**: Uses Aspect and PathAspect for aspect bonuses
- **Progression app**: Uses CharacterPathHistory for current path lookup
- **Conditions app** (#2505): `get_effective_capability_value(sheet, capability)` is the sole
  agency-oracle source `_calculate_capability_points`/CAPABILITY contributions read; lazily
  imported (`world.conditions.services` already imports `world.checks.services` at module scope)
- **Mechanics app**: `resolve_challenge()` uses `apply_resolution()` for effect dispatch, and
  folds its `capability_source.value` into `extra_modifiers` before calling `perform_check()`
- **Any system**: Can call `select_consequence()` + `apply_resolution()` for standalone consequence resolution (magic mishaps, reactive checks, etc.)
- **Callers**: Goals, magic, combat, conditions compute extra_modifiers before calling perform_check

## Design Principles

- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect)
- **No check persistence** -- results are transient, used by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals/magic/combat compute their own modifiers
- **Absolute imports** throughout
