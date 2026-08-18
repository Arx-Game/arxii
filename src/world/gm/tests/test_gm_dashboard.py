"""Tests for GET /api/gm/dashboard/ — the GM dashboard aggregation (#2004, #3268)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMRosterInviteFactory, GMTableFactory
from world.roster.factories import RosterApplicationFactory, RosterEntryFactory
from world.stories.factories import StoryFactory
from world.stories.models import StoryParticipation


class GMDashboardViewTest(APITestCase):
    """GET /api/gm/dashboard/ — IsGM-gated dashboard aggregation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.gm_table = GMTableFactory(gm=cls.gm_profile)
        cls.non_gm_account = AccountFactory()

    def test_gm_can_access_dashboard(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        # All expected sections present.
        for key in [
            "episodes_ready_to_run",
            "pending_agm_claims",
            "assigned_session_requests",
            "waiting_for_gm",
            "open_group_requests",
            "my_tables",
            "pending_story_offers",
            "evidence_summary",
            "pending_applications",
            "open_invites",
        ]:
            self.assertIn(key, data)
        # The GM's table appears in my_tables.
        table_ids = [t["id"] for t in data["my_tables"]]
        self.assertIn(self.gm_table.pk, table_ids)
        # Evidence summary carries the GM's level.
        self.assertEqual(data["evidence_summary"]["level"], self.gm_profile.level)
        # No applications/invites yet.
        self.assertEqual(data["pending_applications"], 0)
        self.assertEqual(data["open_invites"], 0)

    def test_pending_applications_counts_queue_at_own_tables(self) -> None:
        """pending_applications mirrors gm_application_queue(profile).count() (#3268)."""
        entry = RosterEntryFactory()
        story = StoryFactory(primary_table=self.gm_table)
        StoryParticipation.objects.create(
            story=story,
            character=entry.character_sheet,
            is_active=True,
        )
        RosterApplicationFactory(character=entry.character_sheet)

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["pending_applications"], 1)

    def test_open_invites_excludes_claimed_and_expired(self) -> None:
        """open_invites counts only this GM's unclaimed, unexpired invites (#3268)."""
        # Open invite: unclaimed, not yet expired.
        GMRosterInviteFactory(created_by=self.gm_profile)
        # Claimed invite: excluded.
        GMRosterInviteFactory(created_by=self.gm_profile, claimed_at=timezone.now())
        # Expired invite: excluded.
        GMRosterInviteFactory(
            created_by=self.gm_profile,
            expires_at=timezone.now() - timedelta(days=1),
        )
        # Another GM's open invite: excluded.
        other_gm = GMProfileFactory()
        GMRosterInviteFactory(created_by=other_gm)

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["open_invites"], 1)

    def test_non_gm_rejected(self) -> None:
        self.client.force_authenticate(user=self.non_gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_open_group_requests_surfaces_pending_covenant_asks(self) -> None:
        """#2119: any GM sees the broadcast open-request queue, not just their own tables."""
        from world.covenants.factories import CovenantFactory
        from world.stories.factories import GroupStoryRequestFactory

        covenant = CovenantFactory(name="The Watching Circle")
        requester = AccountFactory()
        request = GroupStoryRequestFactory(covenant=covenant, requested_by_account=requester)

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        request_ids = [row["request_id"] for row in resp.data["open_group_requests"]]
        self.assertIn(request.pk, request_ids)
