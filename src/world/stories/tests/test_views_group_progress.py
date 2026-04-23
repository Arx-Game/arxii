"""Tests for GroupStoryProgressViewSet — permission matrix, CRUD, filters."""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StoryFactory,
)


def _create_member_persona(account):
    """Create a Persona linked to account via character_sheet -> character -> db_account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    sheet = CharacterSheetFactory(character=char)
    return PersonaFactory(character_sheet=sheet)


class GroupStoryProgressViewSetPermissionTest(APITestCase):
    """Test the GroupStoryProgressViewSet permission matrix."""

    @classmethod
    def setUpTestData(cls):
        # Staff account
        cls.staff = AccountFactory(is_staff=True)

        # Lead GM account — has a GMProfile and owns the GMTable
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # Member account — has an active GMTableMembership via persona -> char -> account
        cls.member_account = AccountFactory()
        cls.member_persona = _create_member_persona(cls.member_account)
        cls.membership = GMTableMembershipFactory(
            table=cls.gm_table,
            persona=cls.member_persona,
        )

        # Unrelated account — no relationship to the table
        cls.unrelated_account = AccountFactory()

        # A GROUP-scope story with a progress record
        cls.story = StoryFactory(scope=StoryScope.GROUP)
        cls.progress = GroupStoryProgressFactory(
            story=cls.story,
            gm_table=cls.gm_table,
        )

    # ---------- list --------------------------------------------------------

    def test_staff_can_list(self):
        """Staff can list all group progress records."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_member_can_list_their_table(self):
        """Active table member can list progress records for their table."""
        self.client.force_authenticate(user=self.member_account)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.progress.id in ids

    def test_unrelated_user_sees_empty_list(self):
        """Unrelated authenticated user gets an empty queryset (not 403)."""
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    @suppress_permission_errors
    def test_unauthenticated_cannot_list(self):
        """Unauthenticated requests are rejected."""
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------- retrieve ----------------------------------------------------

    def test_member_can_retrieve(self):
        """Active table member can retrieve a progress record."""
        self.client.force_authenticate(user=self.member_account)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.progress.id

    @suppress_permission_errors
    def test_unrelated_user_cannot_retrieve(self):
        """Unrelated user gets 404 or 403 on retrieve (queryset filters them out)."""
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.get(url)
        # queryset filtering produces 404 for objects not in filtered qs
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    # ---------- create -------------------------------------------------------

    def test_staff_can_create(self):
        """Staff can create a group progress record."""
        other_story = StoryFactory(scope=StoryScope.GROUP)
        other_table = GMTableFactory(gm=self.lead_gm_profile)
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        data = {
            "story": other_story.id,
            "gm_table": other_table.id,
            "is_active": True,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_lead_gm_can_create(self):
        """Lead GM of the table can create a progress record for that table."""
        other_story = StoryFactory(scope=StoryScope.GROUP)
        other_table = GMTableFactory(gm=self.lead_gm_profile)
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("groupstoryprogress-list")
        data = {
            "story": other_story.id,
            "gm_table": other_table.id,
            "is_active": True,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_member_cannot_create(self):
        """Table member (non-Lead-GM) cannot create progress records."""
        other_story = StoryFactory(scope=StoryScope.GROUP)
        self.client.force_authenticate(user=self.member_account)
        url = reverse("groupstoryprogress-list")
        data = {
            "story": other_story.id,
            "gm_table": self.gm_table.id,
            "is_active": True,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ---------- update -------------------------------------------------------

    def test_staff_can_update(self):
        """Staff can update a progress record."""
        # Create a fresh record (no current_episode) to avoid stale FK with --keepdb.
        fresh_story = StoryFactory(scope=StoryScope.GROUP)
        fresh_table = GMTableFactory(gm=self.lead_gm_profile)
        fresh_progress = GroupStoryProgressFactory(
            story=fresh_story, gm_table=fresh_table, current_episode=None
        )
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": fresh_progress.pk})
        data = {"is_active": False}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    def test_lead_gm_can_update_own_table(self):
        """Lead GM can update progress for their own table."""
        fresh_story = StoryFactory(scope=StoryScope.GROUP)
        fresh_table = GMTableFactory(gm=self.lead_gm_profile)
        fresh_progress = GroupStoryProgressFactory(
            story=fresh_story, gm_table=fresh_table, current_episode=None
        )
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": fresh_progress.pk})
        data = {"is_active": False}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_member_cannot_update(self):
        """Regular table member cannot update progress records."""
        self.client.force_authenticate(user=self.member_account)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": self.progress.pk})
        data = {"is_active": False}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ---------- filters ------------------------------------------------------

    def test_filter_by_story(self):
        """Filter by story ID returns only matching records."""
        other_story = StoryFactory(scope=StoryScope.GROUP)
        other_table = GMTableFactory(gm=self.lead_gm_profile)
        other_progress = GroupStoryProgressFactory(story=other_story, gm_table=other_table)  # noqa: F841

        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url, {"story": self.story.id})
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.progress.id in ids
        for r_id in ids:
            # All returned records must belong to the filtered story
            assert r_id == self.progress.id

    def test_filter_by_is_active(self):
        """Filter by is_active returns only active/inactive records."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url, {"is_active": "true"})
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["is_active"] is True

    def test_filter_by_gm_table(self):
        """Filter by gm_table ID returns only records for that table."""
        other_table = GMTableFactory(gm=self.lead_gm_profile)
        other_story = StoryFactory(scope=StoryScope.GROUP)
        GroupStoryProgressFactory(story=other_story, gm_table=other_table)

        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        response = self.client.get(url, {"gm_table": self.gm_table.id})
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["gm_table"] == self.gm_table.id

    # ---------- validation ---------------------------------------------------

    @suppress_permission_errors
    def test_create_rejects_non_group_scope_story(self):
        """Creating with a CHARACTER-scope story returns 400."""
        char_story = StoryFactory(scope=StoryScope.CHARACTER)
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-list")
        data = {
            "story": char_story.id,
            "gm_table": self.gm_table.id,
            "is_active": True,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_serializer_fields_present(self):
        """Serialized response contains all expected fields."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "story",
            "gm_table",
            "current_episode",
            "started_at",
            "last_advanced_at",
            "is_active",
        ]:
            assert field in response.data, f"Missing field: {field}"

    def test_current_episode_can_be_set(self):
        """current_episode can be set to a valid episode."""
        chapter = ChapterFactory(story=self.story)
        episode = EpisodeFactory(chapter=chapter)
        self.client.force_authenticate(user=self.staff)
        url = reverse("groupstoryprogress-detail", kwargs={"pk": self.progress.pk})
        data = {"current_episode": episode.id}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_episode"] == episode.id
