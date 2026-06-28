# Falling gains power; redemption is lossy (asymmetric resonance conversion)

A permanent **Fall** — a Celestial character turning to a *selected* Abyssal resonance — converts
their resonance and threads into the new resonance and makes them **stronger** (the fall is a net
gain), while **Redemption** (Abyssal → Primal, especially → Celestial) is a **lossy** conversion that
sheds resonance strength; the asymmetry makes damnation tempting and grace costly (ADR-0035). This is
a one-time conversion of *already-earned* resonance, not a new earning loop, so it does not undercut
ADR-0041 (resonance earned from being perceived). No resonance-type conversion exists today —
`grant_resonance` is add-only and `CharacterResonance.lifetime_earned` is monotonic — so this needs a
new conversion service that resolves a lossy redemption without violating that invariant (convert
spendable/affinity strength, not a decrement of `lifetime_earned`); we rejected symmetric or
fall-is-punished conversion because rewarding the fall is the dramatic engine we want.

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — resonance conversion is ABSENT; respect monotonic `lifetime_earned`
