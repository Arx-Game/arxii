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

    def test_list_page_reuses_owned_persona_lookup_across_rows(self) -> None:
        """A list page's N rows share ONE owned-persona lookup, not N (#2156 review fold-in).

        Pinned to 18 queries for GET /api/places/?room=<room.id> with 3 places on the
        page (observed via assertNumQueries's captured-query dump; composition below —
        renumber this comment if the count ever legitimately changes):
        1. session lookup (`force_authenticate`/session auth)
        2-4. SAVEPOINT / INSERT / RELEASE SAVEPOINT (session-creation bookkeeping)
        5. Place COUNT (pagination)
        6. Place list SELECT (filtered/ordered/paginated)
        7. PlacePresence COUNT for place 1 (`get_presence_count`)
        8-10. get_account_personas' PlayerData -> RosterEntry -> Persona chain — runs
           ONCE for the whole page (memoized by `PlaceSerializer._owned_persona_ids`);
           this is the exact N-per-row duplication this test guards against
        11. PlacePresence.exists() for place 1 (`get_viewer_is_present`)
        12. PlacePresence COUNT for place 2
        13. PlacePresence.exists() for place 2 (persona ids reused from cache, no re-query)
        14. PlacePresence COUNT for place 3
        15. PlacePresence.exists() for place 3 (persona ids reused from cache, no re-query)
        16-18. SAVEPOINT / session UPDATE / RELEASE SAVEPOINT (session-teardown bookkeeping)
        """
        for name in ("Bar", "Corner", "Hearth"):
            PlaceFactory(room=self.room, name=name)

        with self.assertNumQueries(18):
            response = self.client.get(self.url, {"room": self.room.pk})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3
