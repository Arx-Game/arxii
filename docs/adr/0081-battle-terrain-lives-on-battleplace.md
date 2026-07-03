# Battle terrain lives on BattlePlace, not the room Position/PositionEdge graph

`BattlePlace` (#1711) carries `terrain_type` and `movement_cost` directly, rather
than extending the room-level `Position`/`PositionEdge` graph (`world.areas.positioning`)
with battle-specific terrain data. The battle spine (#1592/#1733) deliberately treats
battles as location-less: `_has_unimpaired_mobility` explicitly resolves mobility via
the capability system rather than `blocks_flight`/`elevation_anchor`, noting those
fields "don't apply to location-less battles." Extending the room graph for battle
terrain would wire two abstractions the spine kept apart, and would require every
`BattlePlace` to resolve to a real `Position` — a constraint mass battles (hundreds of
PCs, abstract fronts, no positional room) don't have. `BattlePlace` is already the
abstraction battles use for "where"; terrain is data on it, the same as it carries
`combat_encounter` as its bridge to discrete tactical fights. Rejected: extending
`Position`/`PositionEdge` with a battle-terrain concept (couples two intentionally
separate abstractions, forces every battle front to anchor to a real room position).

> Status: accepted · Source: #1711 Decision 1 · Related: #1733 (the
> location-less-battles precedent this follows)
