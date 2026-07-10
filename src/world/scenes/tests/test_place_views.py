"""Tests for the PlaceSerializer's viewer_is_present field (#2156)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PlaceFactory, PlacePresenceFactory


class PlaceViewerIsPresentTests(APITestCase):
    """GET /api/places/?room=<room.id> reports whether the viewer's persona is present."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = self.room
        self.client.force_authenticate(user=self.account)
        self.url = reverse("place-list")

    def test_viewer_is_present_true_when_persona_has_presence(self) -> None:
        place = PlaceFactory(room=self.room, name="Bar")
        PlacePresenceFactory(place=place, persona=self.persona)

        response = self.client.get(self.url, {"room": self.room.pk})

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["viewer_is_present"] is True

    def test_viewer_is_present_false_when_no_presence(self) -> None:
        PlaceFactory(room=self.room, name="Corner")

        response = self.client.get(self.url, {"room": self.room.pk})

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["viewer_is_present"] is False

    def test_unauthenticated_request_is_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        PlaceFactory(room=self.room, name="Bar")

        response = self.client.get(self.url, {"room": self.room.pk})

        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }
