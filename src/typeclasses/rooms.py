"""
Room

Rooms are simple containers that has no location of their own.

"""

from django.utils.functional import cached_property
from evennia.objects.objects import DefaultRoom

from evennia_extensions.models import RoomProfile
from flows.object_states.room_state import RoomState
from flows.scene_data_manager import SceneDataManager
from typeclasses.mixins import ObjectParent
from world.scenes.models import Scene

# Typeclass path repeated across is_typeclass checks; centralized for dedup.
_CHARACTER_TYPECLASS = "typeclasses.characters.Character"


class Room(ObjectParent, DefaultRoom):
    """
    Rooms are like any Object, except their location is None
    (which is default). They also use basetype_setup() to
    add locks so they cannot be puppeted or picked up.
    (to change that, use at_object_creation instead)

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects.
    """

    state_class = RoomState

    def at_object_creation(self):
        """Called once when the room is first created via Evennia."""
        super().at_object_creation()
        RoomProfile.objects.get_or_create(objectdb=self)

    def return_appearance(self, looker, **kwargs):
        """Standard room appearance plus the Functionaries standing here (#1766).

        Functionaries are abstracted (object-less) NPCs, so they never appear in
        ``self.contents`` — surface them explicitly so a placed room-feature NPC is
        actually visible (and hint that you can ``hire`` them).
        """
        text = super().return_appearance(looker, **kwargs) or ""
        from world.areas.services import get_room_profile
        from world.npc_services.functionaries import functionaries_in_room

        names = [f.display_name for f in functionaries_in_room(get_room_profile(self))]
        if names:
            text = f"{text}\n|wHere you can speak with:|n {', '.join(names)}"
        # #1450 — a Notice Board is a feature, not an object, so hint it on look
        # (a Town Crier already surfaces via the functionaries line above).
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.services import active_hub_feature

        hub = active_hub_feature(get_room_profile(self))
        if hub is not None and (
            hub.feature_kind.service_strategy == RoomFeatureServiceStrategy.NOTICE_BOARD
        ):
            # PLACEHOLDER flavor line (Apostate rewrite pass; keep dash-free).
            text = f"{text}\n|wA notice board stands here; try |ctidings local|w.|n"
        # #1765 — the looker's own pursuit heat here (self-only; None when SAFE).
        from world.justice.display import room_heat_line

        heat_line = room_heat_line(looker, self)
        if heat_line:
            text = f"{text}\n{heat_line}"
        return text

    @cached_property
    def item_data(self):
        """Room-specific item data handler."""
        from evennia_extensions.data_handlers import RoomItemDataHandler

        return RoomItemDataHandler(self)

    @cached_property
    def scene_data(self) -> SceneDataManager:
        """Return the SceneDataManager associated with this room."""
        return SceneDataManager()

    @property
    def active_scene(self) -> Scene | None:
        """Scene currently running in this room.

        Evennia's ndb holder returns None natively for a missing attribute —
        no defensive guard needed (silent-fail audit, holder hunt).
        """
        return self.ndb.active_scene

    @active_scene.setter
    def active_scene(self, value: Scene | None) -> None:
        """Cache ``value`` as the active scene for this room."""
        self.ndb.active_scene = value

    @property
    def dominant_affinity(self):
        """Dominant cascade affinity for this room, or None if inert.

        Computed from the room's cascade resonances. Used by the filter DSL
        to gate MOVED triggers on room affinity
        (path: ``destination.dominant_affinity.name``).
        """
        from world.magic.services.resonance_environment import get_room_dominant_affinity

        return get_room_dominant_affinity(self)

    @property
    def sentient_contents(self) -> list:
        """Return objects in this room that have active sessions."""
        sentients = []
        for obj in self.contents:
            try:
                if obj.sessions.all():
                    sentients.append(obj)
            except AttributeError:
                continue
        return sentients

    def _broadcast_room_state(self, exclude=None) -> None:
        """Send ``room_state`` updates to room occupants.

        Args:
            exclude: Object to omit from notifications.
        """
        room_state = self.scene_state
        if room_state is None:
            return
        for obj in self.sentient_contents:
            if obj is exclude:
                continue
            if hasattr(obj, "send_room_state"):
                obj.send_room_state()

    def at_object_receive(self, obj, source_location, **kwargs):
        """Notify occupants when an object enters.

        Args:
            obj: Object entering the room.
            source_location: Where the object came from.
            **kwargs: Arbitrary keyword arguments.
        """
        super().at_object_receive(obj, source_location, **kwargs)
        self._broadcast_room_state(exclude=obj)
        self._echo_public_gossip(obj)
        self._echo_hub_tidings(obj)

    def _echo_public_gossip(self, obj) -> None:
        """Let a character arriving at a social hub overhear its public gossip (#1572).

        No-op for non-characters and non-hub rooms (the latter short-circuits cheaply, so this
        never touches the region closure on ordinary moves).
        """
        if not obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False):
            return
        from world.secrets.gossip import public_gossip_lines

        lines = public_gossip_lines(self)
        if lines:
            obj.msg("\n".join(lines))

    def _echo_hub_tidings(self, obj) -> None:
        """Give an arriving character a taste of the civic hub's freshest tidings (#1450).

        Only fires in rooms carrying an active hub feature (Notice Board / Town Crier),
        so ordinary moves short-circuit on one cheap feature lookup. Echoes the two
        freshest items; ``tidings local`` is the full read.
        """
        if not obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False):
            return
        from world.areas.services import get_room_profile
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.services import active_hub_feature

        feature = active_hub_feature(get_room_profile(self))
        if feature is None:
            return
        from world.tidings.services import hub_feed_for_room

        feed = hub_feed_for_room(self, limit=2)
        if not feed:
            return
        is_crier = feature.feature_kind.service_strategy == RoomFeatureServiceStrategy.TOWN_CRIER
        # PLACEHOLDER flavor lines (Apostate rewrite pass; keep dash-free).
        lead = (
            "|wA crier's voice carries over the square:|n"
            if is_crier
            else "|wFresh postings crowd the notice board here:|n"
        )
        lines = [lead, *(f"  {item.subject}: {item.headline}" for item in feed)]
        obj.msg("\n".join(lines))

    def at_object_leave(self, obj, target_location, **kwargs):
        """Notify occupants when an object leaves.

        Args:
            obj: Object leaving the room.
            target_location: Destination of the object.
            **kwargs: Arbitrary keyword arguments.
        """
        super().at_object_leave(obj, target_location, **kwargs)
        self._broadcast_room_state(exclude=obj)
        # #1479 Task 8: a departure may remove the last potential rescuer from a
        # downed victim in this room — resolve their abandonment fate immediately.
        from world.scenes.round_services import resolve_solo_abandoned_victims

        resolve_solo_abandoned_victims(self, departing=obj)
        # #1479 (plummet): a departure may leave a falling character with no one to
        # catch them — the fall completes to impact immediately rather than freezing
        # mid-air (falling is environmental, never abandonment-pool-resolved).
        from world.areas.positioning.plummet import resolve_unattended_plummets

        resolve_unattended_plummets(self, departing=obj)
        # #1361: a departure may leave this room's active scene empty — finish it
        # immediately rather than leaving it open indefinitely.
        from world.scenes.round_services import maybe_finish_empty_scene

        maybe_finish_empty_scene(self, leaving=obj)
        # #2356: remove a departing character from the room's speaker queue.
        if obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False):
            from world.scenes.models import Persona
            from world.scenes.services import active_persona_for_sheet
            from world.scenes.speaker_queue_services import (
                remove_persona_from_room_queues,
            )

            sheet = obj.character_sheet
            if sheet is not None:
                try:
                    persona = active_persona_for_sheet(sheet)
                    remove_persona_from_room_queues(self, persona)
                except Persona.DoesNotExist:
                    pass
