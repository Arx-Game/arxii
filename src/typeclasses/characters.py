"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

from functools import cached_property

from evennia.objects.objects import DefaultCharacter

from commands.utils import serialize_cmdset
from flows.object_states.character_state import CharacterState
from typeclasses.mixins import ObjectParent


class Character(ObjectParent, DefaultCharacter):
    """
    The Character defaults to reimplementing some of base Object's hook methods with the
    following functionality:

    at_basetype_setup - always assigns the DefaultCmdSet to this object type
                    (important!)sets locks so character cannot be picked up
                    and its commands only be called by itself, not anyone else.
                    (to change things, use at_object_creation() instead).
    at_post_move(source_location) - Launches the "look" command after every move.
    at_post_unpuppet(account) -  when Account disconnects from the Character, we
                    store the current location in the prelogout_location Attribute and
                    move it to a None-location so the "unpuppeted" character
                    object does not need to stay on grid. Echoes "Account has disconnected"
                    to the room.
    at_pre_puppet - Just before Account re-connects, retrieves the character's
                    prelogout_location Attribute and move it back on the grid.
    at_post_puppet - Echoes "AccountName has entered the game" to the room.

    """

    state_class = CharacterState

    # Example typeclass defaults for item_data fallbacks
    # These provide sensible defaults when data objects don't exist
    default_height_inches = 70  # 5'10" default height
    default_weight_pounds = 160  # Default weight
    default_build = "average"  # Default build category

    @cached_property
    def traits(self):
        """
        Handler for character traits with caching and lookups.

        This is a cached property that can be cleared by doing:
        del character.traits

        Returns:
            TraitHandler: Handler for this character's traits
        """
        from world.traits.handlers import TraitHandler

        return TraitHandler(self)

    @cached_property
    def sheet_data(self):
        """
        Handler for character sheet data with caching and lazy loading.

        Provides property-based access to character demographics, descriptions,
        and characteristics. Similar to Arx I's item_data system but with
        proper Django models.

        This is a cached property that can be cleared by doing:
        del character.sheet_data

        Usage:
            character.sheet_data.age
            character.sheet_data.eye_color
            character.sheet_data.longname

        Returns:
            CharacterDataHandler: Handler for this character's sheet data
        """
        from world.character_sheets.handlers import CharacterDataHandler

        return CharacterDataHandler(self)

    @cached_property
    def item_data(self):
        """
        Unified flat interface for character data from multiple sources.

        Provides a single access point for character data that may come from
        different storage systems (sheet data, physical dimensions, weights, etc.)
        with fallbacks to typeclass defaults when data objects aren't present.

        This maintains compatibility with Arx I's item_data handler system.

        Returns:
            CharacterItemDataHandler: Unified data handler with descriptors
        """
        from world.character_sheets.handlers import CharacterItemDataHandler

        return CharacterItemDataHandler(self)

    def do_look(self, target):
        desc = self.at_look(target)
        self.msg(desc)

    def at_post_puppet(self, **kwargs):
        """Handle actions after a session puppets this character.

        Args:
            **kwargs: Arbitrary, optional arguments passed by Evennia.
        """
        super().at_post_puppet(**kwargs)
        payload = serialize_cmdset(self)
        for session in self.sessions.all():
            session.msg(commands=(payload, {}))

    def at_post_unpuppet(self, account=None, session=None, **kwargs):
        """Handle cleanup after a session stops puppeting this character.

        Args:
            account: Account associated with the unpuppeting session, if any.
            session: Session that was puppeting this character, if any.
            **kwargs: Arbitrary, optional arguments passed by Evennia.
        """
        super().at_post_unpuppet(account=account, session=session, **kwargs)
        target = [session] if session else self.sessions.all()
        for sess in target:
            sess.msg(commands=([], {}))
