# 0319 — Territory yields at the lowest controlled rung; higher rungs earn by tithe

**Status:** accepted (2026-09-29, #4060 slice 1)

Held ground has a base value: staff-built outdoor rooms are the land units, and each held
rung (a `Domain` for legitimate control, a `Turf` for criminal control) carries one
`TERRITORY` income stream whose gross is recomputed at accrual from its units. The
Almanach plants a `Domain` on every rung of a noble chain (kingdom, duchy, county,
barony) over the same ground, so the naive rule, every controller of an area earns from
every outdoor room under it, would pay the same rooms four or five times over and make
depth of ladder, not land, the source of wealth. **Decision:** an area's units exclude
the rooms a lower rung *of the same control kind* already holds. A barony's rooms pay
the barony; the duchy earns from the barony through the fealty tithe that already exists
(`FealtyEdge` + its obligation). A crew's corner pays the crew; the gang earns from the
crew the same way. The two kinds do not reduce each other: the Lord Mayor's city domain
and a gang's neighborhood both yield from the same corner, which is the maintainer's
"never either/or" (a business there will pay both, #4060 slice 3).

**Rejected:** (a) every rung earns from all rooms below (multiplies land by ladder depth);
(b) only the topmost holder earns and pays down (inverts the ladder; a kingdom would fund
its baronies); (c) split each room's value evenly across the rungs above it (hides the
tithe, which is the political lever the ladder exists to create). Buildings and indoor
rooms are never units (maintainer, 2026-09-29): player-built rooms would otherwise
manufacture territory out of nothing.
