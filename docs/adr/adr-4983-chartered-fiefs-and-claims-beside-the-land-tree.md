# ADR-4983: Chartered fiefs and claims are two relations beside the land tree

**Status:** Accepted (2026-11-03, #4983 slice 1, #4984). Extends ADR-0313.

The containment tree (`Area.parent`, footprints derived from it) stays the one de facto rule of
who holds what. Beside it sit two separate relations: `CharteredFief` (title → fief: what a
title's charter covers, its historical holdings, whose border on the map is the union of the
fiefs' footprints and is derived on read, never drawn) and `TitleClaim` (a character's or a
house's claim to rule a title, at any tier, several per title). `Title.station` names a crown
nobody sits (titular) or nobody has worn (potential); such a rung is a sibling on the ladder
with a charter, and tooling never restores it, staff do. Two alternatives were rejected. **Nesting
a titular kingdom inside the live one** as a child rung: a dormant Kingdom of Luxen is not a part
of the Republic, it is a rival reading of the same duchies, and nesting would make the land tree
assert that; the charter relation says "these duchies" without saying "under". **One claims
table carrying both ideas** (what a title covers and who wants it) in one row shape: a charter
is a fact about the title and a claim is a fact about a person, they are edited by different
staff at different times, and the first prototype conflated them until the owner separated them
(2026-11-03). The cost of two relations is a second admin inline and a second ladder read, paid
once.
