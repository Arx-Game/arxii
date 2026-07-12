# Swarm math is derived proportional losses, not a second health pool

`BattleUnit.individual_count` (#1841) is read-derived, not an independently-tracked
resource: `swarm_strike_bonus` computes a banded flat STRIKE-check bonus straight off the
current count (no persisted "bonus" field), and `_apply_swarm_losses` costs bodies
*proportional* to the same-round STRIKE net attrition / ROUT actual morale loss —
`ceil(individual_count * attrition / 100)`, since `strength`/`morale` are both 0-100
scales. `individual_count` only ever moves in lockstep with `strength`/`morale`; it is
never damaged, checked, or thresholded on its own. The rejected alternative was giving
`individual_count` its own attrition path — a second HP-like pool a STRIKE could target
and deplete independently, mirroring how `strength` and `morale` are each independently
attrited. That would have meant a third status-deriving axis (`_compute_unit_status`
already reasons about strength+morale jointly, #1712) with its own thresholds, its own
STRIKE-target semantics, and its own interaction with DESTROYed/ROUTed status — real design
surface for a feature whose actual ask (#1841) was "big swarms hit harder and shed bodies
as they take damage," not a third resource to manage. Deriving losses off the existing
resources keeps `_compute_unit_status`'s two-axis contract intact and makes swarm math a
pure function of state that already exists. Capital vessels (naval/aerial, #1714/#1832)
are explicitly out of scope here and keep their own per-hull `Fortification.integrity`
track — that's a different domain (a single hull that either holds or is breached), not a
body count, and `Fortification` already owns the "second depletable resource on a battle
object" shape correctly for that case.

> Status: accepted · Source: issue #1841 · Related: #1712 (strength+morale joint status
> derivation), #1713/#1714 (Fortification integrity for vessels)
