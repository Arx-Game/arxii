# ADR-4608-A: Roofs and screens are position facts, not shelter rows

**Date:** 2026-10-24
**Status:** Accepted
**Issue:** #4608 (slice 3 of #4576)

## Decision

Overhead cover and a break in line of sight are two booleans on the position node itself,
`is_roofed` and `screens_ranged` (on `PositionNodeBase`, so a blueprint carries them and
`instantiate_blueprint` copies them). The reach rules read them directly, before any edge
test: no strike of any reach or delivery passes between an AERIAL position and a roofed
ground position (`roof_between`), even though the aerial twin and its ground twin share a
passable vertical edge; and a missile or room-wide strike at a screened position must come
from that position or one beside it (`screen_blocks`). Both `position_reachable` (PC
techniques) and `strike_reaches` (NPC entries) apply them, so the rule is the same for both
sides. The route search and `move_to_position` close the vertical edge under a roof, so a
flier lands beside a roofed position and walks in. A forced landing is not a route and
ignores the roof. Nothing is mirrored into the aerial layer: the edge rows stay as they are,
so a roof never drifts out of step with the map.

## Rejected

Reusing `PositionShelter`. A shelter row lowers damage of one damage type at a position
(`apply_position_cover`); it cannot say that a strike does not land at all, and a "roof"
built from shelter rows would still let a flier hit for reduced damage. A roofed tent can
carry shelter rows as well, for what gets through its walls. Also rejected: marking the
vertical edges under a roof impassable, which would put the fact on rows the aerial layer
creates and destroys, and would block reach only along that one edge while a flier one
position over still struck down into the roofed position.
