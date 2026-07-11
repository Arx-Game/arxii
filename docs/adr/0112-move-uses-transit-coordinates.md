# MOVE tracks in-progress position via personal transit coordinates, not a rounds-counter

`BattleParticipant`/`BattleUnit` gain their own `transit_x`/`transit_y`/
`transit_target_place` (#2007) — additive to ADR-0085, which gave only
`BattlePlace` a coordinate on the battle-map plane. A multi-round MOVE needed some
way to track "how far along" a mover is between rounds; the alternative
(a `rounds_remaining` counter computed once at declare time) would have kept
individuals coordinate-free, matching how mass-battle participants/units have
never carried positional data of their own — but it can't re-target mid-transit
without discarding progress, and it diverges from how REPOSITION already models
vehicle movement (real coordinates, capability-bounded per round). Real
coordinates let a mover redeclare toward a different target mid-course and keep
their earned distance, and reuse REPOSITION's exact distance-bounding math instead
of inventing a second movement model. Rejected: a rounds-remaining counter (loses
progress on retarget, and is a second movement paradigm alongside REPOSITION's
coordinate-based one for no compounding benefit).

> Status: accepted · Source: #2007 · Related: ADR-0085 (the `BattlePlace`
> coordinate plane this is additive to)
