# NPC services glossary

**NPC ontology (class-1..4 scale — canonical names, ADR-0070):**

**Functionary**:
A **class-1** NPC — abstracted, non-piloted, with no ObjectDB and no `scenes.Persona`. It serves a
room role (enables gameplay loops there: mission-giving, permit approval, mission-reporting, future
services) and is a *placement* of an `NPCRole` in a room, so it carries its own `room` FK (there is no
object from which to derive its location). One role has many Functionary placements (a Builders Guild
Clerk in each hall). Rarely staff-pilotable (a beloved fixture puppeted for a scene); normally unpiloted.
Promotion into a named, owned asset is the Asset/Companion system's job (#672).
_Avoid_: room NPC, giver, class-1 NPC (for the surface term), nameless functionary.

**Standing NPC**:
A **class-2** NPC — a named `scenes.Persona` on an unpuppeted Character object, permanently in a room.
Has persistent `NPCStanding` (per-PC affection). Room comes from its object, not a placement FK.
`NPCStanding` is kept separate from `NpcRegard` (which covers an NPC's opinion of orgs/societies
and is not scoped to PC targets) — `NPCStanding` is specifically the
PC-persona-vs-NPC-persona offer-eligibility gate; see ADR-0085.
_Avoid_: class-2 NPC, named NPC.

**Story NPC**:
A **class-3/4** NPC — a Character object with a full `CharacterSheet`, intended to be piloted/roleplayed
by staff or GMs for stories.
_Avoid_: class-3 NPC, class-4 NPC, major NPC.

**NPCRole**:
The staff-authored **catalog** entry ("Builders Guild Clerk", "Town Guard") — a bundle of
`NPCServiceOffer` rows. A role is a template, room-less and owner-less; a Functionary is a placement of
one. Not the placement itself.

**NPCServiceOffer**:
One offerable thing on a role, of a `kind` (`OfferKind`: PERMIT, MISSION, …) with a per-kind details
model + effect handler. The single "ask an NPC for a thing" surface, ridden via the `hire` /
`InteractionSession` loop. Building-permit approval is `kind=PERMIT`.

**NpcRegard** — A notable NPC's signed opinion (`-1000`..`1000`) of another
persona (PC or NPC), an Organization, or a Society. General axis: positive is
favor, negative is hostility — there is no separate "enemy" model. Holder is
always a notable NPC's `Persona` (v1; org/society-as-holder is a future
extension of the same discriminator, not built). Deliberately separate from
`NPCStanding` — see that entry's cross-reference and ADR-0085.
_Avoid: "NpcEnmity" (collides with the dead `ThreadAxis.ENMITY`), "grudge" as a
model name (implies negative-only; fine as informal narration of a strongly
negative row)._
