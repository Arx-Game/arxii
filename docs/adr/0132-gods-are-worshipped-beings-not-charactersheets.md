# ADR-0132: Gods are WorshippedBeing rows with optional avatar sheets, not CharacterSheets

**Status:** Accepted (2026-07-13, #2355/#2289 — ratified by ApostateCD in the ceremonies/worship brainstorm)

Worshippable gods/spirits/powers are `worship.WorshippedBeing` rows — a dependency-free
primitive holding a vast accumulating `resonance_pool` — with a nullable OneToOne
`avatar_sheet` for the rare god a trusted GM actually plays. The PC↔god relationship is a
one-way `DevotionStanding` (sheet, being, favor), not a `CharacterRelationship`.

**Rejected: gods as NPCs with CharacterSheets.** It would have reused `CharacterResonance`
(the pool) and `CharacterRelationship` (the bond) for free, but both are the wrong shape:
`CharacterResonance` is a spendable per-resonance-type balance tuned to weekly player-scale
gains, not a divine hoard; `CharacterRelationship` is two-way social machinery (tracks,
tiers, conditions) for people, and its FKs are hard-typed sheet↔sheet. Sheets also drag
vitals/skills/CG baggage onto entities that are mostly setting-data — and the trust model
is that only Apostate and a handful of others ever play a god, so most beings must be
authorable rows, not pseudo-characters. A manifested god opts into the full character
machinery via `avatar_sheet` at that moment; nothing pretends beforehand.
