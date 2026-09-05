# ADR-0271: Declined and fizzled reactions stay mechanical no-ops but always narrate to the actor

**Date:** 2026-09-04
**Status:** Accepted (amends ADR-0161)
**Issue:** #3574

## Decision

A reactive protection that does not fire (technique-guardian fizzle for want of
anima, a reaction declined by `REACTIONS_PER_ROUND` or `ABSORPTION_CAP_PER_MOMENT`,
a standing ward that cannot pay its `reactive_anima_cost`, a ward that lapses at
upkeep) keeps the exact mechanical no-op shape it has: no roll, no charge, damage
proceeds, the instance is deleted. What changes is that the actor is always told,
privately, through `world.scenes.interaction_services.narrate_privately` (a
Narrator whisper on both the WebSocket interaction payload and telnet), and the
room gets one soft line without numbers where the table could see something fail
(a guardian's working failing to catch, a visible ward going out). Budget declines
narrate privately only.

## Why

ADR-0161 said a declined reaction returns "the same did-not-fire no-op shape, no
new UI state, no new error path." That was a ruling about mechanics and about not
leaking a guardian's budget to the table. It was being read as "and do not tell
the player," which left a guardian not knowing their save had failed, a caster not
knowing their ward had lapsed, and the room seeing a hit land as if no one had
tried (#3574). A private line is not new UI state: it rides the existing
interaction feed. The alternative, a new "fizzled" flag on the round payload for
the client to render, was rejected because it would need a second representation
of an event the interaction log already carries, on both clients.
