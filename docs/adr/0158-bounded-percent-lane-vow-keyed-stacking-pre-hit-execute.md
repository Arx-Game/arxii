# The percentage-bounding model is the only buff-multiplier lane, forever; vow-keyed stacking weights; execute prices off pre-hit health

The ratified damage identity (lore repo `design/covenant-vows-consolidated.md` §5): team
damage = Strike's bases (execute-scaled) × Uplift's team-wide % × Undermine's enemy-side %.
#2643 built the machinery for this composition. Three hard, easy-to-get-wrong decisions
needed recording before the next percent-lane feature request reopens them.

## Decision

**A percent-buff lane is bounded, forever — never a second multiplicative stage.** The
`team_damage_percent` lane (Uplift) and the pre-existing enemy-side
`ConditionDamageInteraction.damage_modifier_percent` lane (Undermine) both clamp their
SUMMED contribution to a flat cap (`TEAM_BUFF_LANE_CAP_PERCENT` / `ENEMY_LANE_CAP_PERCENT`,
both 50) before the percent multiplies damage. The team lane folds its clamped delta into
the SAME single `builder.multiply` call the legacy `power_multiplier` target already used
(`world.magic.services.techniques._apply_power_multiplier_stage`) — `total_delta =
lane_delta_clamped + legacy_delta` — rather than adding a second `PowerStage.MULTIPLIER`
entry. This is the "EQ2 lane guard": in that game's itemization history, buff percentages
from independent sources multiplied against each other rather than summing-then-clamping,
so two or three modest buffs compounded into an absurd, balance-breaking spike. A bounded,
summed lane is immune to that by construction — the cap holds regardless of how many
sources contribute. **Any future percent-buff/debuff surface reuses one of these two lanes;
it does not add a third.**

**Power buys the percentage, priced against the landing target's level.** A lane condition
authors `value=1` + `scales_with_severity=True`; `world.conditions.services
.priced_percent_severity` computes the granted severity at apply time from the caster's
effective intensity divided by the target's level (PC: `CharacterSheet.current_level`;
NPC: a flagged `combat.constants.OPPONENT_TIER_LEVEL` pseudo-level table), not from the
row's own authored severity formula. This keeps a fixed percent from being simultaneously
"huge" against a mook and "trivial" against a boss for the same cast power.

**Vow-keyed stacking: diminishing returns within one vow, full stacking across vows.**
`conditions.ConditionInstance.source_vow` (nullable FK → `covenants.CovenantRole`,
`SET_NULL`) is stamped from the applier's first engaged role's ANCHOR at apply time. The
team lane's read groups contributions by `source_vow_id` and runs
`world.magic.services.techniques.vow_keyed_diminished_total`: within one vow, contributions
weight 100% / 50% / 25% / 25%...(descending, 4th+ all ×0.25); distinct vow groups (including
the `None` "no engaged role" group) stack fully against each other. This is a deliberate
mechanical lever for #2643's four-layer vow-power design (ADR-0149): a character who invests
in ONE vow's team-buff spam hits diminishing returns fast; a character (or party) drawing
buffs from several DIFFERENT vows does not — multi-vow synergy is rewarded over single-vow
stacking, in the damage identity exactly as it already is in the power-term layers.

**Execute prices off PRE-hit health, never post-hit — no recursion.**
`AbstractDamageProfile.execute_missing_health_multiplier` scales a landing hit's damage by
`1 + multiplier * missing_health_fraction`, where `missing_health_fraction` is computed from
the target's health BEFORE this hit's own subtraction. A second hit in the same exchange
(AoE, multi-profile technique, or a follow-up strike) prices off the health the FIRST hit
left behind, not off some blended or recomputed value — the basis is always a stable,
already-known number at the moment it's read, so there is no self-referential loop and no
double-counting of the SAME hit's own damage in its own scaling factor.

## Rejected alternatives

- **A second multiplicative stage for the team lane** (apply `power_multiplier`, then
  multiply again by the team lane) — the EQ2 failure mode verbatim; two bounded lanes still
  compound into an effectively unbounded one when multiplied against each other instead of
  summed-then-clamped.
- **Authored (flat, unpriced) percentages on lane conditions** — rejected per the buff-lane
  authoring rule (`docs/systems/magic.md`'s "The Damage Identity" section): buff percentages
  in this lane are NEVER flat/authored; the lane reads only computed-at-apply severities, so
  the same technique scales correctly across every target level without per-target authoring.
- **Flat (non-vow-keyed) stacking, or a hard one-buff-per-target cap** — considered and
  dropped: flat stacking reopens the exact abuse case (spam one vow's cheap buff N times);
  a hard one-buff cap would make a legitimate second vow's buff simply not apply, punishing
  multi-vow investment instead of rewarding it.
- **Execute priced off post-hit health** — recursive by construction (the factor that scales
  a hit's damage would depend on a health value that itself depends on that hit's damage);
  pre-hit avoids the loop entirely and gives predictable, hit-by-hit composable math.

## Consequences

Pre-existing `power_multiplier` sources (Audere/Audere Majora spikes, #636) stay OUTSIDE the
band — they are not retroactively folded into `team_damage_percent`'s cap. Folding them in
(or authoring new content that intentionally straddles both lanes) is flagged future
within-lane tuning, not a #2643 requirement, and should not be read as an oversight.
`ENEMY_LANE_CAP_PERCENT`'s clamp bounds only the live damage APPLICATION — an individual
authored `ConditionDamageInteraction` row may itself exceed the band; only the summed total
a target can accumulate at once is bounded, matching the team lane's own clamp-the-sum (not
clamp-each-source) shape. `execute_missing_health_multiplier` defaults to 0 on every damage
profile, so this is byte-identical for every technique that doesn't opt in — Strike-family
techniques author a nonzero value; nothing else changes behavior.

> Status: accepted · Source: issue #2643 · Related: ADR-0149 (four-layer vow-power model),
> ADR-0151/0152/0153/0154 (situational-perk machinery this vow-keying sits alongside),
> ADR-0007 (no JSON fields), ADR-0010 (FK direction — `ConditionInstance.source_vow` points
> from the specific/dependent runtime row to the general `covenants.CovenantRole` primitive)
