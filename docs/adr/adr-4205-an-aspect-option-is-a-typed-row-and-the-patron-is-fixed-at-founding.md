# ADR-4205: An aspect option is a typed row, never a label; the patron is fixed at founding

**Status:** Accepted (2026-10-09, ApostateCD)
**Issue:** #4205
**Related:** ADR-0101 (aspects are catalog-only), ADR-0010 (FK direction, specific → general),
ADR-0268 (no patron FK on Family), ADR-4198 (an entry's owner registers its companion)

## Context

A house's picked aspect was a name and a blurb. A player could not open the god the house
serves from the house, the game could not ask which houses are sworn to which god, and the
unwritten `Organization.patron_nickname` promised a reading nothing produced. The maintainer
ruled the cards "just wrong": a regional fact a house picks at founding is tied to real things
and, later, to mechanics.

## Decision

`HouseAspectOption` carries what it IS: `being` and `being_nickname` (a god or totem, and the
name a house on that option calls it by) beside the existing `codex_entry` (a lore target such
as a founding battle), one or the other, never both, so a pick opens one page from every house
surface. The question decides what a pick means: `HouseAspectDefinition.sets_patron` marks the
one single-pick question per charter whose answer becomes the house's patron, written once by
`build_family_org` on both founding paths and changed afterwards only by staff. The catalog
stays catalog-only (ADR-0101): the targets are properties of authored rows, not player text,
and both FKs stay out of the content export because beings and nicknames are installation rows.

## Rejected alternatives

A patron question outside the aspect system (a second place to answer a founding fact, and a
second serializer to keep honest); a patron the founder may change later (the patron is a
fact about the house as it has always been, like its words and sigil); member effects in
this change (they are organisation-level modifiers, their own issue); a geas as a house
aspect (ruled a personal Distinction on Aythirmok characters).
