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

**Stables**:
A `RoomFeatureKind` (strategy `STABLES`) that provides an owner-scoped Companion
Capacity bonus scaled by its `level` (#1863). A character with owner or tenant
standing in a room with a Stables gets a flat bonus to their total Companion
Capacity, computed derive-on-read via `stables_capacity_bonus_for_sheet`. Mounts
are beast-domain Companions with `CompanionArchetype.is_mount=True`.

**Mount**:
A beast-domain Companion whose archetype has `is_mount=True` (#1863). No separate
model — a mount uses the existing Companion substrate (bind, capacity, combat).

**Mounted** (#1843):
The rider state: `Companion.ridden_by` points at the rider's `CharacterSheet`
(nullable, unique — one rider per mount), and the rider holds the seeded
"Mounted" `ConditionTemplate` (`world.companions.mount_content`). Set/cleared
by `mount_companion`/`dismount_companion`. Carries **no passive check
bonus** — it exists purely to gate the CHARGE/JOUST combat maneuvers (see
`world/combat/AGENT_GLOSSARY.md`) and the unmounted-Lance penalty. Three
dismount triggers: voluntary, encounter exit, and companion defeat.
_Avoid_: riding (as the state name — "Mounted" is the condition), saddled

**Lance** (#1843):
The `GearArchetype.LANCE` weapon archetype — a `WEAPON_ARCHETYPES` member
required to declare JOUST and to double CHARGE's bonuses. Wielding a Lance
while not Mounted incurs `LANCE_UNMOUNTED_PENALTY` on any attack.
_Avoid_: spear, pike (distinct gear concepts, not this archetype)
