"""GM and Staff character typeclasses.

These extend Character but are mechanically inert — they cannot be
targeted by combat, spells, or right-click actions. They exist to
represent GM and Staff presence in-game. Fun rejection messages
maintain the spirit of the game.

StaffCharacter has all GM capabilities and also represents staff as
"head GM" for story attribution. Both are allowed to run stories
(see Story.active_gms).

NOTE: The combat_target and give_to locks added here are aspirational
— combat commands and interaction systems will need to respect them
when built. The lock type `combat_target` has no consumer yet.
"""

from typeclasses.characters import Character


class _MechanicallyImmuneCharacterMixin:
    """Shared behavior for characters that are immune to mechanical effects."""

    TARGETING_REJECTION = ""

    def at_object_creation(self) -> None:
        """Set up immunity locks on creation."""
        super().at_object_creation()
        self.locks.add("combat_target:false();give_to:false()")

    def get_targeting_rejection_message(self) -> str:
        """Return a fun message when someone tries to target this character."""
        return self.TARGETING_REJECTION


class GMCharacter(_MechanicallyImmuneCharacterMixin, Character):
    """A GM's in-game presence. Can occupy rooms and interact with players,
    but is immune to all mechanical effects (combat, spells, conditions).

    Permission checks for GM actions are handled by individual commands
    querying the account's GMProfile.level — not by the typeclass itself.
    """

    TARGETING_REJECTION = (
        "The GM gives you a knowing look. "
        "'I appreciate the enthusiasm, but I'm just here to tell the story.'"
    )


class StaffCharacter(_MechanicallyImmuneCharacterMixin, Character):
    """A staff member's in-game presence. Same mechanical immunity as
    GMCharacter, but exists to host staff tooling commands. Staff bypass
    all GM level checks and run stories as the "head GM."

    Not a subclass of GMCharacter — they are orthogonal, but both are
    valid for Story.active_gms.
    """

    TARGETING_REJECTION = (
        "The staff character raises an eyebrow. "
        "'Bold move. Unfortunately, I exist outside the narrative.'"
    )
