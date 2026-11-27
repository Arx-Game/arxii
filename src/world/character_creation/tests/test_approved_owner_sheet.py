"""A newly approved player reads their own sheet as its owner, in the process that approved it.

Approval reads the new roster entry's tenures before it writes the player's tenure; the
roster entry is identity-mapped, so a tenure list kept on it would make the owner a
stranger on their own sheet until the process restarted (#5206).
"""

from __future__ import annotations

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.services import submit_draft_for_review
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.models import RosterEntry


class ApprovedOwnerReadsOwnSheetTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="newly_approved")
        self.staff = AccountDB.objects.create(username="approving_staff", is_staff=True)
        self._setup_finalization_base(self, prefix="Approved", height_min=700, height_max=800)
        self.draft = self._create_base_draft(first_name="Ione")

    def test_the_owner_reads_the_owners_sheet_right_after_approval(self) -> None:
        application = submit_draft_for_review(self.draft)
        staff = APIClient()
        staff.force_authenticate(user=self.staff)
        base = f"/api/character-creation/applications/{application.pk}"
        self.assertEqual(staff.post(f"{base}/claim/").status_code, 200)
        approved = staff.post(f"{base}/approve/")
        self.assertEqual(approved.status_code, 200, approved.content)
        entry = RosterEntry.objects.get(tenures__player_data__account=self.account)

        owner = APIClient()
        owner.force_authenticate(user=self.account)
        response = owner.get(f"/api/character-sheets/{entry.character_sheet_id}/")

        self.assertEqual(response.status_code, 200, response.content)
        identity = response.data["identity"]
        # Owner-only fields: a stranger reads None in both.
        self.assertEqual(identity["biological_age"], 25)
        self.assertEqual(identity["withered_years"], 0)
