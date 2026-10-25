# ADR-4670: The combat map is drawn in SVG, with places as areas

**Date:** 2026-10-25
**Status:** Accepted
**Issue:** #4670 (slice 1 of #4651)

## Decision

The combat map is an SVG drawing: each place is a rectangle of map squares (`area_x`, `area_y`,
`area_w`, `area_h` on `Position`) over its `MapTerrain` art, and a token stands on a square inside
its place (`ObjectPosition.square_x`, `square_y`). React Flow stays only for the non-fight scene
map. Squares are drawing only and never rules: hops, held ground, walls and reach still read
places and edges, so a move that names a square costs what the move to that place costs, and
`step_to_square` inside the held place is free. We did it because the fight is the main view and
players need to see where everyone stands, which a node graph cannot show: a node is a point with
a label, not a room with floor space. We rejected keeping React Flow nodes and sizing them to
areas: a node carries its own box model, handles and zoom behaviour, so terrain tiling, the grid
and a token landing on a square would each fight the library, and every later map feature
(walls drawn along edges, movement overlays, area authoring) would inherit that fight.
