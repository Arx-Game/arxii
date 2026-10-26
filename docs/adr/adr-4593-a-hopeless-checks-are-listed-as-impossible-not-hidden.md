# ADR-4593-A: Hopeless checks are listed as Impossible, not hidden

**Date:** 2026-10-23
**Status:** Accepted (spec approved on #4551)
**Issue:** #4593 (slice (a) of #4551). Amends the "never impossible" rule of #2707.

## Decision

#2707 kept every result chart winnable (chart -6 holds 1% Success) so that no approach was
ever graded Impossible, because both approach-listing call sites in
`world/mechanics/services.py` dropped an Impossible approach from the player's list. That
rule is replaced. Charts -7 and -8 now exist with no Success outcome, and an approach
graded Impossible (`chart_has_success_outcomes` is False) stays in the list, labelled
Impossible, so the player sees the option and how hopeless it is. Charts -6 and -5 keep
their Success chance as #2707 designed them. A difference below -8 resolves to chart -8
through the closest-chart fallback; no clamp is added.

The same change makes every "at least X" chance non-decreasing across rank differences.
The old seed deliberately let those chances fall in the deep gaps; that note is retired
because a better matchup must never offer a worse chance at a tier. A data migration
repaired production (charts -4 and -2) and added charts -7 and -8; the odds on them are
example numbers.

## Why

The owner's decision (#4551 decisions 3, 5 and 6): hopeless stays hopeless, and impossible
approaches are shown rather than hidden. Decision 3 ("hopeless stays hopeless") was withdrawn on
2026-10-26 (ADR-4723-A): modifiers may lift a check off charts -7 and -8. Listing an approach as
Impossible stays, as a description of the odds at its current total. Hiding them made the list lie about what the
world offers. Keeping chart -6 winnable meant the lowest chart could never be hopeless,
which the later modifier work needs.

## Rejected

Keeping the filter and only adding the charts: the new charts would vanish from the list
and the owner asked for them to be shown. Clamping the rank difference at -8 in code: the
fallback already lands there.
