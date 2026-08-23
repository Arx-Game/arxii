from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import (
    ObjectDBFactory,
    RoomDescVariantFactory,
    RoomProfileFactory,
)
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from flows.helpers.payloads import build_room_state_payload
from flows.service_functions.communication import send_room_state
from world.game_clock.factories import GameClockFactory
from world.roster.factories import MediaFactory
from world.scenes.factories import SceneFactory


class RoomStateTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller = ObjectDBFactory(
            db_key="char",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.room)
        self.exit = ObjectDBFactory(
            db_key="north",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
        )

        room_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.room, thumbnail=room_media)
        char_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.caller, thumbnail=char_media)
        item_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.item, thumbnail=item_media)
        exit_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.exit, thumbnail=exit_media)

        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.char_state = self.context.initialize_state_for_object(self.caller)
        self.item_state = self.context.initialize_state_for_object(self.item)
        self.exit_state = self.context.initialize_state_for_object(self.exit)

        self.room_state.dispatcher_tags = ["look"]
        self.item_state.dispatcher_tags = ["look", "get"]
        self.exit_state.dispatcher_tags = ["north"]

        look_cmd = SimpleNamespace(key="look")
        get_cmd = SimpleNamespace(key="get")
        say_cmd = SimpleNamespace(key="say")
        north_cmd = SimpleNamespace(key="north")
        self.caller.cmdset.current = SimpleNamespace(
            commands=[look_cmd, get_cmd, say_cmd, north_cmd],
        )

    def test_build_room_state_payload(self):
        payload = build_room_state_payload(self.char_state, self.room_state)
        assert payload["room"]["commands"] == ["look"]
        assert payload["objects"][0]["commands"] == ["look", "get"]
        assert payload["exits"][0]["commands"] == ["north"]
        assert payload["scene"] is None

    def test_build_room_state_payload_uses_cached_scene(self):
        scene = SceneFactory(location=self.room)
        self.room.active_scene = scene
        with patch("world.scenes.models.Scene.objects.filter") as mock_filter:
            payload = build_room_state_payload(self.char_state, self.room_state)
            assert payload["scene"]["id"] == scene.id
            mock_filter.assert_not_called()

    def test_send_room_state(self):
        with patch.object(self.caller, "msg") as mock_msg:
            send_room_state(self.char_state, room_state=self.room_state)
            mock_msg.assert_called_once()
            # Extract the payload from the room_state keyword argument
            call_kwargs = mock_msg.call_args.kwargs
            assert "room_state" in call_kwargs
            payload = call_kwargs["room_state"][1]  # Second element of the ((), payload) tuple
            assert payload["room"]["commands"] == ["look"]
            assert payload["objects"][0]["commands"] == ["look", "get"]
            assert payload["exits"][0]["commands"] == ["north"]
            assert payload["scene"] is None


class RoomStateDescVariantTests(TestCase):
    """#3291 — season/phase variant resolution wired into get_display_desc."""

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="the courtyard",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        ObjectDisplayData.objects.create(object=self.room, permanent_description="A courtyard.")
        self.profile = RoomProfileFactory(objectdb=self.room)
        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)

    def test_no_clock_falls_back_to_base_desc(self):
        RoomDescVariantFactory(room_profile=self.profile, season="winter", description="Frost.")
        assert self.room_state.get_display_desc(mode="look") == "A courtyard."

    def test_matching_variant_replaces_base_desc(self):
        GameClockFactory(
            anchor_ic_time=datetime(1, 1, 10, 2, 0, tzinfo=UTC),  # WINTER, NIGHT
            paused=True,
        )
        RoomDescVariantFactory(
            room_profile=self.profile,
            season="winter",
            phase="night",
            description="A hard black midwinter cold grips the stones.",
        )
        desc = self.room_state.get_display_desc(mode="look")
        assert desc == "A hard black midwinter cold grips the stones."

    def test_non_matching_variant_falls_back_to_base_desc(self):
        GameClockFactory(
            anchor_ic_time=datetime(1, 7, 10, 12, 0, tzinfo=UTC),  # SUMMER, DAY
            paused=True,
        )
        RoomDescVariantFactory(room_profile=self.profile, season="winter", description="Frost.")
        assert self.room_state.get_display_desc(mode="look") == "A courtyard."

    def test_event_overlay_beats_variant(self):
        """#3291 Decision 2: the event room_description_overlay always wins."""
        GameClockFactory(
            anchor_ic_time=datetime(1, 1, 10, 2, 0, tzinfo=UTC),  # WINTER, NIGHT
            paused=True,
        )
        RoomDescVariantFactory(
            room_profile=self.profile,
            season="winter",
            phase="night",
            description="A hard black midwinter cold grips the stones.",
        )
        display_data = ObjectDisplayData.objects.get(object=self.room)
        display_data.temporary_description = "A masquerade transforms the courtyard."
        display_data.save(update_fields=["temporary_description"])
        desc = self.room_state.get_display_desc(mode="look")
        assert desc == "A masquerade transforms the courtyard."

    def test_glance_mode_untouched(self):
        GameClockFactory(
            anchor_ic_time=datetime(1, 1, 10, 2, 0, tzinfo=UTC),
            paused=True,
        )
        RoomDescVariantFactory(room_profile=self.profile, season="winter", description="Frost.")
        from flows.consts import GLANCE_MODE

        assert self.room_state.get_display_desc(mode=GLANCE_MODE) == ""
