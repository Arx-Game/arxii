"""API tests for GET /api/locations/comfort/ (#1522).

The per-character comfort read is personal: it requires auth and only serves a character the
requesting account actually plays.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)

COMFORT_URL = "/api/locations/comfort/"


class ComfortSummaryApiTest(APITestCase):
    def setUp(self) -> None:
        self.user = AccountFactory()
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.room = RoomProfileFactory(area=self.ward).objectdb

        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.location = self.room
        # Wire the account to the character via an active roster tenure so for_account finds it.
        entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=self.user),
        )

    def _make_cold(self, cold: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.COLD,
            value=cold,
        )

    def test_requires_authentication(self) -> None:
        response = self.client.get(COMFORT_URL, {"character_id": self.sheet.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_missing_character_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        assert self.client.get(COMFORT_URL).status_code == status.HTTP_400_BAD_REQUEST

    def test_unowned_character_is_404(self) -> None:
        other_sheet = CharacterSheetFactory()
        self.client.force_authenticate(user=self.user)
        response = self.client.get(COMFORT_URL, {"character_id": other_sheet.pk})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reports_comfort_band_and_reasons(self) -> None:
        self._make_cold(50)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(COMFORT_URL, {"character_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["discomfort"] == 50
        assert response.data["band"] == "Moderately uncomfortable"
        assert response.data["reasons"] == ["cold"]
        assert response.data["felt"] == {"cold": 50}

    def test_comfortable_character_reports_empty_reasons(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(COMFORT_URL, {"character_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["discomfort"] == 0
        assert response.data["band"] == "Comfortable"
        assert response.data["reasons"] == []
        assert response.data["felt"] == {}
