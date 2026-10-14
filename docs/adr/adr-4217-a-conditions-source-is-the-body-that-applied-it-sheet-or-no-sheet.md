# ADR-4217: A condition's source is the body that applied it, sheet or no sheet

**Status:** Accepted (#4217, 2026-10-14). Amends the #2608 audit's verdict table (tranche 4,
which marked `ConditionInstance.source_character` for a retarget at `CharacterSheet`).

**Context.** #2608 triaged every relation field pointing at `ObjectDB`. Two of its five
leftovers were body-axis fields it marked for a retarget: `Scene.location` at `RoomProfile`
(done in #4217: the profile shares the room's pk, `Scene.room` hands back the Evennia object
for presence, broadcast and teardown work) and `ConditionInstance.source_character` at
`CharacterSheet`, on the reasoning that who applied a condition is a fact about the body, not
the face. The second verdict assumed every source has a sheet. The combat code says
otherwise: `CombatOpponent.objectdb` keeps `ObjectDB` precisely because a generic or
ephemeral NPC has no `CharacterSheet` by design, `npc_action` records that object as the
source of the damage a mook deals, `death_is_permitted` refuses a `None` source, and
`is_pc_source` reads a sheetless source as an NPC on purpose (#4091).

**Decision.** `source_character` stays an `ObjectDB` foreign key, tokened as a keeper with
this rationale, and `conditions/models.py` joins the `objectdb-param` hook's scope on the
keeper path. A sheet-typed field would null the source on every mook-applied condition, and
through the death gate make every mook kill impossible, inverting ADR-0023 (PvP is
non-lethal; NPC lethality stays). A reader that wants the character's sheet asks the object
for it (`source_character.character_sheet`, `None` for a mook), which is what the readers
already do.

*Rejected:* retargeting and giving mooks a sheet so the field has something to point at. A
sheet is a character's whole record (vitals, persona, roster tenure); minting one per
ephemeral body would make the roster and every sheet-scoped query carry disposable rows for
the sake of a foreign key's type.
