"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.objects.objects import DefaultCharacter

from commands.utils import serialize_cmdset
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import AttackLandedPayload, MovePreDepartPayload
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
                    object does not need to stay on grid. Echoes "Account has
                    disconnected"
                    to the room.
    at_pre_puppet - Just before Account re-connects, retrieves the character's
                    prelogout_location Attribute and move it back on the grid.
    at_post_puppet - Echoes "AccountName has entered the game" to the room.

    """

    #: Mechanical immunity marker. Characters with this set to True are
    #: inert to combat, targeting, conditions, and other mechanical effects.
    #: GMCharacter and StaffCharacter override this to True.
    is_mechanically_immune: bool = False

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
    def stats(self):
        """
        Handler for primary character statistics.

        Provides access to the 8 primary stats (strength, agility, stamina,
        charm, presence, intellect, wits, willpower) with stat-specific
        methods wrapping the generic traits system.

        This is a cached property that can be cleared by doing:
        del character.stats

        Returns:
            StatHandler: Handler for this character's stats
        """
        from world.traits.stat_handler import StatHandler

        return StatHandler(self)

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

    @cached_property
    def threads(self):
        """Handler for this character's owned magical threads (Spec A §3.7)."""
        from world.magic.handlers import CharacterThreadHandler

        return CharacterThreadHandler(self)

    @cached_property
    def resonances(self):
        """Handler for this character's CharacterResonance rows (Spec A §3.7)."""
        from world.magic.handlers import CharacterResonanceHandler

        return CharacterResonanceHandler(self)

    @cached_property
    def combat_pulls(self):
        """Handler for this character's active CombatPull rows (Spec A §3.7)."""
        from world.combat.handlers import CharacterCombatPullHandler

        return CharacterCombatPullHandler(self)

    @cached_property
    def equipped_items(self):
        """Cached handler for this character's equipped items and their facets (Spec D §3.3)."""
        from world.items.handlers import CharacterEquipmentHandler

        return CharacterEquipmentHandler(self)

    @cached_property
    def covenant_roles(self):
        """Cached handler for this character's covenant role assignments (Spec D §3.3)."""
        from world.covenants.handlers import CharacterCovenantRoleHandler

        return CharacterCovenantRoleHandler(self)

    @property
    def active_account(self):
        """Return the account currently linked to this character.

        Returns:
            Account | None: The controlling account, if any.
        """
        try:
            tenure = self.sheet_data.roster_entry.current_tenure
        except ObjectDoesNotExist:
            return None
        if not tenure or not tenure.player_data:
            return None
        return tenure.player_data.account

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
            entry = self.sheet_data.roster_entry
        except (RosterEntry.DoesNotExist, ObjectDoesNotExist):
            entry = None
        if entry:
            entry.last_puppeted = timezone.now()
            entry.save(update_fields=["last_puppeted"])
        payload = serialize_cmdset(self)
        for session in self.sessions.all():
            session.msg(commands=(payload, {}))

        # Stories login catch-up: re-evaluate active stories and deliver
        # any queued narrative messages that accumulated while offline.
        from world.stories.services.login import catch_up_character_stories

        catch_up_character_stories(self)

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

    def at_attacked(self, attacker, weapon, damage_result, action) -> None:
        """Called by combat after damage calc, before damage apply.

        Emits ATTACK_LANDED and gives listeners a chance to react. Downstream
        damage application fires DAMAGE_PRE_APPLY separately (Task 28).
        """
        if self.location is None:
            return
        payload = AttackLandedPayload(
            attacker=attacker,
            target=self,
            weapon=weapon,
            damage_result=damage_result,
            action=action,
        )
        emit_event(
            EventName.ATTACK_LANDED,
            payload,
            location=self.location,
        )

    def at_pre_move(self, destination, move_type="move", **kwargs):
        """Called just before moving to destination.

        Emits MOVE_PRE_DEPART and returns False if a reactive listener
        cancels the event, allowing conditions/triggers to block movement.
        """
        origin = self.location
        result = super().at_pre_move(destination, move_type=move_type, **kwargs)
        if result is False:
            return False  # Evennia-side cancel; skip emission
        if origin is None:
            return True  # No location to dispatch from; allow the move.
        payload = MovePreDepartPayload(
            character=self,
            origin=origin,
            destination=destination,
            exit_used=kwargs.get("exit_used") or kwargs.get("move_type"),
        )
        stack = emit_event(
            EventName.MOVE_PRE_DEPART,
            payload,
            location=origin,
        )
        if stack.was_cancelled():
            return False
        return True

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
