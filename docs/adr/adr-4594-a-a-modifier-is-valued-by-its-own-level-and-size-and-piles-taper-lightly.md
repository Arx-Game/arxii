# ADR-4594-A: A modifier is valued by its own level and size, and piles taper lightly

**Date:** 2026-10-23
**Status:** Accepted (spec approved on #4551; this is its slice c1)
**Issue:** #4594 (parent #4551). Relates ADR-0158 and ADR-0166. Does not yet supersede any part of
ADR-0158: that happens when the cast power lane (the team damage percent) joins this model.

## Decision

A modifier carries a **level** and a **size**. Its value is a row of one shared value table,
`ModifierValue(lane, level, size, value)`, read at the highest authored level at or below the
modifier's own. The size ladder is `ModifierSize`: Minor, Moderate, Large, Exceptional, and
Paramount, which only a vow's size step reaches. The value is a magnitude; the authored modifier
row keeps its sign, so a debuff stays a penalty. Nothing in the valuation reads the bearer's or
the target's level: the same Large level-6 buff is the same number on every character, and so a
bigger share of a weaker character's rank band.

The modifier pipeline is unchanged in shape: `collect_check_modifiers` still gathers every source
into one `ModifierBreakdown`. `ModifierContribution` gains `level`, `size` and `vow_part`;
`ModifierBreakdown` gains `tapers` and applies the **light taper by kind**: within a roll, the
contributions of a tapered source kind form two piles (bonuses, penalties), each counted largest
first, the k-th at `max(ratio^(k-1), floor)` of its value less its `vow_part`. The owner's numbers
are a ratio of 7/8 and a floor of 2/3, stored as `ModifierTaper(lane, source_kind, ratio, floor)`
rows. A kind with no row never tapers; the character's own standing (rollmod, effort, fatigue,
strain, soulfray, capability) gets no row, and a vow's step (`vow_part`) is always counted whole.

Every table carries a `ModifierLane` column, so the later lanes in #4551's inventory (stats, cast
power, damage, soak, healing and the rest) add rows and a choice, not models.
`ModifierLevelBaseline(lane, level, baseline)` records the typical total at each level, which staff
and the tuning dashboard use to read a value as a share of a rank band.

The first source to be sized is a technique's buff or debuff. `TechniqueAppliedCondition` authors a
`modifier_size` (blank keeps the condition's flat values) and a `narrow_use` flag. The cast's
effective power picks a level from `CastPowerLevel` rows, its outcome shifts it by a
`CastOutcomeLevelShift` row, and the resulting `ConditionInstance` keeps `modifier_level` and
`modifier_size`. Its `ConditionCheckModifier` rows then read the value table instead of their flat
value, with no further severity or stage scaling. The size on the instance is a deliberate snapshot
of the authored row at cast time: a staff edit to the technique changes later casts, never buffs
already standing, and one technique can carry the same condition on more than one row. Items, distinctions and scene modifiers keep
their flat values until their own slices, and still taper with their kind.

All of this is database rows with admin pages; the seed carries example values only, and an empty
table leaves behavior exactly as it was (flat values, plain sums).

## Why

Before this, every source stored a flat integer and `ModifierBreakdown.total` was a plain sum: no
author could say "a large bonus for its level", a flat bonus moved a beginner two ranks and a
veteran none, and ten buffs added ten times one buff. The owner ruled that a modifier's strength
comes from its own level and size, that a pile of ordinary modifiers takes a light taper, and that
the vow's enhancement is never eaten by it (#4551 decisions 1 and 7, comments of 2026-10-21 to
2026-10-23). Keeping the pipeline and adding columns honours "nothing replaces it"; one lane
column honours "the system is relatively universal".

## Rejected

- **A cap on the total buff value.** It would also cap the sworn buffer, which the owner ruled
  out.
- **A table per lane** (a `CheckModifierValue`, a `DamageModifierValue`...). Every later lane would
  add a model and a parallel reader; the lane column makes it a row.
- **Valuing a buff against the target's level.** The owner's rule is that the value comes from the
  buff's own level; the effect on a given character falls out of that character's own totals.
- **Deriving values from a formula in code** (share x step x baseline). The tuning must live in
  rows staff can edit; the formula is how the example rows were sized, and the universality guard
  (a later slice) checks rows against it.
- **Tapering own standing.** Effort, fatigue, strain and soulfray are the character's own
  standing (#4551 decision 7); tapering them would penalize a character for their own build.
