"""Tests for RoomCharacterSearchAPIView (#2049 — returns character id).

The view iterates in-memory scene state (``room_state.contents``), which is
hard to set up in a Django TestCase. These tests mock the puppeted-character
+ scene-state accessors so we can verify the response shape carries the
character's id (the ObjectDB pk the invite endpoint expects).
"""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory


class RoomCharacterSearchAPIViewTests(TestCase):
    URL = "/api/characters/room/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="room-search")
        cls.caller = CharacterFactory()
        CharacterSheetFactory(character=cls.caller)
        cls.other = CharacterFactory()
        CharacterSheetFactory(character=cls.other)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def _patch_view_deps(self, room_contents):
        """Patch the view's dependencies: puppeted characters + scene state.

        ``room_contents`` is a list of (obj, name) tuples for the characters
        in the caller's room. The caller's own scene_state and the room's
        scene_state are both mocked.
        """

        class _FakeObjState:
            def __init__(self, obj, name):
                self.obj = obj
                self._name = name

            def get_display_name(self, _looker):
                return self._name

        caller_state = mock.MagicMock()
        room_state = mock.MagicMock()
        room_state.contents = [_FakeObjState(obj, name) for obj, name in room_contents]

        # Patch get_puppeted_characters to return the caller.
        puppet_patch = mock.patch.object(
            type(self.account), "get_puppeted_characters", return_value=[self.caller]
        )
        # Patch the caller's scene_state property.
        caller_scene_patch = mock.patch.object(
            type(self.caller), "scene_state", new_callable=mock.PropertyMock
        )
        # Patch the caller's location to a mock with scene_state.
        location = mock.MagicMock()
        location.scene_state = room_state
        location_patch = mock.patch.object(
            type(self.caller), "location", new_callable=mock.PropertyMock, return_value=location
        )
        return puppet_patch, caller_scene_patch, location_patch, caller_state

    def test_returns_character_id_and_name(self):
        (
            puppet_patch,
            caller_scene_patch,
            location_patch,
            caller_state,
        ) = self._patch_view_deps([(self.other, "OtherChar")])
        with puppet_patch, caller_scene_patch as cs, location_patch:
            cs.return_value = caller_state
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.other.pk)
        self.assertEqual(results[0]["name"], "OtherChar")

    def test_empty_room_returns_empty_list(self):
        (
            puppet_patch,
            caller_scene_patch,
            location_patch,
            caller_state,
        ) = self._patch_view_deps([])
        with puppet_patch, caller_scene_patch as cs, location_patch:
            cs.return_value = caller_state
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_search_term_filters_results(self):
        (
            puppet_patch,
            caller_scene_patch,
            location_patch,
            caller_state,
        ) = self._patch_view_deps([(self.other, "OtherChar")])
        with puppet_patch, caller_scene_patch as cs, location_patch:
            cs.return_value = caller_state
            resp = self.client.get(self.URL, {"search": "nomatch"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_no_puppeted_character_returns_empty(self):
        with mock.patch.object(type(self.account), "get_puppeted_characters", return_value=[]):
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])
