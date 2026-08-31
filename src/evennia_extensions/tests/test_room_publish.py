"""Tests for the #3477 Task 2 publish lifecycle: ``RoomProfile.published_at``.

Covers ``create_room``'s origin-conditioned default (an AUTHORED/staff-canvas
room is born unpublished; a PLAYER room is born published) and the room-state
exits payload's visibility gate (an unpublished destination's exit is omitted
for anyone but a story-runner). ``staff_publish_room`` action coverage lives
in ``actions/tests/test_world_builder_actions.py`` alongside its siblings;
``ExitState.can_traverse``'s enforcement lives in
``flows/tests/test_object_state_permissions.py``.
"""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import (
    CharacterFactory,
    GMCharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
    StaffCharacterFactory,
)
from evennia_extensions.models import RoomProfile
from flows.factories import SceneDataManagerFactory
from flows.service_functions.serializers.room_state import build_room_state_payload
from world.areas.constants import GridOrigin
from world.areas.factories import AreaFactory
from world.areas.grid_services import create_room


class CreateRoomPublishDefaultTests(TestCase):
    """``create_room``'s ``published_at`` depends on ``origin`` (#3477)."""

    def test_authored_room_born_unpublished(self) -> None:
        """The staff world-builder canvas dig is born unpublished."""
        area = AreaFactory()
        profile = create_room(area=area, name="Sunken Vault", origin=GridOrigin.AUTHORED)
        assert profile.published_at is None

    def test_player_room_born_published(self) -> None:
        """The owner-facing Room Builder (sharing this same primitive) is live immediately."""
        area = AreaFactory()
        profile = create_room(area=area, name="Garret", origin=GridOrigin.PLAYER)
        assert profile.published_at is not None

    def test_default_origin_is_player_and_born_published(self) -> None:
        area = AreaFactory()
        profile = create_room(area=area, name="Unset Origin Room")
        assert profile.published_at is not None


class RoomProfilePublishFieldDefaultTests(TestCase):
    """The model field itself defaults to published (#3477)."""

    def test_bare_room_profile_defaults_published(self) -> None:
        profile = RoomProfileFactory()
        assert profile.published_at is not None


class ExitsPayloadPublishVisibilityTests(TestCase):
    """An unpublished destination's exit is hidden from anyone but a story-runner (#3477)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="lobby",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.dest = ObjectDBFactory(
            db_key="unfinished wing",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        dest_profile = RoomProfile.objects.get(objectdb=self.dest)
        dest_profile.published_at = None
        dest_profile.save(update_fields=["published_at"])
        self.exit = ObjectDBFactory(
            db_key="north",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.dest,
        )

    def _exit_names_for(self, looker_factory) -> list[str]:
        context = SceneDataManagerFactory()
        looker = looker_factory(location=self.room)
        for obj in (self.room, self.dest, self.exit, looker):
            context.initialize_state_for_object(obj)
        looker_state = context.get_state_by_pk(looker.pk)
        room_state = context.get_state_by_pk(self.room.pk)
        payload = build_room_state_payload(looker_state, room_state)
        return [e["name"] for e in payload["exits"]]

    def test_player_looker_does_not_see_unpublished_exit(self) -> None:
        assert self._exit_names_for(CharacterFactory) == []

    def test_gm_looker_sees_unpublished_exit(self) -> None:
        assert "north" in self._exit_names_for(GMCharacterFactory)

    def test_staff_looker_sees_unpublished_exit(self) -> None:
        assert "north" in self._exit_names_for(StaffCharacterFactory)

    def test_published_destination_exit_visible_to_player(self) -> None:
        dest_profile = RoomProfile.objects.get(objectdb=self.dest)
        dest_profile.published_at = timezone.now()
        dest_profile.save(update_fields=["published_at"])
        assert "north" in self._exit_names_for(CharacterFactory)
