from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import FlowExecutionFactory, SceneDataManagerFactory
from flows.helpers.payloads import build_room_state_payload
from flows.service_functions.communication import send_room_state
from world.roster.factories import PlayerMediaFactory
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

        room_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.room, thumbnail=room_media)
        char_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.caller, thumbnail=char_media)
        item_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.item, thumbnail=item_media)
        exit_media = PlayerMediaFactory()
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
        fx = FlowExecutionFactory(
            variable_mapping={"caller": self.caller, "room": self.room.pk},
            context=self.context,
        )
        with patch.object(self.caller, "msg") as mock_msg:
            send_room_state(fx, "@caller")
            mock_msg.assert_called_once()
            # Extract the payload from the room_state keyword argument
            call_kwargs = mock_msg.call_args.kwargs
            assert "room_state" in call_kwargs
            payload = call_kwargs["room_state"][
                1
            ]  # Second element of the ((), payload) tuple
            assert payload["room"]["commands"] == ["look"]
            assert payload["objects"][0]["commands"] == ["look", "get"]
            assert payload["exits"][0]["commands"] == ["north"]
            assert payload["scene"] is None
