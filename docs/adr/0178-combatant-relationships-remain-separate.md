# Combatant relationship models remain separate — no shared base

EngagementLock (pairing), Clash (metered contest), and CombatMark (round-scoped
pointer) share column names (encounter + combatant FKs) but are three distinct
concepts, not parallel implementations of one. The shared surface is too thin
to carry behavior — the deletion test shows complexity vanishes if a
hypothetical `CombatantRelationship` base is removed (it would be a one-field
abstract base with no behavior), and no consumer ever cross-queries them as "all
relationships for this encounter." Clash already carries its own internal
`flavor` discriminator (CLASH/LOCK/WARD/BREAK) with iff-coupled fields and
CheckConstraints; an outer `kind` discriminator would create a
discriminator-on-discriminator. Even the FK targets differ: Clash's PC-side is
`initiator`→CharacterSheet (who started, not exclusive), while the other two use
`participant`→CombatParticipant (the exclusive combatant). A shared concrete
table would be the GenericFK-adjacent pattern ADR-0015 rejects; forcing a base
for distinct concepts is not the convergence ADR-0016 intends (its qualifier is
"single concept," and ADR-0094 already established pairing ≠ struggle). The
three alternatives considered and rejected: (1) Python abstract base — only
`encounter` is truly shareable, a one-field base with no behavior; (2) single
concrete table with `kind` discriminator — discriminator-on-discriminator,
massive nullable column waste, every partial unique becomes kind-conditional;
(3) keep separate — chosen.

> Status: accepted · Source: #2674 (extends ADR-0094, ADR-0015, ADR-0016)
