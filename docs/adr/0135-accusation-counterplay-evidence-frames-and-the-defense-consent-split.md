# ADR-0135: Accusation counter-play — evidence-grown frames, and defense needs no consent

**Status:** Accepted (Apostate, 2026-07-14) · **Refs:** #1825, #2170, ADR-0023, ADR-0114, #2378

Two decisions shape the accusation counter-play loop. **(1) Heavy frames only grow from
real crime evidence.** The originally-specced "assemble false evidence from nothing"
Project was rejected: a crime-tagged deed with a located scene generates physical
`CrimeEvidence` (a real inventory item once gathered — hand-offs, theft, and future
planting ride the item system), and the L3 frame is that evidence *perverted* through a
Workshop-of-Iniquity FRAME_JOB project. This keeps the emergent-tier design of #2212
(wild L2 = no deed; L3 = a real deed misattributed) honest — an L3's robustness comes
from a crime that genuinely happened — and gives criminals the symmetric dispose choice
(destroy the trail instead of weaponizing it). **(2) The consent gate splits on target,
not topic (the Tom/Bob/Fred rule).** Defending the accused — refuting the accusation,
investigating, nullifying — needs NO consent from anyone: the framer opted into the
arena by minting, and blocking defense would let consent settings protect a weapon.
But *turning the frame back on its author* (denouncing with the unmasked authorship
secret) re-checks `accusation_permitted` against the **framer's** own hostile category:
two friends playing consensual antagonists must not license a third party who hates one
of them to weaponize the authorship and drive them off the game. Rejected alternative:
treating the mint itself as blanket opt-in to counterattack — explicitly refused because
it converts one consensual rivalry into open season. Lethal outcomes and the enforcement
pipeline stay out of player hands entirely (automated justice, #2378).
