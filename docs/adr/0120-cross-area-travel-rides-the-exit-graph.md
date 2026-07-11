# Cross-Area travel rides the exit graph; Area coordinates are parent-local rendering data

`find_route()` (`world.areas.positioning.travel`, #2163/#2223) drops the same-Area
precondition and lets BFS cross Area boundaries wherever a room-level `Exit` actually
connects two rooms — the hop cap (`TRAVEL_MAX_HOPS`) and the publicly-listed-room gate
(`room_is_publicly_listed`, the #1287 privacy invariant) are unchanged and still apply
to every waypoint and the destination. Rejected: a new `AreaAdjacency` model recording
which Areas connect to which. Exits already encode every walkable connection in the
game; an adjacency table would need hand-maintenance kept in sync with room exits by
hand, could drift out of true, and still couldn't produce an actual walkable route by
itself — you'd have to walk the exit graph anyway to turn "Area X is adjacent to Area
Y" into a hop sequence, so the adjacency model would be pure duplication with an extra
failure mode. Separately, `Area.grid_x`/`grid_y` (added the same issue) are rendering
hints only — each area's position within its *own parent's* local grid, not a resolved
global coordinate — mirroring the ADR-0081/0085 precedent that a coordinate plane can
be scoped to one abstraction (there, `BattlePlace`'s internal per-`Battle` x/y plane,
deliberately kept separate from the room `Position`/`PositionEdge` graph) without
claiming to be a universal frame; `area_grid_path()` composes the parent-local chain
for a future renderer to lay out, but nothing in it, and nothing in `find_route()`,
ever consults these coordinates for routing — connectivity is exits, full stop.

> Status: accepted · Source: #2223 Decisions 1 & 2 · Related: ADR-0081/0085 (the
> scope-local-coordinate-plane precedent for `Area.grid_x`/`grid_y`)
