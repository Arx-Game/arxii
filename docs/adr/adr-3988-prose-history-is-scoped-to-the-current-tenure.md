# ADR-3988: Prose history is scoped to the current tenure

**Status:** Accepted (2026-10-10, ApostateCD)
**Issue:** #3988
**Amends:** the #2631 ruling (prose history visible to the owner and staff)

## Context

#2631 made a character's prose history visible to its owner and to staff. A roster
character changes hands: the owner of today is not the author of last year's background.
Under #2631 a new tenant reads every word the previous player wrote and then replaced,
including what they chose to take back. #3988 also widens the history to every prose
field, the description and the concept included, which raises what is at stake.

## Decision

Staff see every version. A player sees only the versions written on or after the start of
their own current `RosterTenure` on that entry. A tenure with no start date shows none.
There is no new column: the filter reads `ProfileTextVersion.created_at` against
`RosterTenure.start_date`.

## Consequences

A returning player who picks a character up again sees only their new era of it. The CG
original of a character whose first tenure began after its creation is not shown to that
player; staff still see it. Nothing is deleted, so a later ruling can widen the view again.

## Alternatives rejected

- **A tenure foreign key on each version** stores what the dates already say and needs a
  backfill for every existing row.
- **Leave #2631 as it was** lets a roster pickup read prose its author withdrew.
