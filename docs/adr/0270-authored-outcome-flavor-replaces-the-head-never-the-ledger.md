# Authored outcome flavor replaces the head sentence, never the ledger

**Issue:** #3554 · **Related:** ADR-0187 (concealment hides attribution, not the event), ADR-0072 (signature motif bonus is additive)

## Context

Every resolved combat action is narrated by the Narrator persona as one OUTCOME line, and
that line is the only durable, room-visible record of what happened (#557). Staff wanted
techniques and NPC attacks to read differently from one another. The tempting design was a
whole-line template per technique. That would let an author drop the damage figure or the
knockout clause, and the line would stop being a record players can trust.

## Decision

`Technique` and `ThreatPoolEntry` carry `hit_narration` and `miss_narration`, each with
`{actor}` and `{target}` placeholders (both required, literal substitution). The authored
text replaces only the head sentence. On a hit the machine still appends " for N damage",
the wound, dying, knockout and defeat clauses, and the ward, signature and synergy clauses.
On a miss the authored line replaces "X's Y misses Z" and the suffix clauses still follow.
Blank means the default sentence. The concealed observer tiers never receive the authored
head, because it is an attribution tell exactly like the signature clause.

## Rejected

A whole-line template per technique, because it lets flavor overwrite the ledger. A GM
free-text field on the round result, because the composer already lands in the same feed
and the fixed Narrator line is the fair record.
