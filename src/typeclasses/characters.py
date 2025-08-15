"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

from functools import cached_property

from django.utils import timezone
from evennia.objects.objects import DefaultCharacter

from commands.utils import serialize_cmdset
from flows.object_states.character_state import CharacterState
from flows.service_functions.serializers import build_room_state_payload
from typeclasses.mixins import ObjectParent
from world.roster.models import RosterEntry


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
    def item_data(self):
        """
        Comprehensive character data interface.

        This is the main data access point for characters, providing:
        - Character sheet data (age, gender, concept, family, etc.)
        - Display data (longname, descriptions)
        - Characteristics (eye_color, height, etc.)
        - Future: Classes data (levels, abilities)
        - Future: Progression data (experience, advancement)

        Replaces the old sheet_data handler - all character data should be
        accessed through item_data for consistency.

        Usage:
            character.item_data.age           # Sheet data
            character.item_data.longname      # Display data
            character.item_data.eye_color     # Characteristics
            character.item_data.quote         # Sheet data

        Returns:
            CharacterItemDataHandler: Comprehensive character data handler
        """
        from evennia_extensions.data_handlers import CharacterItemDataHandler

        return CharacterItemDataHandler(self)

    def do_look(self, target):
        desc = self.at_look(target)
        self.msg(desc)

    def at_post_puppet(self, **kwargs):
        """Handle actions after a session puppets this character.

        Updates the roster entry with the time this character entered the game.

        Args:
            **kwargs: Arbitrary, optional arguments passed by Evennia.
        """
        super().at_post_puppet(**kwargs)
        try:
            entry = self.roster_entry
        except RosterEntry.DoesNotExist:
            entry = None
        if entry:
            entry.last_puppeted = timezone.now()
            entry.save(update_fields=["last_puppeted"])
        payload = serialize_cmdset(self)
        for session in self.sessions.all():
            session.msg(commands=(payload, {}))

        # Execute look command to send room state to frontend via flow system
        self.execute_cmd("look")

    def send_room_state(self):
        """Send current room state to this character's frontend.

        Uses the scene_state properties to get current state information.
        Falls back to executing 'look' command if state retrieval fails.
        """
        if not (self.has_account and self.location):
            return
        caller_state = self.scene_state
        room_state = self.location.scene_state
        if caller_state and room_state:
            payload = build_room_state_payload(caller_state, room_state)
            self.msg(room_state=((), payload))

    def at_post_move(self, source_location, move_type="move", **kwargs):
        """Handle actions after moving to a new location.

        Sends updated room state to the frontend after movement.
        """
        # Call parent method to handle trigger registration
        super().at_post_move(source_location, move_type=move_type, **kwargs)

        # Send room state to frontend
        self.send_room_state()

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
