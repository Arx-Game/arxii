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

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — generalizes `resolve_effective_role` (`world/covenants/services.py`); Gift×Path and resonance technique-specialization are ABSENT today
