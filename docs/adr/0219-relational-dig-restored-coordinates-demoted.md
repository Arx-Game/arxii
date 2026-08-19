# ADR-0219: Relational dig restored; absolute coordinates demoted to the advanced path

**Status:** Accepted (2026-08-18, #3269 — partially reverses the #2449 design call)

#2449 deliberately dropped the building builder's direction-relative dig from the
staff world builder ("world rooms place by absolute grid cell, not
relative-to-anchor"). Field use authoring Arx's first grid showed why that fails at
bootstrap: coordinates are only meaningful relative to rooms that exist, so an
empty area presents an x/y form that means nothing, and every dig is blind.
Relational dig is now the **primary** flow — a ghost-cell click carries its anchor
room and direction into `staff_dig_room`, which derives the cell and auto-creates
the aliased exit pair from the shared `Direction` spec (moved to
`world.areas.constants` so the two dig flows cannot drift); an empty area's first
room lands at the origin. Absolute x/y remains as the advanced path for annotating
an existing grid. Alternative rejected: keeping coordinates primary with better
labeling — labels don't fix "nothing exists to be relative to."
