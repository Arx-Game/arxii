"""CompanionObject typeclass — a bound companion's in-world presence (#672).

Extends Character (not Object), following the GMCharacter/StaffCharacter
precedent (typeclasses/gm_characters.py) of "a Character subtype that isn't
a player" — Character's handlers already gracefully degrade with no
sheet_data/RosterEntry. Unlike GMCharacter/StaffCharacter, a CompanionObject
is NOT mechanically immune: it should be a valid future combat
target/participant without a typeclass change (#672 spec, Decision #9).
"""

from __future__ import annotations

from evennia.objects.objects import DefaultCharacter

from typeclasses.characters import Character


class CompanionObject(Character):
    """A bound companion's live in-world object."""

    def at_post_move(self, source_location, move_type="move", **kwargs) -> None:
        """Keep Evennia's base post-move hook; skip Character's narrative-agent
        side effects (mission triggers, trap detection, fame reactions, clue
        triggers, sunlight exposure, resonance-alignment reconciliation) that
        assume a real story participant — a companion arriving in a room
        shouldn't spring any of them (#672 spec, Decision #9).
        """
        DefaultCharacter.at_post_move(self, source_location, move_type=move_type, **kwargs)
