# ADR-4983-B: Containment is drawn by the owner and partitioned below

**Status:** Accepted (2026-11-03, #4983 slice 2, #4986). Companion to ADR-4983.

The owner draws every kingdom's outline by hand on the region map; the layout tool
(`houses/layout.py`, `houses/partition.py`) only splits what is drawn, planting duchies,
counties and single-pip seat baronies beneath it by weighted multi-source region growing
over 4-connected land, the capital child seeded on the crown's seat and weighted largest,
water kept with the land it touches, and every write going through the existing services
(`plant_rung`, `set_footprint`, `name_rung`, `set_pledged_liege`, `charter_fief`,
`record_claim`). Two alternatives were rejected. **A generator that also draws kingdoms**:
the owner ruled that a realm's shape at the top is authored, and a tool that drew it would
be wrong at every river and ridge in a way nobody would clip back; the border-correcting
tools (slice 3) are cheaper than a smarter generator. **A Voronoi split over seeds with no
weights**: it gives equal children and ignores the capital, and the owner's stated rule is
that the capital duchy, county and barony come out largest and richest. The cost is a
layout the owner edits by hand afterwards, which is the point: an evening of clipping
instead of an evening of drawing.
