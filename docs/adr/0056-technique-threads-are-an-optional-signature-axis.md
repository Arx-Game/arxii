# Technique-threads are an optional "signature" axis, distinct from the gift-thread

We keep threads that target an individual technique (`TargetKind.TECHNIQUE`) but give them one narrow
purpose — a **signature**: optional extra depth and strength in a *single* chosen technique, raised
**above** the gift's baseline ("I have poured myself into this one spell"). Responsibilities split by
**scope**, not by withholding resonance: the **gift-thread** sets a gift's overall power and the
**default** resonance/affinity + specialized form of *all* its techniques (ADR-0051, ADR-0052,
ADR-0055); a **signature thread** governs only its one technique, where it adds depth **and** — like
every thread — carries its own **resonance**, which usually matches the gift but **may deliberately
diverge**, letting a single technique manifest as a different affinity than its gift (a *discordant
signature*). So a technique resolves on read as (gift baseline + optional signature delta), the
signature's resonance overriding the gift's for that one technique, and both re-specialize live on a
Fall/Redemption (ADR-0014, ADR-0054). We rejected gift-thread-only (loses the signature) and a
resonance-less signature (every thread has resonance, and forbidding divergence would kill the most
interesting case — one technique that breaks from your gift's affinity). Today `TargetKind.TECHNIQUE`
is wired for a broader role — verify what it currently feeds and re-scope it to the signature delta.

> Status: **superseded by ADR-0065** · The resonance-divergence model described here was replaced by the motif-bonus model (additive flourish, not a discovered variant). See ADR-0065 for the decision and the invariants that apply.
