# 0080 — Heat jurisdiction is judged at the commit location, enforcement scoped to the dominant society

**Status:** accepted (2026-07-02, #1765)

Laws live on the `Area` tree and resolve most-specific-wins (a barony row —
including an exemption — beats the kingdom default), mirroring feudal local
paramountcy: the winning local row carries both "illegal here" and "how hard
the local authority pursues it" in one `heat_weight` knob. Criminality is
judged **once, at the location where knowledge of the deed lands**, and the
winning law's nearest `Area.dominant_society` is the enforcing society; heat
only ever mints — and only ever reads — inside that society's dominion. This
makes cross-border immunity (no extradition between crowns) and sanctuary (a
guild-dominated hall inside a hot city reads Safe) the *same* mismatch rule
rather than two features. Spatial falloff is deliberately **emergent from
knowledge locality** (word spreads locally, so heat concentrates near the
crime) — there is no distance math.

**Rejected:** society-owned law codes applied wherever the society dominates
(cannot express "this barony differs from its kingdom" without a second
mechanism); explicit tree-distance falloff at read time (extra machinery that
decouples heat from the "hot where the deed is *known*" model — revisit only
if playtests show knowledge spreads too evenly for falloff to feel real).
