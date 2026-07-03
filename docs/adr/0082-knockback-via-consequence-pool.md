# ADR-0082: Knockback authored via the existing consequence-pool pipeline

## Status

Accepted

## Context

#1317 needed a knockback mechanic (an NPC attack shoves its defender through
the room's Position graph) and a way to wire a knockback landing into a room
hazard (`Trap`)'s consequence pool. A bespoke field-driven mechanic (e.g. a
flat `knockback_distance` int on `ThreatPoolEntry`, resolved by dedicated new
service code) was considered and rejected.

## Decision

Knockback is authored as an ordinary `MOVE_TO_POSITION` `ConsequenceEffect`
with a new `PositionDestination.AWAY_FROM_ACTOR` mode, fired via the existing
`apply_pool_deterministically` (no roll — the attack's own hit already
determined it landed) from a new `ThreatPoolEntry.on_hit_consequence_pool`
FK. `Trap` gained a nullable `position` FK so a hazard can be anchored to a
specific spot rather than the whole room.

## Consequences

- No new Action, event, or generic mechanic — the entire feature rides the
  effect-handler/consequence-pool pipeline every other hazard/positioning
  effect already uses.
- The #1273 reactive Interpose seam protects against knockback for free: a
  clean interpose block zeroes `DamagePreApplyPayload.amount` before the
  on-hit pool firing check runs.
- Multi-hop knockback requires no new code — authoring multiple
  `AWAY_FROM_ACTOR` `ConsequenceEffect` rows on one `Consequence` chains
  correctly, since each resolves fresh against the defender's
  already-updated Position.
- PC-technique-authored knockback (the attacker side) remains out of scope —
  `Technique` has no on-hit-effect-pool equivalent to `ThreatPoolEntry`'s,
  and building one wasn't part of this issue.
