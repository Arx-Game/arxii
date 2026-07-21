# Situation requirements grow typed parameter columns, not new enum values per axis

#2536's Layer 4 situation library shipped every knob as an argumentless boolean: thresholds
(`ALLY_LOW_HEALTH_FRACTION`, `SURROUNDED_LOCK_THRESHOLD`, `FAVORABLY_DISPOSED_MIN_AFFECTION`)
were module constants, and `attacker_abyssal` flattened `CharacterAura`'s three-axis Decimal
percentages to a single `dominant_affinity == ABYSSAL` check — tripping the standing
don't-flatten-magnitude-to-boolean guardrail and making every tuning pass a code edit. #2623
(`gh issue view 2623`) revisits ruling 5 ("hardcoded labels with real meaning; everything else
is data"): the ruling says labels are taught in code, not that labels take no arguments — a
label plus typed parameters keeps the taught-once boundary while moving thresholds and axes
into data, where ruling 5 wanted them all along.

## Decision

A new abstract `SituationRequirementMixin` (`world.covenants.models`) adds four typed,
nullable/blank columns — `threshold_percent` (`PositiveSmallIntegerField`, 0-100), `count_threshold`
(`PositiveSmallIntegerField`), `affinity` (`CharField`, `AffinityType` choices), `origin_side`
(`CharField`, new `SituationOriginSide` choices: `OURS`/`THEIRS`) — inherited by BOTH
`VowSituationalPerkSituation` and `VowSituationalPerkRung`, answering the issue's open Q2: rungs
parameterize identically, so "…and further when allies drop below 25%" is an ordinary rung with
its own tighter `threshold_percent`. No JSON (ADR-0007) — every knob is a real, queryable,
`clean()`-validated column, the same shape `check_type`/`floor_success_level`/the slice-3 scope
columns already use.

`world.covenants.perks.constants.SITUATION_PARAM_SPECS` is a frozen per-situation
`SituationParamSpec(allowed, required)` contract; the mixin's `clean()` enforces both
directions — a param authored on a situation that never reads it is rejected at author time,
and a required param missing is rejected — mirroring the per-effect-kind gating already on
`VowSituationalPerk.clean()`. The old module constants stay as the documented null-parameter
defaults, so all 14 pre-#2623 situation rows behave byte-identically: parameterless rows are the
parameterless default of a parameterized family, not a breaking change.

`ATTACKER_ABYSSAL` is superseded by `ATTACKER_AFFINITY` (required `affinity` axis, optional
`threshold_percent`) and REMOVED outright rather than kept as back-compat sugar — pre-production,
no data migration (ADR-0013), and no lore-repo fixture referenced the old name. This amends
ADR-0153, whose v1 approximation this generalizes.

Combat-origin direction (open Q3) gets a new `CombatEncounter.initiated_by_pc_side`
(`BooleanField(null=True)`): `True` = a PC participant's action opened the encounter, `False` =
the opposing side sprang it, `NULL` = unknown/undirected (duels, battles, staff-opened).
`seed_or_feed_encounter_from_cast` stamps `True` unconditionally at CREATE — verified, every
encounter-creation path today is PC-cast (`cast_seed.py`, `duels.py`, `battles/services.py`); no
code path exists that could stamp `False`. Rather than inventing an NPC-aggression system to
give `False` a caller, the ADR records this honestly: `False` is admin/GM-stampable in v1 (the
column is exposed in combat admin), and the first NPC-initiated-encounter service to land stamps
it at creation. `AMBUSH_UNDERWAY`/`COMBAT_OPENED_FROM_PARLEY` gain an `origin_side` param read
against this column (blank = today's side-blind behavior; `NULL` initiator with a non-blank
param = direction unprovable = situation does not hold).

## Rejected alternatives

- **JSON params column** — ADR-0007 rules this out outright; it would also move situation
  authoring out of the admin-editable, `clean()`-validated, queryable column world every other
  authored constraint on these models lives in.
- **Per-situation parameter tables** (a `ThresholdSituationParams`/`AxisSituationParams`
  side-table per shape) — more schema and more joins than four shared columns on the mixin
  already carried by both requirement models; the parameter space (percent, count, one axis
  enum, one side enum) is small and closed enough that a shared row covers every family without
  per-shape sprawl.
- **New enum values per axis** (`ATTACKER_PRIMAL`, `ATTACKER_CELESTIAL`, `ALLY_LOW_HEALTH_25`,
  …) — the exact overfit pattern the issue was filed to stop; every tuning pass would stay a
  code change instead of a content edit.
- **A `resonance` FK parameter target** (open Q1's other candidate) — dropped: no attacker-side
  data source stores resonance holdings (`Thread` rows belong to `CharacterSheet` owners;
  `CombatOpponent`/`ThreatPoolEntry` carry none), so an authorable resonance knob would be inert
  on every attacker the situation can actually see.

## Consequences

The `(perk, situation)` / `(perk, rung_number)` unique constraints are unchanged — one row per
situation per perk in v1; multi-row same-situation composition ("attacker ≥30 Primal AND ≥30
Abyssal") stays deliberately out of scope. `SituationParams` (`perks/context.py`) is a frozen,
hashable dataclass built from a requirement row's `.params` property; `_PerkResolver`'s
`_eval_cache` keys on `(situation, params, holder_pk)` so a rung can re-require the same
situation at a tighter parameter without cache collision. `initiated_by_pc_side` being honestly
`NULL`-heavy in v1 (no NPC-initiated creation path stamps `False` yet) is a recorded, not
invented, gap — `origin_side=THEIRS` perks are authorable now and will start firing the moment
an NPC-initiated encounter service exists, with no further schema change.

> Status: accepted · Source: issue #2623 · Amends: ADR-0153 (`ATTACKER_ABYSSAL` v1 approximation
> superseded by `ATTACKER_AFFINITY`) · Related: ADR-0149 (four-layer vow-power model — Layer 4),
> ADR-0151 (situational-perk machinery, slice 1 — the `SITUATION_EVALUATORS` registry and
> per-effect-kind `clean()` gating this contract mirrors), ADR-0152 (outcome guarantees, slice
> 2), ADR-0007 (no JSON fields), ADR-0013 (no data migrations pre-production)
