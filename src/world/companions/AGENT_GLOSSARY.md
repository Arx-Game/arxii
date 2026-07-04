# Companions glossary

**Companion**:
The persistent, room-present bound creature a PC has created/tamed/raised
(`Companion` model). Reserved term — never use "familiar," "pet," or "summon"
for this row (see `world/combat/AGENT_GLOSSARY.md`'s Summon entry, which
explicitly avoids "companion" for the in-combat ally row, and vice versa here).

**Companion Archetype**:
The staff-authored catalog row (`CompanionArchetype`) a `Companion` is an
instance of — e.g. "Direwolf." Binding is archetype-selection: a PC picks an
archetype and narrates the encounter; there is no separate in-room "wild
creature" object a bind attempt targets.

**Companion Capacity**:
The proficiency-gated pool limiting how many/how costly a PC's active
companions can be, computed from their granting Gift's Thread level via the
existing `ThreadPullEffect` mechanism — always say "Companion Capacity" in
full; bare "Capacity" is the `world.relationships` track-ceiling term.
_Avoid_: capacity (unqualified), companion count, pet slots.

**Bind** (verb):
The acquisition action for a Companion. _Avoid_: summon (reserved for the
in-combat `CombatOpponent` ally row, ADR-0059).
