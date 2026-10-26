# ADR-4723-A: Big effects can lift a check off an impossible chart

**Date:** 2026-10-26
**Status:** Accepted (owner ruling 2026-10-26 on the parent spec #4551; this is its slice 7)
**Issue:** #4723 (parent #4551). Supersedes the hopeless pin paragraph of ADR-4601-A and
withdraws decision 3 in ADR-4593-A's Why.

## Decision

A check's chart comes from both sides' full totals, modifiers included, with no special case for
a chart that has no Success outcome. The hopeless pin is removed from `resolve_standing`
(`world/checks/slide.py`), and so is the plumbing that only it read: `extra_standing` and
`target_modifiers` through `perform_check` and its wrappers, the action pipeline and
`PendingActionResolution`, `ModifierBreakdown.standing_total`, `OWN_STANDING_SOURCE_KINDS`,
`level_opposition_points` / `OppositionPoints`, `chart_is_impossible`, and `CheckStanding`'s
own-standing, `hopeless` and `pinned` fields. A big enough buff or pile of buffs lifts a roll off
charts -7 and -8 like any other chart. Buffs that do not reach the next rank only slide the roll,
and the slide still never shows an outcome its chart lacks, so "make the impossible possible"
means moving onto another chart. Unchanged: the slide, charts -7 and -8, listing an approach as
Impossible when its current total lands on a chart with no Success (that describes the odds, not
a wall), vow outcome floors capped at the landed chart's best outcome, and the light taper.

## Why

The owner, 2026-10-26 (#4551 comment 6425127250): "very large effects/spectacular results are
explicitly supposed to make the impossible possible", and "'impossible because of X' isn't really
a thing". Keeping the top tiers hard is the job of the taper and of tuning the value tables, not
of a rule that walls them off.

## Rejected

- **Keeping the pin with a higher threshold** (only very large piles escape). It is still a wall,
  and the owner ruled walls out; the taper already makes large piles cost real effort.
- **Keeping the own-standing split for later use.** Nothing else reads it, and the repo keeps no
  unused compatibility surface. The taper's untapered kinds are decided by `ModifierTaper` rows,
  not by this split.
