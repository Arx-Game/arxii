# ADR-4097: A thread on a prerequisite technique empowers what it unlocks, at full level

**Status:** Accepted (2026-10-01, #4097).

A thread woven into technique A also empowers every technique A is a transitive
`TechniqueKnownRequirement` prerequisite for, at the thread's full level, read on
demand through the prerequisite closure (`prerequisite_technique_ids`) inside the
existing in-action predicate (`_anchor_in_action`), not a new mechanism. We decided
this because early investment in a foundational technique must never be wasted the
moment a character learns what it unlocks, including a hidden ultimate several hops
downstream; punishing the natural order of acquisition (learn the foundation, invest
in it, then learn what it gates) would make investing early a trap. We rejected
moving or copying a thread's investment onto the newly learned technique (destroys
the provenance of where the investment was made, and complicates re-deriving it if
the prerequisite chain changes), a stored/denormalized carried total (another cache
to keep in sync with the prerequisite graph, instead of deriving it on read per
ADR-0014's precedent), and widening the ambient passive-capability sweep
(`_anchor_ambiently_active`) in the same change (that sweep demands demonstrable real
state for a free contribution; carry is scoped to the paid in-action predicate only).

> Status: accepted · Source: issue #4097
