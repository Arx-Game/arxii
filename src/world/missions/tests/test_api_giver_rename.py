"""PATCH rename tests for MissionGiver.

MissionGiverSerializer.validate_name has the same collision/free/own-name
logic as MissionTemplateSerializer.validate_name but had zero tests.
These three tests mirror the MissionTemplatePatchRenameTests in
test_api_template_create.py.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.factories import MissionGiverFactory


class MissionGiverPatchRenameTests(TestCase):
    """PATCH /api/missions/givers/<pk>/ rename collision behavior.

    Create-path auto-suffixes; PATCH path must error explicitly so the
    author sees their choice was rejected (same rule as templates).

    Uses setUp (per-test fixture) rather than setUpTestData to avoid
    SharedMemoryModel identity-map staleness: successful PATCHes mutate
    the Python object in the identity map, and even though Django's
    savepoint rolls back the DB after each test, the identity map retains
    stale field values that would corrupt validate_name's exclude-self lookup.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-giver-rename", is_staff=True, is_superuser=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)
        # Create fresh per-test to avoid SharedMemoryModel identity-map
        # staleness from successful PATCHes in earlier tests.
        self.giver_a = MissionGiverFactory(name="giver-a-patch")
        self.giver_b = MissionGiverFactory(name="giver-b-patch")

    def test_patch_rename_to_taken_name_returns_400(self) -> None:
        res = self.client.patch(
            f"/api/missions/givers/{self.giver_a.pk}/",
            {"name": "giver-b-patch"},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("name", res.json())

    def test_patch_rename_to_free_name_succeeds(self) -> None:
        res = self.client.patch(
            f"/api/missions/givers/{self.giver_a.pk}/",
            {"name": "giver-c-patch"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["name"], "giver-c-patch")

    def test_patch_rename_to_own_name_succeeds(self) -> None:
        """Patching to the SAME current name is a no-op rename — must NOT 400."""
        res = self.client.patch(
            f"/api/missions/givers/{self.giver_a.pk}/",
            {"name": "giver-a-patch"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
