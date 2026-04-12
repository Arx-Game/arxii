"""GM and Staff character typeclasses.

These extend Character but are mechanically inert — they cannot be
targeted by combat, spells, or right-click actions. They exist to
represent GM and Staff presence in-game. Fun rejection messages
maintain the spirit of the game.

StaffCharacter has all GM capabilities but without level-based
permission checks. GMCharacter permission checks are deferred to
individual commands that query GMProfile.level.
"""

from typeclasses.characters import Character


class GMCharacter(Character):
    """A GM's in-game presence. Can occupy rooms and interact with players,
    but is immune to all mechanical effects (combat, spells, conditions).

    Permission checks for GM actions are handled by individual commands
    querying the account's GMProfile.level — not by the typeclass itself.
    """

    TARGETING_REJECTION = (
        "The GM gives you a knowing look. "
        "'I appreciate the enthusiasm, but I'm just here to tell the story.'"
    )

    def at_object_creation(self) -> None:
        """Set up GM character defaults on first creation."""
        super().at_object_creation()
        self.locks.add("combat_target:false();give_to:false()")

    def get_targeting_rejection_message(self) -> str:
        """Return a fun message when someone tries to target this character."""
        return self.TARGETING_REJECTION


class StaffCharacter(Character):
    """A staff member's in-game presence. Same mechanical immunity as
    GMCharacter, but exists to host staff tooling commands. Staff bypass
    all GM level checks.

    Not a subclass of GMCharacter — they are orthogonal. Staff tooling
    commands will be added in later phases.
    """

    TARGETING_REJECTION = (
        "The staff character raises an eyebrow. "
        "'Bold move. Unfortunately, I exist outside the narrative.'"
    )

    def at_object_creation(self) -> None:
        """Set up Staff character defaults on first creation."""
        super().at_object_creation()
        self.locks.add("combat_target:false();give_to:false()")

    def get_targeting_rejection_message(self) -> str:
        """Return a fun message when someone tries to target this character."""
        return self.TARGETING_REJECTION
