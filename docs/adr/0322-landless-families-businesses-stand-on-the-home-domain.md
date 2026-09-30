# 0322 — A landless family's businesses stand on the home city's domain, owned by the family

**Status:** accepted (2026-09-29, #4060 slice 4)

The maintainer ruled that a family's money must come from an organization whose books
are actually in shape, and that a new family should be able to start in a good or bad
position the player can see. A `DomainHolding` fed the *domain owner's* books, so a
commoner family, which owns no domain, could own no business and had no books. **Decision:**
`DomainHolding.owner_org`, blank for the pre-#4060 shape (the landholder's own holdings),
names the organization a holding pays when it is not the landholder. A family the player
names at character creation gets its Family Template's holdings materialized, unsited, on
the **home domain**: the first owned Domain up the starting room's area chain, else the
realm's capital city's, the Lord Mayor's land. Its businesses are therefore on someone
else's land and the Mayor's tax levy applies to them like anyone's (ADR-0321), which is the
point: a commoner tavern in Luxen pays the city. The Upbringing answer the player picked
(`family_standing`) seeds those businesses' `standing`, or a noble claim's seat
`prosperity`; established families show the same number read from their books.

**Rejected:** (a) a Domain per commoner family (a family is not a landholder; the
Almanach's ladder would fill with pseudo-baronies); (b) an allowance field on `Family`
(money in a void, the thing the maintainer refused); (c) `standing` on `Family` itself
(it would drift from the books it is supposed to summarize; it is derived instead).
