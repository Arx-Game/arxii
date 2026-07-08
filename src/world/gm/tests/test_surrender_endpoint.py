"""Tests for POST /api/stories/{id}/surrender/ — GM surrenders oversight (#2004)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.narrative.models import NarrativeMessage
from world.stories.constants import StoryScope
from world.stories.factories import StoryFactory


class StorySurrenderEndpointTest(APITestCase):
    """POST /api/stories/{id}/surrender/ — Lead GM surrenders oversight."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.non_gm_account = AccountFactory()
        cls.character_sheet = CharacterSheetFactory()

    def _make_story(self) -> object:
        return StoryFactory(
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
            scope=StoryScope.CHARACTER,
            character_sheet=self.character_sheet,
        )

    def test_lead_gm_can_surrender(self) -> None:
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("story-surrender", kwargs={"pk": story.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        story.refresh_from_db()
        self.assertIsNone(story.primary_table)

    def test_non_gm_cannot_surrender(self) -> None:
        story = self._make_story()
        self.client.force_authenticate(user=self.non_gm_account)
        url = reverse("story-surrender", kwargs={"pk": story.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        story.refresh_from_db()
        self.assertIsNotNone(story.primary_table)

    def test_surrender_notifies_player(self) -> None:
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("story-surrender", kwargs={"pk": story.pk})
        self.client.post(url)
        self.assertTrue(NarrativeMessage.objects.filter(related_story=story).exists())

    def test_surrender_stamps_gm_activity(self) -> None:
        story = self._make_story()
        self.assertIsNone(self.lead_gm_profile.last_active_at)
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("story-surrender", kwargs={"pk": story.pk})
        self.client.post(url)
        self.lead_gm_profile.refresh_from_db()
        self.assertIsNotNone(self.lead_gm_profile.last_active_at)
