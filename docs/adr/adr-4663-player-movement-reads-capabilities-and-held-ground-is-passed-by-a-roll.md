# ADR-4663: Player movement reads capabilities, and held ground is passed by a roll

**Date:** 2026-10-25
**Status:** Accepted
**Issue:** #4663 (slice 2 of #4651)

## Decision

How a player character moves across the position graph is read from her capabilities and nothing
else. A `CapabilityType` row names a way of moving through its `traversal` field (a
`CreatureTraversal` value, blank for none); `player_traversals(sheet)` returns WALKS plus every
traversal whose capability she holds above its `innate_baseline`, from any source (technique,
condition, species, distinction or gear), and `edge_crossing_cost` prices an edge for the cheapest
of them. Ground held by a ready enemy stops a player character who enters it, however she moves
on the ground (NPCs do not roll: an NPC walker or climber stops, an NPC flier or leaper passes),
and a roll against a staff challenge (`MovementConfig.held_ground_challenge`) lets a character with a matching capability get
past it cleanly, past it at a price, or stopped. We rejected branching in code on particular
capabilities, or looking them up by name: a new way of moving (swimming, burrowing) is a staff row
and a `traversal` value, and a capability a player earns in a new way needs no movement change.
