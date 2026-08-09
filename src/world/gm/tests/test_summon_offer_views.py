"""API tests for the GM summon offer inbox endpoint (#3071).

GET /api/gm/summon-offers/ returns the requesting player's pending
GMSummonOffer rows, scoped to the characters they currently play — the same
poll-and-toast shape ``DuelChallengeViewSet`` established (see
``world.combat.tests.test_duel_challenge_inbox``).
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.areas.services import get_room_profile
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.models import GMSummonOffer
from world.gm.services import offer_gm_summon
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory

_INBOX_URL = "/api/gm/summon-offers/"


class GMSummonOfferInboxTests(TestCase):
    """GET /api/gm/summon-offers/ scopes to the caller's played characters."""

    @classmethod
    def setUpTestData(cls) -> None:
        gm_room = ObjectDBFactory(
            db_key="SummonInboxGMRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        cls.room_profile = get_room_profile(gm_room)
        cls.scene = SceneFactory(location=gm_room, name="Summon Inbox Scene")

        cls.target_account = AccountFactory(username="summon_inbox_target")
        cls.target_character = CharacterFactory(db_key="SummonInboxTarget")
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=cls.target_character,
            player_data__account=cls.target_account,
        )

        # A third player uninvolved in any summon — must see an empty inbox.
        cls.bystander_account = AccountFactory(username="summon_inbox_bystander")
        cls.bystander_character = CharacterFactory(db_key="SummonInboxBystander")
        CharacterSheetFactory(character=cls.bystander_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=cls.bystander_character,
            player_data__account=cls.bystander_account,
        )

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.offer = offer_gm_summon(
            None,
            self.target_sheet,
            room=self.room_profile,
            scene=self.scene,
            gm_display_name="Story Weaver",
        )

    def _client(self, account: object) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_requires_authentication(self) -> None:
        response = APIClient().get(_INBOX_URL)
        self.assertIn(
            response.status_code,
            (http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN),
        )

    def test_target_sees_their_pending_offer(self) -> None:
        response = self._client(self.target_account).get(_INBOX_URL)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], self.offer.pk)
        self.assertEqual(payload[0]["gm_display_name"], "Story Weaver")
        self.assertEqual(payload[0]["scene_title"], "Summon Inbox Scene")

    def test_bystander_sees_an_empty_inbox(self) -> None:
        response = self._client(self.bystander_account).get(_INBOX_URL)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_resolved_offer_disappears_from_the_inbox(self) -> None:
        GMSummonOffer.objects.filter(pk=self.offer.pk).delete()
        response = self._client(self.target_account).get(_INBOX_URL)
        self.assertEqual(response.json(), [])
