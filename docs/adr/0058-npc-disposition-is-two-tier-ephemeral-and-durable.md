# NPC disposition is two-tier: ephemeral for mooks, durable for named NPCs, with persona-promotion as the seam

An NPC's disposition toward a character is stored in two tiers keyed on whether the NPC is a real
identity or an ephemeral mook: **durable** — `npc_services.NPCStanding.affection` (per-(PC persona,
NPC persona)) for Persona-bearing NPCs; **ephemeral** — a session/scene-scoped store (mirroring the
in-memory `InteractionSession`/`request.session` pattern) for persona-less NPCs outside combat, and
the `CombatOpponent` row for them inside combat. The single seam between the tiers is
`combat.services.has_persistent_identity_references` (true iff the ObjectDB has a CharacterSheet,
Persona, or RosterEntry): when an ephemeral mook is promoted to real — staff authoring, or the
"charmed him and he followed me home" retention path — minting that identity row is what flushes
ephemeral disposition into durable `NPCStanding`. We rejected a single uniform disposition model
(keyed on `(CharacterSheet, target-Character/ObjectDB)` to reach mooks directly): it would collide
with ADR-0038's asymmetrical-PvE tenet that NPCs have no sheets and would persist rows for
encounter-scoped mooks that self-clean today, and it would re-key `NPCStanding`. We also rejected a
lighter "retained" flag parallel to persona-promotion (ADR-0016 parallel-impl smell). The
two-tier model extends ADR-0038 (mooks stay un-sheeted; only promotion gives them a sheet) and sits
on the un-consented side of ADR-0024 (charm on an NPC alters a non-player's behavior — no PC agency
to gate). The threat-read that *consumes* disposition in combat is the spec's design work, not part
of this storage decision.

> Status: accepted · Source: issue #1590, #1591 · Confidence: high (storage seam verified against code: `combat/services.py` `has_persistent_identity_references` line 138, ephemeral-ObjectDB deletion ~line 3700; `npc_services/services.py` `InteractionSession` line 104 + `views.py` `request.session` line 60)
