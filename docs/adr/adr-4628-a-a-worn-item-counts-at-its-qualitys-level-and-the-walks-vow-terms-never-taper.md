# ADR-4628-A: A worn item counts at its quality's level, and the walk's vow terms never taper

**Date:** 2026-10-24
**Status:** Accepted (spec approved on #4551; this is its slice c, worn items)
**Issue:** #4628 (parent #4551). Extends ADR-4594-A.

## Decision

Worn items are the second sized source on the check lane. The level comes from quality (#4551
decision 7): `QualityTier.modifier_level` is the item level row, a column on the tier rather than
a side table, because each tier has exactly one level and the level is lane-independent like
`CastPowerLevel.level`. The size is authored on the row that carries the bonus,
`ItemCheckModifier.modifier_size`, on the same `ModifierSize` ladder as technique buffs, with
Paramount refused (vow-only). A sized row reads `ModifierValue` through the shared
`ValueTable.signed_value`; the flat `modifier_value` then supplies only the sign. A row with no
size, a worn instance with no tier, a tier with no level, or a missing table row keeps the flat
value, and all of them taper with the EQUIPMENT pile.

`ItemCheckModifier` stays apply-once per template (the #3430 stacking rule). When several worn
instances of one template qualify, the row counts at the **best** of their levels. The level is an
aggregate over the same filtered join that decides whether the row counts, so a spare that is
carried, or worn but unattuned where attunement is required, never raises it.

The equipment walk is split into its worn-item terms (facet, facet crossing, mantle, mantle
crossing, motif style) and its vow terms (covenant role, covenant level, vow stat scaling) by
`equipment_walk_parts`. On a check, the vow terms ride as the walk contribution's `vow_part`, so the
taper never eats them (#4551 decision 1). `ModifierContribution.vow_part` thus carries the
character's vow share generally, and slice (d)'s vow size step joins it.

Crafted modifiers become one EQUIPMENT contribution per worn piece instead of one lump, so three
crafted pieces taper as three modifiers.

## Deferred, with reasons

- **Sizing crafted recipe modifiers and accents.** `CraftingRecipeModifier` and `ItemAccent` target
  a generic `ModifierTarget` that `get_modifier_total` reads for every lane. Sizing them on the check
  seam alone would let the check and the other readers disagree on the same row's value. They join
  with the generic-target carrier (#4551 section 5.5). They already scale with quality through
  `stat_multiplier`.
- **The walk's thread passives.** Facet and mantle passives scale by thread level times item
  quality: thread power with its own scaling, which belongs with the magic lanes. They stay flat
  and taper.
- **Fashion** is its own FASHION kind (perception-relative), unchanged.

## Rejected

- **A `QualityTierModifierLevel` table.** A 1:1 side table for one integer, with a join and a row to
  keep in step.
- **Deriving the level from `sort_order` or `numeric_min` in code.** Tuning lives in rows staff
  edit; a formula in code would be a constant.
- **The worst or the first worn instance's level.** The worst punishes a character for a spare; the
  first depends on row order.
- **Tapering the walk whole.** It would let the taper eat a vow, which the owner ruled out.
