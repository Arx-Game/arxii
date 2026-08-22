"""Tests for the tavern games API (#3292): /api/tavern-games/games/ + /sessions/.

Every write dispatches the matching REGISTRY action, mirroring
``world.scenes.tests.test_action_views.PlaceViewSetTestCase``.
"""

from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PlaceFactory
from world.scenes.place_models import PlacePresence
from world.tavern_games.constants import GameSessionState
from world.tavern_games.factories import TavernGameFactory
from world.tavern_games.models import GameSession


class TavernGamesViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.identity = CharacterSheetFactory()
        cls.character = cls.identity.character
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.identity)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.persona = cls.identity.primary_persona
        cls.room_obj = ObjectDBFactory(db_key="Tavern", db_typeclass_path="typeclasses.rooms.Room")
        cls.room_profile = RoomProfileFactory(objectdb=cls.room_obj, is_social_hub=True)
        cls.game = TavernGameFactory(min_ante=1, max_ante=1000)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)
        self.place = PlaceFactory(room=self.room_profile, name="Bar")
        PlacePresence.objects.create(place=self.place, persona=self.persona)
        transfer(amount=100, reason="test seed", to_purse=get_or_create_purse(self.identity))

    def test_list_games(self) -> None:
        url = reverse("tavern-game-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert self.game.pk in {row["id"] for row in response.data["results"]}

    def test_open_session_debits_ante_and_returns_session(self) -> None:
        url = reverse("tavern-game-session-open")
        response = self.client.post(
            url, {"place": self.place.pk, "game": self.game.pk, "ante": 10}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["pot"] == 10
        assert get_or_create_purse(self.identity).balance == 90

    def test_open_without_being_present_refuses(self) -> None:
        PlacePresence.objects.filter(place=self.place, persona=self.persona).delete()
        url = reverse("tavern-game-session-open")
        response = self.client.post(
            url, {"place": self.place.pk, "game": self.game.pk, "ante": 10}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not GameSession.objects.filter(place=self.place).exists()

    def test_join_session_grows_the_pot(self) -> None:
        session = GameSession.objects.create(
            place=self.place, game=self.game, ante=10, opened_by=self.persona
        )
        url = reverse("tavern-game-session-join", kwargs={"pk": session.pk})
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["pot"] == 10
        assert get_or_create_purse(self.identity).balance == 90

    def test_leave_session_refunds(self) -> None:
        open_url = reverse("tavern-game-session-open")
        opened = self.client.post(
            open_url, {"place": self.place.pk, "game": self.game.pk, "ante": 10}, format="json"
        )
        session_id = opened.data["id"]

        leave_url = reverse("tavern-game-session-leave", kwargs={"pk": session_id})
        response = self.client.post(leave_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["state"] == GameSessionState.ABANDONED
        assert get_or_create_purse(self.identity).balance == 100

    def test_roll_without_a_second_player_refuses(self) -> None:
        open_url = reverse("tavern-game-session-open")
        opened = self.client.post(
            open_url, {"place": self.place.pk, "game": self.game.pk, "ante": 10}, format="json"
        )
        session_id = opened.data["id"]

        roll_url = reverse("tavern-game-session-roll", kwargs={"pk": session_id})
        with patch("world.tavern_games.services.random.randint", return_value=3):
            response = self.client.post(roll_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_request_is_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("tavern-game-session-list")
        response = self.client.get(url)
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }
