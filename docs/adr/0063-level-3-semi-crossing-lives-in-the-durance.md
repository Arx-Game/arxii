# The level-3 (Prospect→Potential) semi-crossing lives in the Ritual of the Durance, not Audere Majora

A character's first path advancement — Prospect→Potential at class level 3 — switches their Path and
grants that Path's gift(s) + starter techniques **through the Ritual of the Durance**, not through an
Audere Majora crossing. Audere Majora (`cross_threshold`) remains the true tier-crossing ceremony at
the authored boundary levels (5/10/15/20 → Puissant/True/Grand/Transcendent); the level-3 transition
is a lesser "semi-crossing" reached by ordinary leveling, so it belongs to the leveling rite. Both
paths converge on one shared seam — `cross_into_path(sheet, path)` (writes `CharacterPathHistory` +
fires `grant_path_magic`) — so a path change can never silently skip its grant. In the Durance,
`_maybe_semi_cross_into_potential_path` fires the seam only when the advance enters a new path stage
**and** the inductee has declared an eligible advanced path (`participant_kwargs["path_id"]`, else
their `PathIntent`); otherwise the advance is level-only (non-breaking — a character may take Potential
later). We rejected adding a level-2 `AudereMajoraThreshold` (it would wrongly stage the full crossing
ceremony — offer/deed/condition — for what is narratively a pre-crossing) and rejected a standalone
semi-crossing command (the Durance already *is* the leveling rite; level 3 is reached by leveling).
This realizes the (Gift × Path) grant leg of ADR-0055 at the level players hit first, honoring ADR-0053
(advancement gates; the grant follows from Path membership per ADR-0050, not an XP purchase) and
ADR-0046 (true tier breakthroughs stay fixed-threshold drama).

> Status: accepted · Source: #1579 design discussion 2026-06-29 · Confidence: built and wired —
> `cross_into_path` + `_maybe_semi_cross_into_potential_path` in `world/progression/services/advancement.py`;
> proven by `world/progression/tests/test_advancement.py::DuranceSemiCrossingTests`.
