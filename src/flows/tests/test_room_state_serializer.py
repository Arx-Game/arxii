"""Tests for the room state serializer enrichment (characters + description)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from flows.service_functions.serializers.room_state import build_room_state_payload
from world.roster.factories import PlayerMediaFactory


class RoomStateSerializerCharacterSplitTests(TestCase):
    """Verify characters are separated from objects and description is included."""

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="grand hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller = ObjectDBFactory(
            db_key="hero",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.other_char = ObjectDBFactory(
            db_key="ally",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(
            db_key="sword",
            location=self.room,
        )
        self.exit = ObjectDBFactory(
            db_key="north",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
        )

        # Create display data for all objects
        for obj in (self.room, self.caller, self.other_char, self.item, self.exit):
            media = PlayerMediaFactory()
            ObjectDisplayData.objects.create(object=obj, thumbnail=media)

        # Initialize scene data manager and states
        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.caller_state = self.context.initialize_state_for_object(self.caller)
        self.other_char_state = self.context.initialize_state_for_object(self.other_char)
        self.item_state = self.context.initialize_state_for_object(self.item)
        self.exit_state = self.context.initialize_state_for_object(self.exit)

        # Set up dispatcher tags
        self.room_state.dispatcher_tags = ["look"]
        self.other_char_state.dispatcher_tags = ["look"]
        self.item_state.dispatcher_tags = ["look", "get"]
        self.exit_state.dispatcher_tags = ["north"]

        # Set up caller's command set
        look_cmd = SimpleNamespace(key="look")
        get_cmd = SimpleNamespace(key="get")
        north_cmd = SimpleNamespace(key="north")
        self.caller.cmdset.current = SimpleNamespace(
            commands=[look_cmd, get_cmd, north_cmd],
        )

        # Mock sessions.all() on the underlying Evennia objects.
        # We patch the .all method on the existing sessions handler rather than
        # replacing the handler itself (Evennia handlers are descriptors).
        self._session_patches = []

        # other_char is puppeted (sessions.all() returns non-empty list)
        p1 = patch.object(self.other_char.sessions, "all", return_value=[MagicMock()])
        p1.start()
        self._session_patches.append(p1)

        # item has no sessions (sessions.all() returns empty list)
        p2 = patch.object(self.item.sessions, "all", return_value=[])
        p2.start()
        self._session_patches.append(p2)

    def tearDown(self):
        for p in self._session_patches:
            p.stop()

    def test_characters_appear_in_characters_list(self):
        """Puppeted objects should appear in 'characters', not 'objects'."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert "ally" in char_names

    def test_non_characters_appear_in_objects_list(self):
        """Non-puppeted objects should appear in 'objects', not 'characters'."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        obj_names = [o["name"] for o in payload["objects"]]
        assert "sword" in obj_names

    def test_characters_not_in_objects(self):
        """Puppeted objects should not appear in 'objects'."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        obj_names = [o["name"] for o in payload["objects"]]
        assert "ally" not in obj_names

    def test_non_characters_not_in_characters(self):
        """Non-puppeted objects should not appear in 'characters'."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert "sword" not in char_names

    def test_caller_excluded_from_characters(self):
        """The caller should not appear in 'characters'."""
        # Ensure caller also has sessions (they are puppeted)
        p = patch.object(self.caller.sessions, "all", return_value=[MagicMock()])
        p.start()
        self._session_patches.append(p)

        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert "hero" not in char_names

    def test_room_data_includes_description(self):
        """Room data in payload should include the 'description' field."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert "description" in payload["room"]

    def test_exits_still_in_exits(self):
        """Exits should still appear in the 'exits' list."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        exit_names = [e["name"] for e in payload["exits"]]
        assert "north" in exit_names

    def test_exits_not_in_characters_or_objects(self):
        """Exits should not leak into 'characters' or 'objects'."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        obj_names = [o["name"] for o in payload["objects"]]
        assert "north" not in char_names
        assert "north" not in obj_names

    def test_payload_has_all_expected_keys(self):
        """Payload should contain room, characters, objects, exits, and scene."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert set(payload.keys()) == {"room", "characters", "objects", "exits", "scene"}
