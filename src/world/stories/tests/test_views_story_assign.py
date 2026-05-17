"""Tests for StoryViewSet.assign — Task B2.

Covers POST /api/stories/{id}/assign-to-scope/ which lifts a Story out of
UNASSIGNED scope: it sets ``Story.scope`` and creates the matching progress
record (StoryProgress / GroupStoryProgress / GlobalStoryProgress) so the
story can run.

The scope <-> target invariant (CHARACTER requires character_sheet only;
GROUP requires gm_table only; GLOBAL forbids both; UNASSIGNED is not a
valid input scope) is enforced in AssignStoryInputSerializer.validate(),
so any violation returns 400 with no scope change and no progress row.
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import StoryScope
from world.stories.factories import StoryFactory
from world.stories.models import (
    GlobalStoryProgress,
    GroupStoryProgress,
    StoryProgress,
)


class StoryAssignViewSetTest(APITestCase):
    """Tests for POST /api/stories/{id}/assign-to-scope/."""

    @classmethod
    def setUpTestData(cls):
        # Story owner / Lead GM (mirrors the promote / resolve Lead-GM fixture:
        # AccountFactory -> GMProfileFactory -> GMTableFactory ->
        # StoryFactory(owners=[...], primary_table=...)).
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.unrelated_account = AccountFactory()

        cls.character_sheet = CharacterSheetFactory()

    def _make_story(self):
        """Create an UNASSIGNED story owned by / led by the Lead GM."""
        return StoryFactory(
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
            scope=StoryScope.UNASSIGNED,
        )

    def _post(self, story, payload):
        url = reverse("story-assign", kwargs={"pk": story.pk})
        return self.client.post(
            url,
            json.dumps(payload),
            content_type="application/json",
        )

    # ------------------------------------------------------------------
    # Happy paths
    # ------------------------------------------------------------------

    def test_assign_character_scope_creates_story_progress(self):
        """CHARACTER scope sets scope + character_sheet and creates StoryProgress."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(
            story,
            {"scope": "character", "character_sheet": self.character_sheet.pk},
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.CHARACTER
        assert story.character_sheet_id == self.character_sheet.pk
        assert response.data["scope"] == "character"
        assert StoryProgress.objects.filter(
            story=story, character_sheet=self.character_sheet
        ).exists()

    def test_assign_group_scope_creates_group_progress(self):
        """GROUP scope sets scope and creates GroupStoryProgress for the table."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "group", "gm_table": self.gm_table.pk})

        assert response.status_code == status.HTTP_200_OK, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.GROUP
        assert response.data["scope"] == "group"
        assert GroupStoryProgress.objects.filter(story=story, gm_table=self.gm_table).exists()

    def test_assign_global_scope_creates_global_progress(self):
        """GLOBAL scope sets scope and creates the GlobalStoryProgress singleton."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "global"})

        assert response.status_code == status.HTTP_200_OK, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.GLOBAL
        assert response.data["scope"] == "global"
        assert GlobalStoryProgress.objects.filter(story=story).exists()

    def test_staff_can_assign(self):
        """Staff (not the Lead GM) may also assign scope."""
        story = self._make_story()
        staff_account = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff_account)

        response = self._post(story, {"scope": "global"})

        assert response.status_code == status.HTTP_200_OK, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.GLOBAL

    # ------------------------------------------------------------------
    # Invalid combinations -> 400, no scope change, no progress
    # ------------------------------------------------------------------

    def _assert_unchanged(self, story):
        story.refresh_from_db()
        assert story.scope == StoryScope.UNASSIGNED
        assert not StoryProgress.objects.filter(story=story).exists()
        assert not GroupStoryProgress.objects.filter(story=story).exists()
        assert not GlobalStoryProgress.objects.filter(story=story).exists()

    def test_character_scope_missing_character_sheet_is_400(self):
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "character"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self._assert_unchanged(story)

    def test_character_scope_with_wrong_target_is_400(self):
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "character", "gm_table": self.gm_table.pk})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self._assert_unchanged(story)

    def test_group_scope_missing_gm_table_is_400(self):
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "group"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self._assert_unchanged(story)

    def test_unassigned_scope_is_rejected(self):
        """UNASSIGNED is not a valid input scope (cannot assign TO unassigned)."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(story, {"scope": "unassigned"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self._assert_unchanged(story)

    def test_global_scope_with_extraneous_target_is_400(self):
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        response = self._post(
            story,
            {"scope": "global", "character_sheet": self.character_sheet.pk},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self._assert_unchanged(story)

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    @suppress_permission_errors
    def test_unrelated_user_forbidden(self):
        """A non-owner, non-Lead-GM, non-staff user gets 403."""
        story = self._make_story()
        self.client.force_authenticate(user=self.unrelated_account)

        response = self._post(story, {"scope": "global"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        self._assert_unchanged(story)
