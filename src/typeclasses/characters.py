"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

from django.utils.functional import cached_property
from evennia.objects.objects import DefaultCharacter
from evennia.utils.utils import lazy_property

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

    @lazy_property
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
    def cached_tenures(self):
        """Prefetched active tenures for this character.

        Returns:
            list: Tenures with no end date.
        """
        return list(self.tenures.filter(end_date__isnull=True))

    def do_look(self, target):
        desc = self.at_look(target)
        self.msg(desc)
