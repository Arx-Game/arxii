# One specialization engine: resonance × entity → customized techniques (parity across Gift, Path, Covenant Role)

A character's specialized techniques and capabilities are resolved by combining an entity they hold —
a **Gift**, a **Path**, a **Covenant Role** (and future Vows) — with their **resonance** (and, where a
thread is woven, that thread and its level) through **one shared specialization primitive**, not
per-entity bespoke logic: the combination of (Gift × Path) sets the base technique set and the
character's resonance specializes how those techniques manifest, exactly as
(Covenant Role × anchored-thread resonance × thread level) already resolves a specialized sub-role
today. At a threshold (≈ thread level 3) the grant becomes **customized to the character's specific
resonance**, so the same Gift/Path/Role yields a staggering number of unique builds across resonances —
the combinatorial space (resonance × {gift, path, role}) IS the product. We generalize the one proven
instance — `resolve_effective_role` (covenant sub-roles, the only working axis-combination in the
codebase) — into a shared engine per ADR-0016, rejecting three parallel per-entity specialization
systems because only a shared primitive keeps the explosion of combinations consistent and tractable. The
specialized form is **derived on read** from the character's current gift/path/resonance/thread
state, never snapshotted (ADR-0014) — so a change of resonance (a Fall or Redemption, ADR-0054)
instantly re-specializes every affected technique to the new resonance's version, with no
regeneration step.

> Status: accepted · Source: design discussion 2026-06-27 · **Realized in #1578** — `AbstractSpecializedVariant` shared base + `TechniqueVariant` (Gift techniques) + `CovenantRole` (refactored to inherit); `resolve_specialized_variant(entity, character)` is the one resolver (`resolve_effective_role` is now a shim); `fire_variant_discoveries` generalizes the discovery ceremony across `target_kind`. The GIFT thread substrate (`TargetKind.GIFT` + `Thread.target_gift` + latent provisioning + `gift_resonances_for`) is proven end-to-end by `test_gift_specialization_e2e.py`. · Confidence: built and wired
