"""Tests for RoomCharacterSearchAPIView (#2049 — returns character id).

The view iterates in-memory scene state (``room_state.contents``), which is
hard to set up in a Django TestCase. Rather than fighting Evennia's ORM
descriptors (``location`` is a Django FK), these tests call the view's ``get``
method directly with a DRF Request and patched ``get_puppeted_characters``,
verifying the response shape carries the character's id (the ObjectDB pk the
invite endpoint expects).
"""

from unittest import mock

from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory, CharacterFactory
from web.api.views.search_views import RoomCharacterSearchAPIView
from world.character_sheets.factories import CharacterSheetFactory


class _FakeObjState:
    """Mimics an ObjectState row in room_state.contents."""

    def __init__(self, obj, name):
        self.obj = obj
        self._name = name

    def get_display_name(self, **_kwargs):
        return self._name


class _FakeRoomState:
    """Mimics a room's scene_state with a contents list."""

    def __init__(self, contents):
        self.contents = contents


class _FakeCallerState:
    """Mimics a caller's scene_state (the looker's state)."""


class RoomCharacterSearchViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="room-search")
        cls.caller = CharacterFactory()
        CharacterSheetFactory(character=cls.caller)
        cls.other = CharacterFactory()
        CharacterSheetFactory(character=cls.other)

    def _make_request(self, search=""):
        factory = APIRequestFactory()
        url = "/api/characters/room/"
        if search:
            url += f"?search={search}"
        django_request = factory.get(url)
        request = Request(django_request)
        # Bypass DRF authentication — force the account as the user.
        request.user = self.account
        return request

    def _call_view(self, room_contents, search=""):
        """Call the view directly with patched puppeted characters + scene state.

        Patches ``get_puppeted_characters`` so the view sees ``self.caller``,
        and patches the caller's ``scene_state`` property + ``db_location`` FK
        so the view iterates the given ``room_contents``.
        """
        request = self._make_request(search)
        caller_state = _FakeCallerState()
        room_state = _FakeRoomState([_FakeObjState(obj, name) for obj, name in room_contents])
        fake_room = mock.MagicMock()
        fake_room.scene_state = room_state

        with (
            mock.patch.object(
                type(self.account), "get_puppeted_characters", return_value=[self.caller]
            ),
            mock.patch.object(
                type(self.caller), "scene_state", new_callable=mock.PropertyMock
            ) as cs_mock,
            mock.patch.object(
                type(self.caller), "db_location", new_callable=mock.PropertyMock
            ) as loc_mock,
        ):
            cs_mock.return_value = caller_state
            loc_mock.return_value = fake_room
            view = RoomCharacterSearchAPIView()
            view.kwargs = {}
            return view.get(request)

    def test_returns_character_id_and_name(self):
        resp = self._call_view([(self.other, "OtherChar")])
        self.assertEqual(resp.status_code, 200)
        results = resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.other.pk)
        self.assertEqual(results[0]["name"], "OtherChar")

    def test_empty_room_returns_empty_list(self):
        resp = self._call_view([])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_search_term_filters_results(self):
        resp = self._call_view([(self.other, "OtherChar")], search="nomatch")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_no_puppeted_character_returns_empty(self):
        request = self._make_request()
        with mock.patch.object(type(self.account), "get_puppeted_characters", return_value=[]):
            view = RoomCharacterSearchAPIView()
            resp = view.get(request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])
