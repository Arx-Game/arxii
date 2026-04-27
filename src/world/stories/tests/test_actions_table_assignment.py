"""Tests for Wave 2 table assignment action endpoints on StoryViewSet.

Covers:
  - POST /api/stories/{id}/assign-to-table/
  - POST /api/stories/{id}/detach-from-table/
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
)
from world.stories.constants import StoryScope
from world.stories.factories import StoryFactory


def _character_with_account(account):
    """Return a CharacterSheet whose character.db_account == account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class AssignToTableActionTest(APITestCase):
    """POST /api/stories/{id}/assign-to-table/."""

    @classmethod
    def setUpTestData(cls):
        # Lead GM who will receive the story
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # A different GM who owns a different table
        cls.other_gm_account = AccountFactory()
        cls.other_gm_profile = GMProfileFactory(account=cls.other_gm_account)
        cls.other_table = GMTableFactory(gm=cls.other_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.random_account = AccountFactory()

        # A CHARACTER-scope story with no primary table (orphaned / seeking GM)
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            primary_table=None,
        )

    def _url(self):
        return reverse("story-assign-to-table", args=[self.story.pk])

    def test_lead_gm_assigns_story_to_own_table_returns_200(self):
        """Lead GM of the destination table can assign the story."""
        self.client.force_authenticate(user=self.lead_gm_account)
        resp = self.client.post(self._url(), {"table": self.gm_table.pk}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] == self.gm_table.pk
        # Refresh from DB to confirm persistence
        self.story.refresh_from_db()
        assert self.story.primary_table_id == self.gm_table.pk

    @suppress_permission_errors
    def test_non_gm_cannot_assign_returns_400(self):
        """A user with no GMProfile gets a 400 from serializer validation."""
        self.client.force_authenticate(user=self.random_account)
        resp = self.client.post(self._url(), {"table": self.gm_table.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_gm_cannot_assign_to_another_gm_table_returns_400(self):
        """A GM can only assign to their own table; assigning to other GM's table is rejected."""
        self.client.force_authenticate(user=self.lead_gm_account)
        resp = self.client.post(self._url(), {"table": self.other_table.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_staff_can_assign_story_to_any_table(self):
        """Staff may assign a story to any table."""
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.post(self._url(), {"table": self.other_table.pk}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] == self.other_table.pk

    @suppress_permission_errors
    def test_archived_table_rejected(self):
        """An ARCHIVED table cannot receive stories."""
        archived = GMTableFactory(gm=self.lead_gm_profile, status=GMTableStatus.ARCHIVED)
        self.client.force_authenticate(user=self.lead_gm_account)
        resp = self.client.post(self._url(), {"table": archived.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_unauthenticated_returns_403(self):
        """Unauthenticated requests are rejected."""
        resp = self.client.post(self._url(), {"table": self.gm_table.pk}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class DetachFromTableActionTest(APITestCase):
    """POST /api/stories/{id}/detach-from-table/.

    Tests use setUp (not setUpTestData) to reset the story's primary_table
    before each test, avoiding SharedMemoryModel in-memory state bleed.
    """

    @classmethod
    def setUpTestData(cls):
        # Lead GM who owns the table overseeing the story
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # Player who owns the CHARACTER-scope story (via character sheet)
        cls.owner_account = AccountFactory()
        cls.owner_sheet = _character_with_account(cls.owner_account)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.random_account = AccountFactory()

    def setUp(self):
        """Create a fresh story per-test with primary_table set to cls.gm_table."""
        super().setUp()
        self.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=self.owner_sheet,
            primary_table=self.gm_table,
        )

    def _url(self):
        return reverse("story-detach-from-table", args=[self.story.pk])

    def test_lead_gm_of_table_can_detach(self):
        """Lead GM of the story's primary_table can detach."""
        self.client.force_authenticate(user=self.lead_gm_account)
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] is None
        self.story.refresh_from_db()
        assert self.story.primary_table_id is None

    def test_character_owner_can_detach_own_story(self):
        """The player whose character owns the story can detach it."""
        self.client.force_authenticate(user=self.owner_account)
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] is None

    def test_staff_can_detach(self):
        """Staff may detach any story."""
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] is None

    @suppress_permission_errors
    def test_random_user_cannot_detach_returns_403(self):
        """A user with no relationship to the story is rejected."""
        self.client.force_authenticate(user=self.random_account)
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_detach_when_no_primary_table_is_idempotent(self):
        """Detaching a story that already has no primary_table succeeds with no error."""
        self.story.primary_table = None
        self.story.save(update_fields=["primary_table"])
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_table"] is None

    @suppress_permission_errors
    def test_unauthenticated_returns_403(self):
        """Unauthenticated requests are rejected."""
        resp = self.client.post(self._url())
        assert resp.status_code == status.HTTP_403_FORBIDDEN
