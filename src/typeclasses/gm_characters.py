"""GM and Staff character typeclasses.

These extend Character but are mechanically inert — they cannot be
targeted by combat, spells, or right-click actions. They exist to
represent GM and Staff presence in-game. Fun rejection messages
maintain the spirit of the game.

StaffCharacter has all GM capabilities and also represents staff as
"head GM" for story attribution. Both are allowed to run stories
(see Story.active_gms).

NOTE: Mechanical immunity is signalled via the class attribute
``is_mechanically_immune``. Combat, interaction, and targeting code
should check ``getattr(target, "is_mechanically_immune", False)`` and
display ``target.get_targeting_rejection_message()`` when True. No
Evennia locks are involved — this is a plain Python attribute check.
"""

from typeclasses.characters import Character


class _MechanicallyImmuneCharacterMixin:
    """Shared behavior for characters immune to mechanical effects.

    Future combat, interaction, and targeting code should check
    `getattr(target, "is_mechanically_immune", False)` and display
    `target.get_targeting_rejection_message()` when True.
    """

    is_mechanically_immune: bool = True
    TARGETING_REJECTION: str = ""

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
