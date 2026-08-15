# ADR-0215: Public conversion historicizes the old faith instead of retiring it, and heart-vs-lip-service is a boolean flag, not a new model

**Status:** Accepted (2026-08-15, #2361 — ratified by ApostateCD in the post-CG worship conversion spec review)

A public conversion (`CeremonyTypeKey.CONVERSION`) repoints
`WorshipDeclaration.public_being` and leaves everything else about the character's prior
faith standing exactly as it was: `DevotionStanding` favor with the old being is never
zeroed or deleted, and an old secret faith's minted `Secret` row is never mutated,
retired, or given a new lifecycle field — it stays a true, discoverable historical fact
("was secretly a cultist of X before conversion"), unchanged in `content`, `level`, or
any other column. The heart-vs-lip-service choice (does the character believe the new
public faith, or is it performative) is a single `public_is_sincere` boolean on
`WorshipDeclaration`, private to owner/staff (same leak-table pattern as `current_mood`).

**Rejected: a Secret status/lifecycle field ("retired"/"historical").** `Secret` is an
append-only fact ledger by design (`expose_secret` tracks *exposure*, not *validity*); a
status field would be the first crack in that invariant and would need every other
Secret-reading surface (blackmail, investigation, `expose_secret`) to learn a new state
it doesn't currently need to know about. Leaving the row untouched achieves the same
narrative result — "was secretly devoted to X" stays real and discoverable — with zero
new surface.

**Rejected: a `true_faith`/`public_faith` split (two `WorshippedBeing` FKs) for
sincerity.** The inward truth isn't necessarily belief in a *different specific being* —
a lip-service convert may believe in nothing, may still privately hold the old faith, or
may simply be play-acting without a settled alternative. A boolean captures exactly what
the amendment asked for (does the public act reflect the heart or not) without forcing a
second FK to always resolve to *something*, and without duplicating the FK-nullability
questions `WorshipDeclaration.secret_being` already answers for the genuinely-separate
secret-faith case.

**Rejected: minting new `PhilosophicalArchetype` rows for old→new conversion framing.**
The #1464 scandal vocabulary (`world/seeds/scandal_archetypes.py`) is a small,
deliberately curated, Apostate-authored set with an explicit "no edgelord societies"
design ruling. Conversion reuses the existing "Treacherous Scandal" archetype (broken
vows) for any conversion away from an already-declared public faith, rather than
authoring new per-tradition archetype rows — narrower framing (e.g. a distinct
"Heretical" tag for conversion to a specific reviled power) is left to Apostate's future
content pass, not designed here.
