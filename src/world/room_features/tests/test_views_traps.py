"""API tests for GET /api/room-features/traps/ (#3011).

Personal like ``ComfortViewSet``/``PortalDestinationsViewSet``: only serves a
character the requesting account actually plays, and the room is derived from
that character's own location rather than taken as a caller-supplied param --
so "present in the room" falls out of the ownership check for free. These
tests pin the leak table from the #3011 spec: a hidden trap the viewer hasn't
detected never appears, even for a viewer standing in the same room as a
character who HAS detected it.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.room_features.factories import TrapFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory

ROOM_TRAPS_URL = "/api/room-features/traps/"


class RoomTrapViewSetTest(APITestCase):
    def setUp(self) -> None:
        self.user = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.user)
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.character = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)
        self._wire_account_to_character(self.sheet)

    def _wire_account_to_character(self, sheet) -> None:
        """Give ``self.user`` an active roster tenure over ``sheet``'s character."""
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=self.player_data)

    def test_requires_authentication(self) -> None:
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_missing_character_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unowned_character_is_404(self) -> None:
        other_sheet = CharacterSheetFactory()
        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": other_sheet.pk})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_empty_room_returns_empty_list(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_character_with_no_location_returns_empty_list(self) -> None:
        homeless = CharacterFactory(location=None)
        homeless_sheet = CharacterSheetFactory(character=homeless)
        self._wire_account_to_character(homeless_sheet)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": homeless_sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_not_hidden_armed_trap_is_visible_with_no_detection(self) -> None:
        trap = TrapFactory(room_profile=self.room_profile, is_hidden=False, name="Obvious Snare")

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data] == [trap.pk]
        assert response.data[0] == {
            "id": trap.pk,
            "name": "Obvious Snare",
            "is_armed": True,
        }

    def test_hidden_undetected_trap_is_invisible(self) -> None:
        TrapFactory(room_profile=self.room_profile, is_hidden=True)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_hidden_trap_visible_once_this_character_detected_it(self) -> None:
        trap = TrapFactory(room_profile=self.room_profile, is_hidden=True, name="Spike Pit")
        trap.detected_by.add(self.sheet)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data] == [trap.pk]

    def test_disarmed_trap_never_listed_even_if_detected(self) -> None:
        trap = TrapFactory(room_profile=self.room_profile, is_hidden=True, is_armed=False)
        trap.detected_by.add(self.sheet)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_another_characters_detection_does_not_leak_to_a_co_located_viewer(self) -> None:
        """The leak table's core case: a hidden trap detected by character B is
        invisible to character A even though both stand in the same room."""
        trap = TrapFactory(room_profile=self.room_profile, is_hidden=True, name="Spike Pit")

        detector = CharacterFactory(location=self.room)
        detector_sheet = CharacterSheetFactory(character=detector)
        trap.detected_by.add(detector_sheet)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_serializer_never_leaks_consequence_pool_or_difficulty(self) -> None:
        trap = TrapFactory(room_profile=self.room_profile, is_hidden=False)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(ROOM_TRAPS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        row = response.data[0]
        assert set(row.keys()) == {"id", "name", "is_armed"}
        assert row["id"] == trap.pk
