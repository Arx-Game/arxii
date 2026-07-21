"""Tests for the aura glimpse @actions on CharacterAuraViewSet (#2427)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.distinctions.factories import CharacterDistinctionFactory
from world.magic.constants import GlimpseState, GlimpseTagAxis
from world.magic.factories import CharacterAuraFactory, GlimpseTagFactory
from world.roster.factories import RosterTenureFactory


class GlimpseAuraActionTestBase(TestCase):
    """Shared owner/aura fixture for the four glimpse actions."""

    @classmethod
    def setUpTestData(cls):
        cls.tenure = RosterTenureFactory()
        cls.account = cls.tenure.player_data.account
        cls.character = cls.tenure.roster_entry.character_sheet.character
        cls.aura = CharacterAuraFactory(character=cls.character)

        cls.other_tenure = RosterTenureFactory()
        cls.other_account = cls.other_tenure.player_data.account

        cls.tone_a = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-a")
        cls.tone_b = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-b")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _url(self, action: str) -> str:
        return f"/api/magic/character-auras/{self.aura.pk}/{action}/"


class SetGlimpseTagsActionTest(GlimpseAuraActionTestBase):
    def test_owner_sets_tags_for_axis(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["glimpse_state"] == GlimpseState.TAGS_ONLY

    def test_tone_multi_select_rejected(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id, self.tone_b.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_tag_id_rejected(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"axis": GlimpseTagAxis.TONE, "tag_ids": [999999]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_gets_404(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class SetGlimpseProseActionTest(GlimpseAuraActionTestBase):
    def test_owner_sets_prose_and_completes(self):
        response = self.client.post(
            self._url("set-glimpse-prose"),
            {"text": "I saw the threads unravel."},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["glimpse_state"] == GlimpseState.COMPLETE

    def test_non_owner_gets_404(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("set-glimpse-prose"),
            {"text": "Not my aura."},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class GlimpseDistinctionLinkActionTest(GlimpseAuraActionTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.character_distinction = CharacterDistinctionFactory(character=cls.character.sheet_data)
        cls.foreign_distinction = CharacterDistinctionFactory()  # different character

    def test_link_sets_from_glimpse(self):
        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        self.character_distinction.refresh_from_db()
        assert self.character_distinction.from_glimpse_id == self.aura.pk

    def test_unlink_clears_from_glimpse(self):
        self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        response = self.client.post(
            self._url("unlink-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        self.character_distinction.refresh_from_db()
        assert self.character_distinction.from_glimpse_id is None

    def test_linking_another_characters_distinction_404s(self):
        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.foreign_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owner_gets_404_on_link(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owner_gets_404_on_unlink(self):
        self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("unlink-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
