# ADR-0092: Relationship Bond Pull Modulation is unsigned and saturating, deliberately diverging from Court Regard Modulation's signed-ratio shape

#1849 added a second per-`target_kind` thread-pull modulation rule (extending the
seam ADR-0086 built): `relationship_bond_modulation` for `RELATIONSHIP_TRACK`
threads. It deliberately diverges from the existing Court rule
(`court_regard_modulation`) in two ways, both load-bearing rather than
incidental: (1) it consults no `RegardPolarity` — Court modulates an NPC master's
*preference*, where narrative consistency demands the empowerment direction match
the master's actual opinion, but a PC-to-PC relationship (rival or lover alike)
should reward investment unconditionally, so a sign-gate would undermine the
"enemies to lovers" design goal it's built for; (2) its magnitude is a
saturating curve (`round(cap × S / (S + half_saturation))`, reusing the formula
shape `ThreadSurvivabilityTuning` already established) rather than Court's fixed
`|value|/MAX × K` ratio, because `CharacterRelationship` values grow unbounded
(no equivalent to `NpcRegard`'s `0..REGARD_MAX` ceiling) — the fixed-ratio shape
would either overshoot without a clamp or need an arbitrary, unbacked
normalization constant. The rejected alternative was mirroring Court's shape
exactly (signed ratio × K) for consistency between the two rules; that was ruled
out because the two rules serve genuinely different narrative purposes (NPC
preference vs. PC investment) and Court's boundedness assumption doesn't hold
for relationships.

> Status: accepted · Source: #1849, ADR-0086
