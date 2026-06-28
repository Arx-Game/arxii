# Gift strength comes from the thread woven into it (the costliest thread kind)

A character grows stronger in a gift — unlocking more, and more-powerful, techniques — through the
**thread woven into that gift**, so you deepen a species or minor gift by investing its thread; and
because that gift-thread fundamentally gates a character's magical power, it is the **most expensive
thread kind** to raise. We rejected level-driven gift power: ADR-0046 keeps tier *breakthroughs* as
fixed-threshold drama while thread depth is the continuous within-tier strength axis — tying power to
a woven thread keeps magical strength earned through invested RP rather than handed out by leveling.
Today threads cannot target a `Gift` (the `TargetKind` set has no GIFT) and thread cost varies by
tier/level/path but never by target kind, so both the gift anchor and the per-kind cost are new build. This gift-thread is the gift-side
instance of the shared specialization engine (ADR-0055): at thread level 3 the gift grants techniques
customized to the character's specific resonance, in parity with covenant sub-roles. The gift-thread is the *primary* power axis; an optional
per-technique "signature" thread adds depth to a single technique above this baseline (ADR-0056).

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — GIFT thread anchor + per-target-kind cost are ABSENT
