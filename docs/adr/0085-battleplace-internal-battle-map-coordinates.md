# BattlePlace gains internal battle-map coordinates, additive to ADR-0081

`BattlePlace` (#1714) gains `x`/`y`/`footprint_radius` — a coordinate on a
per-`Battle` internal battle-map plane, with a footprint used for overlap
detection (boarding, cross-vehicle targeting). ADR-0081 rejected anchoring
`BattlePlace` to the room-level `Position`/`PositionEdge` graph specifically —
mass battles (hundreds of PCs, abstract fronts) can't require every front to
resolve to a real room. It never asserted `BattlePlace`s have no spatial
relationship to each other. Naval/aerial vehicles need real movement and
range — a ship closing with another vessel, a dragon overflying a fleet — which
an internal, battle-scoped coordinate plane provides without coupling to the
room graph ADR-0081 kept separate. Rejected: extending `Position`/`PositionEdge`
for this (repeats ADR-0081's exact rejected alternative); a full 2D physics/
pathing engine (out of scope — this is a coarse overlap/distance check, not
real-time movement simulation).

> Status: accepted · Source: #1714 · Related: ADR-0081 (the graph this is
> additive to, not a reversal of)
