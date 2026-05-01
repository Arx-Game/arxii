"""Encounter-scoped NPC ObjectDB typeclass.

Owned by a CombatOpponent with `objectdb_is_ephemeral=True`. Created at
`add_opponent` time, destroyed at `cleanup_completed_encounter` time.
Never used for persistent NPCs — those use their existing ObjectDB.
"""

from typeclasses.characters import Character


class CombatNPC(Character):
    """Encounter-scoped NPC. Inherits Character to get .location, attribute
    storage, condition_instances reverse FK, and event-emission targeting.
    """
