# Resonance-as-drift: compromising acts grant spendable non-native resonance

When a character's actions pull them away from their native affinity — a
Celestial killing in combat, a Primal inflicting cruelty — the system grants
**real spendable `CharacterResonance`** in the non-native type. No separate
"moral compromise" tracking model is created; the existing
`CharacterResonance.balance` + `lifetime_earned` rows ARE the drift tracker.
`recompute_aura` (which sums `lifetime_earned` by affinity) shifts the aura
percentages automatically, and `AuraAffinityThreshold` fires achievements
when an affinity percentage crosses an authored threshold.

This is the simplest possible expression of the "compromise chips away at
your nature" design: compromising acts are a new `GainSource.COMPROMISE`
that writes through the existing `grant_resonance` path. The Fall is then a
one-time conversion ceremony (ADR-0054) that converts accumulated resonance
+ threads to a new affinity with an asymmetric multiplier.

We rejected a separate drift/compromise tracking model (Option B in the
brainstorm) because it would duplicate `CharacterResonance`'s architecture
and create two parallel "you're drifting" signals. We also rejected a
separate "drift value" field that affects aura but isn't spendable (Option B
in the unified-model question) because spendable resonance is more tempting
— a character who has accidentally invested in Primal threads can spend
them, which makes the Fall more dramatically motivated.

**Monotonicity note (revised after spec review):** ADR-0054 stated
"lifetime_earned is monotonic" to prevent earn-rate gaming. The Fall
conversion transfers `lifetime_earned` from the source to the target
(scaled by the multiplier) rather than decrementing it — the total is
preserved modulo the multiplier. This is necessary because `recompute_aura`
reads `lifetime_earned`, not `balance`; preserving the source's
`lifetime_earned` would leave the aura stuck on the old affinity. The
transfer is a one-time act on an irreversible conversion, not a claw-back
that could be re-earned through perception sources.

Compromise grants are in `NON_ACCELERATED_GAIN_SOURCES` (they are not
perception/presence-driven gains), so they don't undercut ADR-0041's
earning loop.

> Status: accepted · Source: design discussion 2026-07-14 · Confidence: high — reuses existing `grant_resonance` / `recompute_aura` / `AuraAffinityThreshold` machinery
