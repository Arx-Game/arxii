# ADR-4638-A: A distinction counts at its holder's level, scaled by rank, and stays a character modifier

**Date:** 2026-10-24
**Status:** Accepted (spec approved on #4551; this is its slice c, distinctions and scene surroundings)
**Issue:** #4638 (parent #4551). Extends ADR-4594-A and ADR-4628-A.

## Decision

Distinctions and scene surroundings are the third and fourth sized sources on the check lane.

**Distinctions.** The size is authored on the row that carries the bonus,
`DistinctionEffect.modifier_size`, on the `ModifierSize` ladder (Paramount refused, vow-only). The
level is the holder's, per #4551 decision 7: `CharacterSheet.current_level`, the cached accessor
the rest of the modifier pipeline (the equipment walk, covenant role bonuses, cast power terms)
already reads. The pricing lives in `get_modifier_breakdown(..., value_lane=...)`, not in the check
seam, because that function owns the amplification and immunity rules: a sized effect's base value
becomes the table number and amplification and immunity apply to it unchanged. Only the check
seam passes a lane; every other reader of the breakdown keeps the flat authored values, and no
other reader looks at a check-scoped target, so the two cannot disagree on one row.

**Rank.** The spec does not say how a distinction's rank meets its size. The ruling is the smallest
reading that keeps rank meaningful: rank scales the table number the way it scales the authored
number, by the ratio `get_value_at_rank(rank) / get_value_at_rank(1)`. For a per-rank effect that is
"rank 2 is twice rank 1"; for a `scaling_values` effect it follows the authored curve. The size is
therefore the size at rank 1. Rank 3 of a Large effect is worth three Large steps at the holder's
level, in one untapered contribution. This is flagged for the owner: if a rank should instead move
the size up the ladder, or not count at all, that is a change to `_sized_distinction_value` only.

**Source kind.** Distinction rows stay in `ModifierSourceKind.CHARACTER` and taper in that pile.
The other `CharacterModifier` rows that can reach a check-scoped target, achievement rewards and
form combat profiles, stay flat and taper with them (residence comfort targets AP regeneration
only). A new DISTINCTION kind was rejected: a kind with no `ModifierTaper` row never tapers, so
every distinction would have stopped tapering until staff added a row, and the two remaining
CHARACTER sources would have formed a pile of their own for no stated reason.

**Scene surroundings.** `SceneCheckModifier` gains an authored `modifier_level` and
`modifier_size`, required together (a level without a size reads nothing). The contribution reads
the table at that level, never the roller's. The model had no admin surface; a
`SceneCheckModifierInline` on the scene page is now where staff author it.

Every unsized row, and every sized row with no level (a character with no class), no value row or
a zero authored value, keeps its flat value and still tapers. All of them go through
`ValueTable.signed_value`. The value-table Required content entry names every sized source;
distinctions and surroundings need no level rows of their own.

## Rejected

- **Multiplying the table number by rank only for `value_per_rank` effects.** It would ignore the
  authored `scaling_values` curve.
- **Ignoring rank once sized.** Buying rank 2 of a distinction would buy nothing on checks.
- **Pricing in the check seam from the breakdown's final values.** The seam would have to redo the
  amplification and immunity rules on the sized base.
- **`get_character_path_level` as the holder's level.** It queries per call and floors at 1;
  `current_level` is cached on the sheet and is 0 for a character with no class, which reads as
  "no level" and keeps the flat value.
