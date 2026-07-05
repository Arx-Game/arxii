# Story-Critical NPC Protection — structural death prevention for load-bearing NPCs

A GM can declare that an NPC is load-bearing for a player's story via a
`StoryNPCDependency` row (FK to `Story`, optionally to a specific `Beat`).
When an actor external to that story — someone who is not a
`StoryParticipation` member of any dependent story — attempts to kill the NPC
in combat, the death is structurally prevented: the NPC flees (health floored,
`OpponentStatus.FLED`, moved out of the room) rather than dying. The attacker
gets a generic OOC message to narrate a plausible survival reason; online
staff get a detailed notification listing the affected stories. The story
owner is never notified — protection is silent, preserving the possibility
that the NPC is a secret antagonist.

The protection is a parallel gate to `death_deferred` (condition-based
temporary protection) — both are independent checks in the death-gate sequence.
The primary integration is `apply_damage_to_opponent` (the NPC combat death
path, where the existing `HERO_KILLER` tier is the precedent for NPC narrative
immunity). The secondary integration is `death_is_permitted` (post-combat
peril resolution: bleed-out, abandonment, surrounded).

Death is the first implemented removal vector. The model is designed so
charming, capture, and banishment can hook into the same
`is_death_prevented_by_story` check in follow-up issues.

> Status: accepted · Source: issue #1874
