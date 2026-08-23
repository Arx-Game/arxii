"""Tests for the room state serializer enrichment (characters + description)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from flows.service_functions.serializers.room_state import build_room_state_payload
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.roster.factories import MediaFactory, RosterEntryFactory


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
            media = MediaFactory()
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

    def test_room_data_includes_is_owner_false_for_non_owner(self):
        """Room payload carries an is_owner flag (#1470); False without ownership."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["room"]["is_owner"] is False

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
        """Payload keys: room/characters/objects/exits/scene + heat (#1765) + hub (#1450)
        + npc_givers (#3044) + decorations/comfort_level (#2991)
        + has_unseen_presence (#3288)."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert set(payload.keys()) == {
            "room",
            "characters",
            "objects",
            "exits",
            "scene",
            "heat",
            "hub",
            "npc_givers",
            "decorations",
            "comfort_level",
            "has_unseen_presence",
        }
        # Cold persona → the self-only heat field is None (never another player's data).
        assert payload["heat"] is None
        # No Notice Board / Town Crier feature here → the hub block is None.
        assert payload["hub"] is None
        # No Functionary placed here → no NPC givers.
        assert payload["npc_givers"] == []
        # No RoomDecoration rows here → empty, and the bare neutral comfort level (5).
        assert payload["decorations"] == []
        assert payload["comfort_level"] == 5
        # No concealed occupant → no unseen-presence disclosure (#3288).
        assert payload["has_unseen_presence"] is False

    def test_objects_carry_is_mission_board_false_by_default(self):
        """A plain object with no MissionGiver is never a board (#3044)."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        sword = next(o for o in payload["objects"] if o["name"] == "sword")
        assert sword["is_mission_board"] is False


class RoomStateSerializerDecorAndComfortTests(TestCase):
    """#2991 — placed decorations and comfort level are legible in scenes."""

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="furnished parlor",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller = ObjectDBFactory(
            db_key="hero",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.caller_state = self.context.initialize_state_for_object(self.caller)
        self.room_state.dispatcher_tags = ["look"]
        self.caller.cmdset.current = SimpleNamespace(commands=[])

    def test_placed_decorations_appear_ordered_by_placement(self):
        from world.buildings.factories import DecorationKindFactory
        from world.buildings.services import place_decoration

        profile = self.room.room_profile
        place_decoration(profile, DecorationKindFactory(name="Rug", amenity=50))
        place_decoration(profile, DecorationKindFactory(name="Tapestry", amenity=30))

        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["decorations"] == ["Rug", "Tapestry"]

    def test_comfort_level_reflects_placed_amenity(self):
        from world.buildings.factories import DecorationKindFactory
        from world.buildings.services import place_decoration

        profile = self.room.room_profile
        payload_before = build_room_state_payload(self.caller_state, self.room_state)
        assert payload_before["comfort_level"] == 5  # neutral, no decor yet

        place_decoration(profile, DecorationKindFactory(name="Marble Bath", amenity=3000))

        payload_after = build_room_state_payload(self.caller_state, self.room_state)
        assert payload_after["comfort_level"] == 8  # 3000 points crosses the 2500 floor


class RoomStateSerializerMissionDiscoveryTests(TestCase):
    """#3044 — the board discriminator and NPC-giver room block."""

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="market square",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller = ObjectDBFactory(
            db_key="hero",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.board_obj = ObjectDBFactory(db_key="notice board", location=self.room)
        self.plain_obj = ObjectDBFactory(db_key="barrel", location=self.room)

        for obj in (self.room, self.caller, self.board_obj, self.plain_obj):
            media = MediaFactory()
            ObjectDisplayData.objects.create(object=obj, thumbnail=media)

        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.caller_state = self.context.initialize_state_for_object(self.caller)

    def test_board_object_carries_is_mission_board_true(self):
        from world.missions.constants import GiverKind
        from world.missions.factories import MissionGiverFactory

        MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)

        payload = build_room_state_payload(self.caller_state, self.room_state)
        board_row = next(o for o in payload["objects"] if o["name"] == "notice board")
        plain_row = next(o for o in payload["objects"] if o["name"] == "barrel")
        assert board_row["is_mission_board"] is True
        assert plain_row["is_mission_board"] is False

    def test_inactive_board_giver_does_not_flag_object(self):
        from world.missions.constants import GiverKind
        from world.missions.factories import MissionGiverFactory

        MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj, is_active=False)

        payload = build_room_state_payload(self.caller_state, self.room_state)
        board_row = next(o for o in payload["objects"] if o["name"] == "notice board")
        assert board_row["is_mission_board"] is False

    def test_npc_givers_lists_active_functionary_placements(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory

        profile = RoomProfileFactory(objectdb=self.room)
        role = NPCRoleFactory(name="market-crier")
        FunctionaryFactory(room=profile, role=role, name_override="Old Marta")

        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["npc_givers"] == [{"role_id": role.pk, "name": "Old Marta"}]

    def test_npc_givers_excludes_retired_placements(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory

        profile = RoomProfileFactory(objectdb=self.room)
        FunctionaryFactory(room=profile, is_active=False)

        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["npc_givers"] == []


class RoomStateSerializerConcealmentTests(TestCase):
    """#1225 — ``can_perceive`` gates the ``characters`` list.

    A concealed-and-undetected character must not leak name/dbref/avatar to other
    room occupants via the web room-state payload.
    """

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="shadowed hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        self.caller_sheet = RosterEntryFactory().character_sheet
        self.caller = self.caller_sheet.character
        self.caller.move_to(self.room, quiet=True)

        self.visible_sheet = RosterEntryFactory().character_sheet
        self.visible = self.visible_sheet.character
        self.visible.move_to(self.room, quiet=True)

        self.concealed_sheet = RosterEntryFactory().character_sheet
        self.concealed = self.concealed_sheet.character
        self.concealed.move_to(self.room, quiet=True)

        cat = ConditionCategoryFactory(conceals_from_perception=True)
        self.concealing_condition = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.concealed, condition=self.concealing_condition)

        for obj in (self.room, self.caller, self.visible, self.concealed):
            media = MediaFactory()
            ObjectDisplayData.objects.create(object=obj, thumbnail=media)

        self.context = SceneDataManagerFactory()
        self.room_state = self.context.initialize_state_for_object(self.room)
        self.caller_state = self.context.initialize_state_for_object(self.caller)

        self._session_patches = []
        for char in (self.caller, self.visible, self.concealed):
            p = patch.object(char.sessions, "all", return_value=[MagicMock()])
            p.start()
            self._session_patches.append(p)

    def tearDown(self):
        for p in self._session_patches:
            p.stop()

    def test_concealed_and_undetected_character_is_omitted(self):
        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert self.concealed.key not in char_names

    def test_unconcealed_co_located_character_appears(self):
        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert self.visible.key in char_names

    def test_detected_concealed_character_appears(self):
        register_detection(self.caller_sheet, self.concealed)

        payload = build_room_state_payload(self.caller_state, self.room_state)
        char_names = [c["name"] for c in payload["characters"]]
        assert self.concealed.key in char_names

    def test_has_unseen_presence_flag_disclosed(self):
        """#3288 — a concealed occupant always flips the identity-free room flag."""
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["has_unseen_presence"] is True

    def test_flag_stays_true_for_detecting_viewer(self):
        """#3288 — piercing gives the viewer MORE info; the disclosure never retracts."""
        register_detection(self.caller_sheet, self.concealed)
        payload = build_room_state_payload(self.caller_state, self.room_state)
        assert payload["has_unseen_presence"] is True
