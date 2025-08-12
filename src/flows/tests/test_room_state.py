from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import FlowExecutionFactory, SceneDataManagerFactory
from flows.helpers.payloads import build_room_state_payload
from flows.service_functions.communication import send_room_state
from world.roster.factories import PlayerMediaFactory


class RoomStateTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="char",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.room)

        room_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.room, thumbnail=room_media)
        char_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.caller, thumbnail=char_media)
        item_media = PlayerMediaFactory()
        ObjectDisplayData.objects.create(object=self.item, thumbnail=item_media)

        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.char_state = self.context.initialize_state_for_object(self.caller)
        self.item_state = self.context.initialize_state_for_object(self.item)

        self.room_state.dispatcher_tags = ["look"]
        self.item_state.dispatcher_tags = ["look", "get"]

        look_cmd = SimpleNamespace(key="look")
        get_cmd = SimpleNamespace(key="get")
        say_cmd = SimpleNamespace(key="say")
        self.caller.cmdset.current = SimpleNamespace(
            commands=[look_cmd, get_cmd, say_cmd]
        )

    def test_build_room_state_payload(self):
        payload = build_room_state_payload(self.char_state, self.room_state)
        self.assertEqual(payload["room"]["commands"], ["look"])
        self.assertEqual(payload["objects"][0]["commands"], ["look", "get"])

    def test_send_room_state(self):
        fx = FlowExecutionFactory(
            variable_mapping={"caller": self.caller, "room": self.room.pk},
            context=self.context,
        )
        with patch("web.message_dispatcher.send") as md:
            send_room_state(fx, "@caller", "@room")
            md.assert_called_once()
            payload = md.call_args.kwargs["payload"]
            self.assertEqual(payload["room"]["commands"], ["look"])
            self.assertEqual(payload["objects"][0]["commands"], ["look", "get"])
