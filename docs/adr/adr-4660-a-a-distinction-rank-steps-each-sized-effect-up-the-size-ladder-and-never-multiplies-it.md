# ADR-4660-A: A distinction's rank steps each sized effect up the size ladder and never multiplies it

**Date:** 2026-10-25
**Status:** Accepted (owner ruling 2026-10-25 on the parent spec #4551; this is its slice 6)
**Issue:** #4660 (parent #4551). Supersedes the Rank paragraph of ADR-4638-A.

## Decision

On the check lane, a sized distinction effect is worth the value table's number for its holder's
level and the size its held rank names. Staff author that size per effect and per rank in
`DistinctionEffectRankSize` (one row per effect and rank, rank 2 or more, never Paramount, no
higher than the distinction's `max_rank`). A rank with no row keeps the size of the nearest lower
rank that has one, ending at the effect's own `modifier_size`, which is its rank-1 size. So one
distinction can step one effect Minor, Minor, Large while its other effects keep their size, and a
sized effect with no rank rows is worth the same at every rank. The sign still comes from the
effect's authored rank-1 value. `value_per_rank` and `scaling_values` no longer scale a sized effect
on checks; they still drive unsized effects and every non-check reader. The change is confined to
`_sized_distinction_value` in `world/mechanics/services.py`, which reads
`DistinctionEffect.size_at_rank`; amplification, immunity and the light taper apply to the result
as before.

## Rejected

- **Multiplying the table number by rank (ADR-4638-A as built).** Rank 3 of a Large effect became
  three Large steps: past Exceptional, the largest authorable size, and as one contribution it
  escaped the light taper that three separate bonuses would take.
- **Ignoring rank once sized.** Buying rank 2 of a distinction would buy nothing on checks.
- **One "+1 size per rank" flag on the effect.** The ladder is four authorable steps long, so a
  fixed step runs out within a few ranks, and staff need shapes a flag cannot say, such as Minor,
  Minor, Large.
- **A list of sizes on the effect.** That is a JSON field (ADR-0007); the child table is queryable,
  constrained in the database and edited as an admin inline.
