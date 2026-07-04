"""Tests for POST /api/stories/{id}/resolve-foreclosure/.

Covers the strict 3-layer pattern: IsLeadGMOnStoryOrStaff permission,
ResolveForeclosureInputSerializer validation (scope match + FORECLOSED state),
and resolved_by stamped from request.user.gm_profile.
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.completion import complete_story
from world.stories.types import StoryStatus


class ResolveForeclosureEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Lead GM fixture: Account -> GMProfile -> GMTable -> Story.
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

    def _story_with_foreclosed_character_progress(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(
            status=StoryStatus.ACTIVE,
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
        )
        progress = StoryProgressFactory(
            story=story, character_sheet=sheet, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        return story, progress

    def _url(self, story):
        return reverse("story-resolve-foreclosure", kwargs={"pk": story.pk})

    def test_lead_gm_resolves_foreclosed_character_progress(self):
        story, progress = self._story_with_foreclosed_character_progress()
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(
            self._url(story),
            json.dumps(
                {"scope": StoryScope.CHARACTER, "character_sheet": story.character_sheet_id}
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        progress.refresh_from_db()
        assert progress.resolved_at is not None
        assert progress.resolved_by_id == self.lead_gm_profile.pk

    def test_staff_resolves_foreclosed_character_progress(self):
        story, progress = self._story_with_foreclosed_character_progress()
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.post(
            self._url(story),
            json.dumps(
                {"scope": StoryScope.CHARACTER, "character_sheet": story.character_sheet_id}
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        progress.refresh_from_db()
        assert progress.resolved_at is not None

    def test_non_lead_gm_forbidden(self):
        story, _ = self._story_with_foreclosed_character_progress()
        self.client.force_authenticate(user=self.unrelated_account)
        response = self.client.post(
            self._url(story),
            json.dumps(
                {"scope": StoryScope.CHARACTER, "character_sheet": story.character_sheet_id}
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_scope_mismatch_returns_400(self):
        story, _ = self._story_with_foreclosed_character_progress()
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(
            self._url(story),
            json.dumps({"scope": StoryScope.GROUP}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_foreclosed_progress_returns_400(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(
            status=StoryStatus.ACTIVE,
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
        )
        StoryProgressFactory(
            story=story, character_sheet=sheet, status=ProgressStatus.ACTIVE, is_active=True
        )
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(
            self._url(story),
            json.dumps(
                {"scope": StoryScope.CHARACTER, "character_sheet": story.character_sheet_id}
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_lead_gm_resolves_group_progress(self):
        story = StoryFactory(
            status=StoryStatus.ACTIVE,
            scope=StoryScope.GROUP,
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
        )
        progress = GroupStoryProgressFactory(
            story=story, gm_table=self.gm_table, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(
            self._url(story),
            json.dumps({"scope": StoryScope.GROUP, "gm_table": self.gm_table.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        progress.refresh_from_db()
        assert progress.resolved_at is not None
