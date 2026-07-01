# NPC ontology: Functionary / Standing NPC / Story NPC name the class-1..4 scale; a Functionary is a room-placed class-1 with its own room FK

The codebase's informal `class-1..class-4` NPC scale (referenced throughout `world.npc_services`) gets
canonical names: **Functionary** (class-1 — abstracted, no ObjectDB, no `scenes.Persona`, no persisted
standing), **Standing NPC** (class-2 — a named `Persona` on an unpuppeted Character object, permanently
in a room), and **Story NPC** (class-3/4 — object + full `CharacterSheet`, intended to be GM-piloted for
stories). A **Functionary** is the non-piloted anchor for a room's gameplay loops (mission-giving, permit
approval, mission-reporting, and future room services); it is a *placement* of an `NPCRole` in a specific
room and therefore carries **its own `room` FK** — it has no object from which to derive a location,
unlike Standing/Story NPCs, whose room comes from their Character object. One role has many Functionary
placements across the world (a Builders Guild Clerk in each hall). Making a Functionary into a named,
**owned asset** (the class-1 → class-2 promotion) belongs to the Asset/Companion system (#672): a
Functionary is the rung-1 base that promotion stands on, so it is deliberately **ownerless here** and,
when ownership does enter, reuses `LocationOwnership`'s `{Persona, Organization}` holder discriminator
(`world.locations`) rather than a new owner scheme. We rejected (a) adding a `room` FK to `NPCRole` — a
role is a template instantiated across many rooms, so placement is a distinct row, not a role property;
and (b) representing the abstracted (class-1) case as an ObjectDB FK — Functionaries are deliberately
object-less (that is what distinguishes class-1 from Standing/Story), and the codebase avoids broad FKs
to `ObjectDB` (ADR-0006-style specificity).

> Status: accepted · Source: issue #1766
