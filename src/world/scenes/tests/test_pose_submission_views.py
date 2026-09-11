"""Tests for the writer-only PoseSubmission lookup endpoint (#3760).

A client asks "did my submission land?" by client_request_id. Owner-only:
a non-owner's lookup must 404, not 403 -- a resend attempt is not proof of
authorship, and a 403 would still confirm the row exists.
"""

import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import idempotent_record_interaction


class PoseSubmissionViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        def build_account():
            account = AccountFactory()
            character = CharacterFactory()
            roster_entry = RosterEntryFactory(character_sheet__character=character)
            player_data = PlayerDataFactory(account=account)
            RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
            return account, character, roster_entry.character_sheet.primary_persona

        cls.account, cls.character, cls.persona = build_account()
        cls.other_account, cls.other_character, cls.other_persona = build_account()

    def _url(self, client_request_id: uuid.UUID) -> str:
        return reverse(
            "pose-submission-detail",
            kwargs={"client_request_id": str(client_request_id)},
        )

    def test_url_matches_confirmed_spec_path(self) -> None:
        """Guards the literal path the spec names (#3760 Task 6 Interfaces)."""
        request_id = uuid.uuid4()
        self.assertEqual(
            self._url(request_id),
            f"/api/scenes/submissions/{request_id}/",
        )

    def test_owner_can_look_up_their_own_submission(self) -> None:
        request_id = uuid.uuid4()
        idempotent_record_interaction(
            persona=self.persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=self.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(self._url(request_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["interaction_id"])
        self.assertTrue(response.data["replayed"])

    def test_non_owner_gets_404_not_someone_elses_submission(self) -> None:
        request_id = uuid.uuid4()
        idempotent_record_interaction(
            persona=self.persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=self.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        self.client.force_authenticate(user=self.other_account)
        response = self.client.get(self._url(request_id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_request_id_gets_404(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(self._url(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_gets_no_data(self) -> None:
        request_id = uuid.uuid4()
        idempotent_record_interaction(
            persona=self.persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=self.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        response = self.client.get(self._url(request_id))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_endpoint_is_read_only(self) -> None:
        """No create/update/delete is exposed on this lookup."""
        request_id = uuid.uuid4()
        idempotent_record_interaction(
            persona=self.persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=self.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        self.client.force_authenticate(user=self.account)
        url = self._url(request_id)
        self.assertEqual(
            self.client.post(url, {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(url, {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
