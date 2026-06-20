"""API tests for the duel-challenge inbox endpoint (#1180).

GET /api/combat/duel-challenges/ returns the requesting player's PENDING
DuelChallenges (as challenger and/or challenged), scoped to the characters they
currently play, with an optional ``?role=incoming|outgoing`` narrowing.
"""

from __future__ import annotations

from django.db.models import Q
from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import DuelChallengeStatus
from world.combat.factories import DuelChallengeFactory
from world.combat.models import DuelChallenge
from world.combat.serializers import DuelChallengeSerializer
from world.roster.factories import RosterTenureFactory

_INBOX_URL = "/api/combat/duel-challenges/"


class DuelChallengeInboxTests(TestCase):
    """GET /api/combat/duel-challenges/ scopes to the caller's played characters."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.challenger_account = AccountFactory(username="duel_inbox_challenger")
        cls.challenger_character = CharacterFactory(db_key="DuelInboxChallenger")
        cls.challenger_sheet = CharacterSheetFactory(character=cls.challenger_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=cls.challenger_character,
            player_data__account=cls.challenger_account,
        )

        cls.challenged_account = AccountFactory(username="duel_inbox_challenged")
        cls.challenged_character = CharacterFactory(db_key="DuelInboxChallenged")
        cls.challenged_sheet = CharacterSheetFactory(character=cls.challenged_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=cls.challenged_character,
            player_data__account=cls.challenged_account,
        )

        # A third player uninvolved in any challenge — must see an empty inbox.
        cls.bystander_account = AccountFactory(username="duel_inbox_bystander")
        cls.bystander_character = CharacterFactory(db_key="DuelInboxBystander")
        CharacterSheetFactory(character=cls.bystander_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=cls.bystander_character,
            player_data__account=cls.bystander_account,
        )

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.challenge = DuelChallengeFactory(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=self.challenged_sheet,
            status=DuelChallengeStatus.PENDING,
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

    def test_challenged_player_sees_incoming_challenge(self) -> None:
        response = self._client(self.challenged_account).get(_INBOX_URL)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["id"], self.challenge.pk)
        self.assertEqual(row["status"], DuelChallengeStatus.PENDING)
        self.assertEqual(row["challenger"]["id"], self.challenger_sheet.pk)
        self.assertEqual(row["challenger"]["name"], self.challenger_character.db_key)
        self.assertEqual(row["challenged"]["id"], self.challenged_sheet.pk)

    def test_challenger_player_sees_outgoing_challenge(self) -> None:
        response = self._client(self.challenger_account).get(_INBOX_URL)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.challenge.pk)

    def test_bystander_sees_empty_inbox(self) -> None:
        response = self._client(self.bystander_account).get(_INBOX_URL)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])

    def test_role_incoming_excludes_outgoing(self) -> None:
        """For the challenger, ?role=incoming has no rows (their challenge is outgoing)."""
        response = self._client(self.challenger_account).get(_INBOX_URL, {"role": "incoming"})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])

    def test_role_outgoing_returns_outgoing(self) -> None:
        response = self._client(self.challenger_account).get(_INBOX_URL, {"role": "outgoing"})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.challenge.pk)

    def test_non_pending_challenge_excluded(self) -> None:
        self.challenge.status = DuelChallengeStatus.DECLINED
        self.challenge.save(update_fields=["status"])
        response = self._client(self.challenged_account).get(_INBOX_URL)
        self.assertEqual(response.data["results"], [])

    def test_inbox_queryset_is_select_related(self) -> None:
        """The inbox queryset's select_related keeps serialization N+1-free across rows."""
        DuelChallengeFactory(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=CharacterSheetFactory(
                character=CharacterFactory(db_key="DuelInboxAlt")
            ),
            status=DuelChallengeStatus.PENDING,
        )
        played_ids = self.challenger_account.played_character_sheet_ids
        qs = (
            DuelChallenge.objects.filter(status=DuelChallengeStatus.PENDING)
            .filter(Q(challenger_sheet_id__in=played_ids) | Q(challenged_sheet_id__in=played_ids))
            .select_related("challenger_sheet__character", "challenged_sheet__character")
        )
        with self.assertNumQueries(1):
            data = DuelChallengeSerializer(list(qs), many=True).data
        self.assertEqual(len(data), 2)
