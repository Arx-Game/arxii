# 0325 — The area ladder is sizes only, and a city is a barony

**Status:** accepted (2026-09-30, #4085)

`AreaLevel` carried three kinds of thing on one integer ladder: urban sizes (building,
neighborhood, ward, city), feudal holdings (barony, county, duchy, kingdom, empire; ADR-0309)
and one mechanical boundary (region, the scope gossip and its readers looked up). Because a
child's level must be strictly below its parent's, the ladder's order was also a rule about
what may contain what, and the mixed ladder produced rules nobody meant: a barony could
contain a city but a city was never a barony, and a region had to be smaller than a county.
**The ruling:** the ladder is sizes only. `REGION` is retired (the boundary it stood for is
gone, ADR-0324). `CITY` and `BARONY` are one rung, named `BARONY`, at the old city value 40: a
barony is the actual holding a title or a Lord Mayor stands on, whatever its shape, a city, a
fortress or a temple, anything big enough for a real population, which is also what ADR-0310
already says a seat is. Nothing stored moved: no production row sat at 46 or 50, and the data
migration re-levels any that do to 40 and refuses to leave a child level with its parent.
**Rejected:** (a) two rungs at the same tier with a rule forbidding either inside the other,
which adds a second ordering to maintain beside the numeric one; (b) a new neutral name for the
merged rung (Settlement, Seat and Holding are all taken by other things in the glossary, and
Barony is the word the seat rule already uses). Related: ADR-0309 (the feudal rungs stay real
Atlas levels; its list is amended by this), ADR-0310, ADR-0324.
