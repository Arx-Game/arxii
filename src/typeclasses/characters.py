"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

import contextlib

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.objects.objects import DefaultCharacter

from commands.utils import serialize_cmdset
from core.descriptors import ReverseOneToOneOrNone
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import AttackLandedPayload, MovedPayload, MovePreDepartPayload
from flows.object_states.character_state import CharacterState
from flows.service_functions.serializers import build_room_state_payload
from typeclasses.mixins import ObjectParent
from world.magic.services.resonance_environment import (
    clear_resonance_alignment,
    refresh_resonance_alignment,
)
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

    #: True only for GM/Staff "story-runner" characters; gates scene/round admin.
    is_story_runner: bool = False

    state_class = CharacterState

    #: Reverse-OneToOne safe accessor (#2386): the CharacterFormState row, or
    #: None when unprovisioned. Character-scoped, so it lives here rather than
    #: on ObjectParent (CharacterFormState.character is limited to Characters).
    form_state_or_none = ReverseOneToOneOrNone("form_state")

    #: Reverse-OneToOne safe accessor (#2386): the CharacterAnima row, or None.
    anima_or_none = ReverseOneToOneOrNone("anima")

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
    def techniques(self):
        """Handler for this character's Techniques + effect Properties.

        Used by the clash-opposition predicate to find which of the
        character's techniques can engage in or assist a given clash.
        """
        from world.magic.handlers import CharacterTechniqueHandler

        return CharacterTechniqueHandler(self)

    @cached_property
    def conditions(self):
        """Handler for this character's active ConditionInstance rows."""
        from world.conditions.handlers import CharacterConditionHandler

        return CharacterConditionHandler(self)

    @cached_property
    def companions(self):
        """Handler for this character's bonded Companion rows (#672)."""
        from world.companions.handlers import CharacterCompanionHandler

        return CharacterCompanionHandler(self)

    @cached_property
    def equipped_items(self):
        """Cached handler for this character's equipped items and their facets (Spec D §3.3)."""
        from world.items.handlers import CharacterEquipmentHandler

        return CharacterEquipmentHandler(self)

    @cached_property
    def carried_items(self):
        """Cached handler for items located on this character (inventory)."""
        from world.items.handlers import CharacterCarriedItemsHandler

        return CharacterCarriedItemsHandler(self)

    @cached_property
    def covenant_roles(self):
        """Cached handler for this character's covenant role assignments (Spec D §3.3)."""
        from world.covenants.handlers import CharacterCovenantRoleHandler

        return CharacterCovenantRoleHandler(self)

    @cached_property
    def weaving_unlocks(self):
        """Cached handler for this character's ThreadWeavingUnlock purchases."""
        from world.magic.handlers import CharacterWeavingUnlockHandler

        return CharacterWeavingUnlockHandler(self)

    @cached_property
    def mantle_clearances(self):
        """Cached handler for this character's recorded mantle-level clearances (Spec D, #512)."""
        from world.items.handlers import CharacterMantleClearanceHandler

        return CharacterMantleClearanceHandler(self)

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

    def active_covenant_ids(self) -> frozenset[int]:
        """Return the frozenset of covenant PKs where this character is currently active.

        Delegates to the covenant-roles handler; returns empty frozenset if no sheet.
        """
        sheet = self.character_sheet
        if sheet is None:
            return frozenset()
        return self.covenant_roles.active_covenant_ids()

    def shares_covenant_with(self, other: "Character") -> bool:
        """True if self and other share at least one currently-active covenant.

        Used by the reactive-filter ``shares_covenant`` op.
        """
        mine = self.active_covenant_ids()
        if not mine:
            return False
        return bool(mine & other.active_covenant_ids())

    def has_property(self, name: str) -> bool:
        """True if this character currently carries the named Property tag.

        Checks both the primary persona's authored identity tags (e.g.
        masked-identity) and this character's runtime ObjectProperty
        attachments (e.g. aerial) — the same Property catalog, two
        attachment surfaces. Used by the reactive-filter ``has_property`` op.
        """
        from world.scenes.models import Persona

        if self.object_properties.filter(property__name=name).exists():
            return True
        sheet = self.character_sheet
        if sheet is None:
            return False
        try:
            persona = sheet.primary_persona
        except Persona.DoesNotExist:
            return False
        return persona.properties.filter(name=name).exists()

    def has_capability(self, name: str) -> bool:
        """True if this character's effective value for the named Capability is > 0.

        The capability-typed sibling of ``has_property`` for reactive-trigger
        effect negation (e.g. "flying" modeled as an intrinsic Capability
        rather than a runtime Property). Used by the reactive-filter
        ``has_capability`` op.
        """
        from world.conditions.models import CapabilityType
        from world.conditions.services import get_effective_capability_value

        sheet = self.character_sheet
        if sheet is None:
            return False
        try:
            capability = CapabilityType.objects.get(name=name)
        except CapabilityType.DoesNotExist:
            return False
        return get_effective_capability_value(sheet, capability) > 0

    def has_resonance_at_least(self, spec: dict) -> bool:
        """True if this character's lifetime-earned value for a Resonance meets a minimum.

        ``spec = {"resonance": <name>, "minimum": <int>}``. Used by the reactive-filter
        ``has_resonance_at_least`` op (#2471 v2).
        """
        from world.magic.models import Resonance

        resonance = Resonance.objects.filter(name=spec["resonance"]).first()
        if resonance is None:
            return False
        return self.resonances.lifetime(resonance) >= spec["minimum"]

    def has_public_distinction(self, slug: str) -> bool:
        """True if this character holds the named Distinction and it isn't secret-relocated.

        A distinction relocated into a Secret (#1334) must never leak through a reactive
        filter. Used by the reactive-filter ``has_public_distinction`` op (#2471 v2).
        """
        return self.distinctions.filter(distinction__slug=slug, secret__isnull=True).exists()

    def fame_tier_at_least(self, spec: dict) -> bool:
        """True if this character's active persona's perceived fame tier meets a minimum.

        ``spec = {"min_tier": <FameTier value>, "perceiving_society": <name or None>}``.
        ``perceiving_society`` applies that society's ``fame_perception_offset`` before
        comparing (insular societies perceive less fame). Used by the reactive-filter
        ``fame_tier_at_least`` op (#2471 v2).
        """
        from world.scenes.models import Persona
        from world.scenes.services import active_persona_for_sheet
        from world.societies.constants import FAME_TIER_ORDER

        sheet = self.character_sheet
        if sheet is None:
            return False
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return False
        offset = 0
        society_name = spec.get("perceiving_society")
        if society_name:
            from world.societies.models import Society

            society = Society.objects.filter(name=society_name).first()
            if society is not None:
                offset = society.fame_perception_offset or 0
        perceived_index = max(0, FAME_TIER_ORDER.index(persona.fame_tier) + offset)
        return perceived_index >= FAME_TIER_ORDER.index(spec["min_tier"])

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

        # Friends watch list (#1727): alert online players who friended this character.
        from world.scenes.friend_services import notify_friends_of_status

        notify_friends_of_status(self, online=True)

        # Execute look command to send room state to frontend via flow system
        self.execute_cmd("look")

    def send_room_state(self):
        """Send current room state to this character's frontend.

        Uses the scene_state properties to get current state information.
        Falls back to executing 'look' command if state retrieval fails.

        #2287/#2290: while Unconscious or Sleeping, perception relocates to the
        dream space — the frontend renders the dream side, not the waking room.
        """
        if not (self.has_account and self.location):
            return
        room = self.location
        from world.dreams.services import get_dream_space
        from world.vitals.services import perceives_dreamside

        try:
            sheet = self.sheet_data
        except ObjectDoesNotExist:
            sheet = None
        if perceives_dreamside(sheet):
            room = get_dream_space(room=self.location) or room
        caller_state = self.scene_state
        room_state = room.scene_state
        if caller_state and room_state:
            payload = build_room_state_payload(caller_state, room_state)
            self.msg(room_state=((), payload))

    def at_post_move(self, source_location, move_type="move", **kwargs):
        """Handle actions after moving to a new location.

        Sends updated room state to the frontend after movement.
        Reconciles the presence-tied resonance-alignment buff for the new location.
        Emits EventName.MOVED so reactive triggers (e.g. scar-gated presence
        escalation) can respond to character arrival.
        """
        # Call parent method to handle trigger registration
        super().at_post_move(source_location, move_type=move_type, **kwargs)

        # Send room state to frontend
        self.send_room_state()

        # #1765 — relief line when a hot persona crosses into safety (self-only).
        from world.justice.display import safe_transition_line

        relief = safe_transition_line(self, source_location, self.location)
        if relief:
            self.msg(relief)

        # #2378 — at max heat, merely arriving in a public room rolls guard
        # pressure (event-driven; never offline, never in private rooms).
        self._maybe_justice_room_arrival()

        # Reconcile presence-tied ALIGNED resonance buff for arrival location.
        # Guard mirrors at_post_puppet: some Character-typeclass objects have no sheet.
        with contextlib.suppress(RosterEntry.DoesNotExist, ObjectDoesNotExist):
            refresh_resonance_alignment(character_sheet=self.sheet_data)

        # Emit MOVED for reactive triggers (e.g. scar-gated presence escalation).
        # Only emit when destination is a real room; no-op if character has no location.
        if self.location is not None:
            payload = MovedPayload(
                character=self,
                origin=source_location,
                destination=self.location,
                exit_used=kwargs.get("exit_used"),
            )
            emit_event(EventName.MOVED, payload, location=self.location)

            # Optional side-effects of arriving — mission ROOM_TRIGGER dispatch (#729),
            # trap detection (#1051), passive clue triggers (#1160). Ambient room
            # reactions (species/resonance/distinction/fame-tier, #2471 — retired #881's
            # fame_reactions.py) dispatch separately via the MOVED Flows/Trigger event
            # emitted just above, not through this hardcoded list.
            # Each is wrapped by run_safely (#1164): a failure never breaks the move, but it
            # is captured as a SystemErrorReport and the player is told — not silently
            # swallowed. The cheap room-bound query in each short-circuits ordinary rooms.
            from world.clues.services import maybe_grant_clue_triggers
            from world.missions.services.trigger_dispatch import (
                maybe_dispatch_on_enter,
            )
            from world.npc_services.guard_services import (
                check_guard_detection,
            )
            from world.player_submissions.services import run_safely
            from world.room_features.trap_services import (
                check_room_traps_on_entry,
            )
            from world.species.services import reconcile_sunlight_exposure

            run_safely(
                "mission_trigger_on_enter",
                lambda: maybe_dispatch_on_enter(self, self.location),
                actor=self,
            )
            run_safely(
                "trap_detection_on_enter",
                lambda: check_room_traps_on_entry(self, self.location),
                actor=self,
            )
            run_safely(
                "clue_trigger_on_enter",
                lambda: maybe_grant_clue_triggers(self, self.location),
                actor=self,
            )
            run_safely(
                "sunlight_exposure_on_enter",
                lambda: reconcile_sunlight_exposure(self, self.location),
                actor=self,
            )

            # Companions follow their owner (#672 spec, Decision #9).
            def _companion_follow_on_move() -> None:
                for companion in self.companions.active():
                    if companion.objectdb is not None:
                        companion.objectdb.move_to(self.location, quiet=True)

            run_safely("companion_follow_on_move", _companion_follow_on_move, actor=self)

            # Guard detection (#2178) — post-arrival stealth check.
            run_safely(
                "guard_detection_on_enter",
                lambda: check_guard_detection(self, self.location),
                actor=self,
            )

            # Cancel any in-progress servant fetch (#2276) — the servant
            # can't deliver to an empty room.
            from world.npc_services.servant_fetch import (
                cancel_servant_fetch,
            )

            run_safely(
                "cancel_servant_fetch_on_move",
                lambda: cancel_servant_fetch(self),
                actor=self,
            )

    def _maybe_justice_room_arrival(self):
        """Max-tier guard pressure on public-room arrival (#2378)."""
        from world.justice.constants import GuardTrigger
        from world.justice.pipeline import (
            maybe_guard_encounter,
            public_room_profile,
            resolve_guard_encounter,
        )
        from world.justice.services import area_for_room
        from world.scenes.services import active_persona_for_sheet

        location = self.location
        if public_room_profile(location) is None:
            return
        try:
            sheet = self.sheet_data
        except (RosterEntry.DoesNotExist, ObjectDoesNotExist, AttributeError):
            return
        persona = active_persona_for_sheet(sheet) if sheet else None
        if persona is None:
            return
        encounter = maybe_guard_encounter(
            persona, area_for_room(location), GuardTrigger.ROOM_ARRIVAL
        )
        if encounter is not None:
            resolved = resolve_guard_encounter(encounter)
            self.msg(_guard_encounter_line(resolved))

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
        # departure-to-no-room: explicit clear so the buff doesn't linger on a
        # character with no location (normal room→room transit is reconciled by
        # at_post_move on the destination side; only this special case needs clearing here).
        if destination is None:
            with contextlib.suppress(RosterEntry.DoesNotExist, ObjectDoesNotExist):
                clear_resonance_alignment(character_sheet=self.sheet_data)
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
        origin = self.location
        super().at_post_unpuppet(account=account, session=session, **kwargs)
        target = [session] if session else self.sessions.all()
        for sess in target:
            sess.msg(commands=([], {}))

        # Clear presence-tied resonance buff on logout; character is no longer present.
        with contextlib.suppress(RosterEntry.DoesNotExist, ObjectDoesNotExist):
            clear_resonance_alignment(character_sheet=self.sheet_data)

        # Friends watch list (#1727): alert online players who friended this character.
        from world.scenes.friend_services import notify_friends_of_status

        notify_friends_of_status(self, online=False)

        # #1361: the base at_post_unpuppet call above already relocated this
        # character off-grid if that was its last session — finish the room's
        # scene if it's now empty. Guard mirrors Evennia's own last-session-out
        # check rather than re-implementing it.
        if origin is not None and self.location is None:
            from world.scenes.round_services import maybe_finish_empty_scene

            maybe_finish_empty_scene(origin, leaving=self)

            # #2356: remove this character from the room's speaker queue.
            from world.scenes.models import Persona
            from world.scenes.services import active_persona_for_sheet
            from world.scenes.speaker_queue_services import (
                remove_persona_from_room_queues,
            )

            if self.character_sheet is not None:
                try:
                    persona = active_persona_for_sheet(self.character_sheet)
                    remove_persona_from_room_queues(origin, persona)
                except Persona.DoesNotExist:
                    pass

            sheet = self.character_sheet
            if sheet is not None:
                from world.battles.services import maybe_pause_battle_for_disconnect
                from world.combat.services import maybe_pause_encounter_for_disconnect
                from world.missions.services.play import maybe_pause_mission_for_disconnect

                maybe_pause_encounter_for_disconnect(sheet)
                maybe_pause_battle_for_disconnect(sheet)
                maybe_pause_mission_for_disconnect(sheet)


def _guard_encounter_line(encounter) -> str:
    """PLACEHOLDER prose for a resolved guard encounter (#2378)."""
    from world.justice.constants import EncounterOutcome

    if encounter.outcome == EncounterOutcome.CAPTURED:
        return "|rGuards close in — you are taken into custody.|n"
    if encounter.outcome == EncounterOutcome.ESCAPED_SEEN:
        return "|yGuards give chase! You slip away, but you were seen.|n"
    return "|gYou spot the watch first and melt into the crowd.|n"
