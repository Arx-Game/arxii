# ADR-4675: A stunt is a feature's challenge template, rolled like the held-ground pass

**Date:** 2026-10-26
**Status:** Accepted
**Issue:** #4675 (slice 3 of #4651)

## Decision

A stunt uses a feature in the character's own place to reach another place. Staff author a
catalog of `FeatureType` rows (art, a `FeatureReach` rule and a `ChallengeTemplate`) and attach
them to places; `perform_stunt` mints a one-shot instance of the template in the room, resolves
it with the approach her capabilities match best (the same shape as the held-ground pass of
ADR-4663), deactivates it, and moves her unless she missed. A miss leaves her in place with the
template's authored consequences, and every try spends a hop in a declaring round. No prone
condition is coded and NPCs do not use features: consequences are staff content, and NPC
movement is traversal based. We rejected a `CHALLENGE`-backend entry per live feature instance:
resolving one moves no one and spends no hop, so the move, the miss and the hop would each need
separate code beside it. We also rejected features authored per room: the owner chose a catalog
that staff define once and attach anywhere, which a GM can also do mid-fight.
