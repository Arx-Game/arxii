# Capability values share one uncapped ladder; blocking is emergent arithmetic, not a flag

#2704 found that `get_effective_capability_value` summed three incompatible scales as if
they were one: `CapabilityType.innate_baseline` sat at 0–1, the 739 authored
`TechniqueCapabilityGrant` rows ran 2–9, and the 41 `ConditionCapabilityEffect` rows ran
−100…+50 — with the sum floored at 0, so every effect strong enough to "block" collapsed
to the same result regardless of how negative it was. `Hastened +50` on a baseline-1
`movement` produced an effective value of 51, which `world/battles/resolution.py:935`
reads directly as grid squares of movement per round — an artifact of the scale
mismatch, not an authored design. We decided a single ladder: 0 blocked, 1-3 impaired,
5 unimpaired mortal, 8-12 gifted, 25+ greater supernatural, 100+ mythic, deliberately
uncapped above — because a high enough value must let a being do what is flatly
impossible for a mortal, and an upper cap would foreclose that on principle.
**Blocking is emergent arithmetic, never a flag**: a block is just a negative sized to
beat the tier it must beat — mundane (`-20`, e.g. Grappled: stops mortal and gifted, a
greater supernatural walks out of it), potent (`-100`, e.g. Frozen/Unconscious: beats
everything below mythic), and absolute (`-1000`, reserved for mythic-defeating effects).
The check-roll contribution (`_capability_point_allocation`, ADR-0164/D3) scores
*deviation from `innate_baseline`* rather than the raw value, so an unimpaired character
authored onto many check types contributes exactly 0 to all of them — a no-op for any
capability whose baseline is 0, since raw value and deviation coincide there.

## Rejected alternatives

- **A `blocks` boolean column on `ConditionCapabilityEffect`.** Rejected: a boolean is
  binary by construction, so it would make a block unbeatable at any power level — the
  entire point of an uncapped ladder is that a strong enough character or effect can
  eventually walk through a weaker block, and a flag forecloses that outright.
- **Rescaling to a 0–100 percentage scale.** Rejected: it would require re-authoring all
  739 `TechniqueCapabilityGrant` rows (currently 2–9) to fit the new range, versus
  re-baselining the much smaller set of 16 condition-owning rows under the ladder
  instead; it also collides with `movement`'s existing use as a literal grid-distance
  value in `world/battles/resolution.py`, which a percentage scale cannot represent.

## Consequences

Mundane restraints become escapable by the supernatural: Grappled's block moves from
`-100` to `-20`, so a greater-supernatural character (baseline well above 20) is no
longer stopped by a mortal grapple the way a `-100`-vs-baseline-1 block used to stop
everyone uniformly. Battle-grid movement quintuples across the board, since the
`movement` baseline moves from 1 to 5 — a deliberate, board-wide rebalance, not a
one-off tuning pass.

> Status: accepted · Source: issue #2704 (capability value ladder + check bridge);
> relates to ADR-0143 (canonical capability vocabulary), ADR-0034 (grant individuation
> by MAX); supersedes nothing.
