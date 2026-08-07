# 0205. Ritual anima pools replace a spell system; anima is a level-scaled, blood-payable economy

**Date:** 2026-08-07 · **Issue:** #3001 · **Status:** Accepted

All PCs are Gifted, which dissolved #3001's original "hedge magic for quiescent characters"
rationale. Instead of a parallel `Spell` model (already ruled out on the roadmap), rituals became
the home of generalized magic: a `Ritual` carries an `anima_requirement` and **the price is the
only gate** — no Gifted-check anywhere in the ritual framework. The pool fills from any mix of
channeling (own anima), prick (1, trivial damage), gash ((1d6+1)×level, a real wound), or
sacrifice (a victim drained; a killing drain yields `death_harvest_multiplier` (20) × the victim's
full maximum — the metaphysical engine of ritual murder, and why anima-feeders are tempted to
finish victims). Underfilled pools roll the ritual's check at a deficit-bumped difficulty;
overfilled (≥2×) unlocks a spectacular tier. Blood extraction is affinity-neutral; the *method*
taints, via authored `CompromiseActType` rows (murder +5 Praedari; essence-kind seduction feeding
+1 Insidia +1 Praedari). To make the economy real, anima maximum scales with level (10 at level 0,
100×level after) and regen collapsed from percentage to a flat +1/day (appetite holders 0 or
−1/day toward authored floors, one system) — recovery rituals, feeding, and blood ARE the refill
economy. Rejected alternatives: a separate `Spell` model (parallel pipeline sprawl); per-species
regen modes (duplicates `AppetiteUpkeep`); a Gifted-gate on rituals (the price gates better and
keeps hedge-witch fiction alive); percentage regen (made big pools self-refilling and hollowed
out the recovery economy). "Spell" remains an in-prose synonym for ritual — never a model or
mechanical term.
