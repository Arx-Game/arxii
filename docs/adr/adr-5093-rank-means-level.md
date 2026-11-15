# ADR-5093: A check rank is the level someone is acting at, and every number scales through rows

A rank used to be one of nine named bands that every strong character reached the top of, an NPC
opposed with five points a level that fell behind a character's total as both rose, a bonus was a
hand-written value per level, perks and vow power multiplied by the sum of every thread a character
owned, and four copies of a linear cost formula sat in code. We decided that a check rank is the
level someone is acting at: rank N starts at the CHECK lane's level-N baseline
(`ModifierLevelBaseline`), and one level's width is the gap between two baselines. A character's
level adds `CheckScaleConfig.level_share` of its baseline to every roll, an NPC opposes with its
level's baseline, and a player character who is the obstacle counts as her full check total. A
modifier is worth its size's `ModifierSizeFraction` of one level's width at the level it applies
at, with `ModifierValue` kept only as an override. Staff author a difficulty as a level, or as
tenths of a level for an increment. A vow perk and vow power read only the holder's vow thread,
at its rung. Development cost is one geometric curve, `DevelopmentCostConfig`, held in a row:
each band of ten steps costs a set percent more than the band before it, and every step in a band
costs the same. A tier jump is a `LevelTier` row, a number of points added in full wherever a
level's strength is read, so a level-6 character stands several ranks above a level-5 NPC, and the
rank ladder runs past rank 30 as far as the top level's baseline plus its tier bonus. Every
per-level pool and cap (anima, the soul tether and Hollow limits, the outfit trickle, techniques
per gift, fatigue) became a per-level baseline row on its own lane. This supersedes ADR-0166's
five-points-a-level constant, and it amends ADR-4594-A, whose per-level value rows are now
overrides of a derived value.

We rejected four alternatives. A multiplier per level on each rule keeps every rule on its own
scale and gives none of them diminishing returns, which is the problem this work set out to
remove. Steeper curve formulas written in code put coefficients where staff cannot tune them,
against the rule that values live in rows. Summing every thread a character owns into perks and
vow power lets a Gift-heavy character out-power a vow-focused one; thread survivability keeps its
own flattening sum over every thread. A separate per-tier modifier that only widens the rank bands
fails because the odds come from the rank difference, and an NPC's rank equals its level, so a
band-width modifier moves a character and an NPC of the same level together and changes nothing;
the tier bonus has to raise the strength itself.

> Status: accepted · Source: issue #5093 (maintainer rulings 2026-11-15, decisions 1 to 16); supersedes ADR-0166; amends ADR-4594-A; the vow power amendment to ADR-0149 and the rethink that ADR-5091 deferred
