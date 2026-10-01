# ADR-4098: An ultimate is a flagged Technique, revealed and chosen at Audere, never a separate record or an auto-cast

**Status:** Accepted (2026-10-01, #4098).

An ultimate is a `Technique` with `is_ultimate=True`, attached to its source (a Path's
major-Gift grant, a patron being, or a companion archetype); a character's discovery of one is
a `KnownUltimate` row, never a `CharacterTechnique`, so every ordinary cast surface that reads
`CharacterTechnique` excludes ultimates by construction. The reveal is derived on read from the
character's current pools (`ultimate_reveal_for`), not an offer table written at accept time;
`KnownUltimate.readied` carries a DB constraint of at most one per character, so a character has
exactly one pick live at a time, cleared on the next Audere accept, a Crossing, or Audere's end.
Choosing an ultimate sets `readied`; it does not cast it - the pick still goes through the
ordinary combat declaration, which admits a readied ultimate only while an active DECLARING
round holds (never clash, never a scene cast), so ultimates are castable only in combat
encounters. An owned known ultimate (the technique sits in any `PathGiftGrant.ultimate_techniques`
for a Gift the character still holds as MAJOR) stays listed in every later Audere regardless of
which Path is current; a bond ultimate (patron, companion) is listed only while that bond is
active, delisting itself the moment it derives from no-longer-active bond state rather than
through any extra check. The reveal's framing line, the deferred-death line, and the three
category display labels live on `AudereThreshold` fields, authored content seeded with a visible
PLACEHOLDER marker, never a string in code. Soulfray's `character_loss` consequence, under a
`death_deferred` condition, sets the new `CharacterVitals.death_certain_pending` instead of
killing synchronously; it resolves through the existing condition-expiry seam when the last
deferring condition ends, backstopped by a cleanup pass at encounter completion, and honors story
protection at both the defer and resolution points. Per the project owner's ruling of 2026-10-01
on #4098, Soulfray can kill only inside a combat encounter: scene casts, technique-enhanced social
actions, battles, and reactive spends with no active COMBAT engagement all pass non-lethal, which
bounds accumulated severity below the first death-risk stage instead of ever rolling a death
consequence.
The Audere Majora round-resolution block, originally an unconditional guard against any round
resolving while a participant was mid-crossing, is narrowed to the undecided-offer window only -
the post-crossing aftermath (the rest of the Majora condition's lifetime) must let the crosser act
on the new Path, and the full-window block froze every later round instead. A dispel that removes
Audere's condition mid-fight resolves a pending certain death right there, not at the encounter's
end - an accepted consequence of tying deferral to the condition's own expiry rather than to the
encounter's. The telnet reveal and choice are guarded by a session snapshot
(`ndb.ultimate_reveal_choice_keys`) of the cards last shown, so `accept ultimate <n>` against a
pool that changed since the last listing is refused and reprinted rather than resolved blind.

We rejected: a separate ultimate catalog (a second payload and cast system duplicating the one
`Technique` already provides); `CharacterTechnique` with an origin flag (every cast surface would
need a filter, and one forgotten filter leaks an ultimate into everyday play); auto-casting the
chosen ultimate (destroys the player's target choice and round timing); a pending-death field on
the combat participant (combat-only, and needs its own resolution seam the condition system
already has); a "doomed" condition as the carrier of certain death (authored content that would
have to exist, and its own dispel or end-of-combat expiry could cure certain death instead of
guaranteeing it); and the original unscoped Audere Majora round block (protected the crossing
moment but froze every round after it, so a crosser could never act on the new Path).

> Status: accepted · Source: issue #4098
