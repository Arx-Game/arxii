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

    # ------------------------------------------------------------------
    # Re-assignment of an already-assigned story -> 400, state unchanged
    #
    # The assign contract is "lift a story OUT of UNASSIGNED". A story whose
    # scope is no longer UNASSIGNED must not be re-assigned: doing so either
    # 500s (duplicate progress IntegrityError) or, worse, silently commits
    # contradictory progress records (CHARACTER -> GROUP). The Layer-2 guard
    # in AssignStoryInputSerializer.validate() rejects any non-UNASSIGNED
    # target with 400 and no state change.
    # ------------------------------------------------------------------

    def test_reassign_character_to_character_rejected(self):
        """A CHARACTER story re-assigned to CHARACTER is 400, not a 500."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        first = self._post(
            story,
            {"scope": "character", "character_sheet": self.character_sheet.pk},
        )
        assert first.status_code == status.HTTP_200_OK, first.data

        response = self._post(
            story,
            {"scope": "character", "character_sheet": self.character_sheet.pk},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.CHARACTER
        assert story.character_sheet_id == self.character_sheet.pk
        assert StoryProgress.objects.filter(story=story).count() == 1
        assert not GroupStoryProgress.objects.filter(story=story).exists()
        assert not GlobalStoryProgress.objects.filter(story=story).exists()

    def test_reassign_global_to_global_rejected(self):
        """A GLOBAL story re-assigned to GLOBAL is 400, not a 500."""
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        first = self._post(story, {"scope": "global"})
        assert first.status_code == status.HTTP_200_OK, first.data

        response = self._post(story, {"scope": "global"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.GLOBAL
        assert GlobalStoryProgress.objects.filter(story=story).count() == 1
        assert not StoryProgress.objects.filter(story=story).exists()
        assert not GroupStoryProgress.objects.filter(story=story).exists()

    def test_reassign_character_to_group_rejected(self):
        """A CHARACTER story re-assigned to GROUP is cleanly rejected (400).

        This is the silent-corruption case: pre-fix it returned 200 with a
        stale ``character_sheet``, an orphan StoryProgress, AND a new
        GroupStoryProgress. The Layer-2 guard rejects it with 400 and the
        story keeps exactly its original CHARACTER state.
        """
        story = self._make_story()
        self.client.force_authenticate(user=self.lead_gm_account)

        first = self._post(
            story,
            {"scope": "character", "character_sheet": self.character_sheet.pk},
        )
        assert first.status_code == status.HTTP_200_OK, first.data

        response = self._post(story, {"scope": "group", "gm_table": self.gm_table.pk})

        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        story.refresh_from_db()
        assert story.scope == StoryScope.CHARACTER
        assert story.character_sheet_id == self.character_sheet.pk
        assert not GroupStoryProgress.objects.filter(story=story).exists()
        assert not GlobalStoryProgress.objects.filter(story=story).exists()
        assert StoryProgress.objects.filter(story=story).count() == 1
