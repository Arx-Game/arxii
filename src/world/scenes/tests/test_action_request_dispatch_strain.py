"""Tests for strain_commitment validation on the dispatch endpoint.

Covers:
- POST /api/action-requests/ rejects strain_commitment > anima.current with 400.
- POST /api/action-requests/ accepts strain_commitment within the anima cap.
- POST /api/action-requests/ rejects strain > 0 when no CharacterAnima row exists.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterAnimaFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory


class DispatchActionRequestStrainTests(APITestCase):
    """Strain_commitment is validated against the initiator's available anima."""

    @classmethod
    def setUpTestData(cls) -> None:
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

        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.target_character
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def _url(self) -> str:
        return reverse("sceneactionrequest-list")

    def _payload(self, **overrides: object) -> dict:
        data: dict[str, object] = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona": self.target_persona.pk,
            "action_key": "intimidate",
        }
        data.update(overrides)
        return data

    def test_strain_commitment_validated_against_anima(self) -> None:
        """Strain_commitment greater than available anima → 400."""
        CharacterAnimaFactory(character=self.character, current=5, maximum=10)
        response = self.client.post(
            self._url(),
            self._payload(strain_commitment=20),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("strain_commitment", response.data)

    def test_strain_within_cap_accepted(self) -> None:
        """Strain_commitment within the anima cap → 201."""
        CharacterAnimaFactory(character=self.character, current=10, maximum=10)
        response = self.client.post(
            self._url(),
            self._payload(strain_commitment=5),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_strain_zero_default_with_no_anima(self) -> None:
        """No anima row + no strain commit → 201 (strain defaults to 0)."""
        response = self.client.post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_strain_nonzero_without_anima_rejected(self) -> None:
        """Strain commit > 0 with no CharacterAnima row → 400."""
        response = self.client.post(
            self._url(),
            self._payload(strain_commitment=3),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("strain_commitment", response.data)
