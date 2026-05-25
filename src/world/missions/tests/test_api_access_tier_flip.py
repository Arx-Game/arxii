"""Phase D D4.1: access-tier flip + is_publishable guard.

Flipping ``access_tier`` from ``STAFF_ONLY`` to ``OPEN`` is the
publish moment. Refused when any attached giver is not publishable
(no target set) — the Studio surfaces those as "needs-work" items.
The reverse flip (OPEN -> STAFF_ONLY) is always allowed (unpublish).
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.missions.constants import AccessTier, GiverKind
from world.missions.factories import MissionGiverFactory, MissionTemplateFactory


class AccessTierFlipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-access-flip", is_staff=True)
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.publishable_giver = MissionGiverFactory(
            slug="ready-giver", giver_kind=GiverKind.ROOM_TRIGGER, target=room
        )
        cls.drafty_giver = MissionGiverFactory(
            slug="drafty-giver", giver_kind=GiverKind.NPC, target=None
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _url(self, template_slug: str) -> str:
        return f"/api/missions/templates/{template_slug}/"

    def test_flip_to_open_succeeds_when_all_givers_publishable(self) -> None:
        template = MissionTemplateFactory(slug="ready-tmpl", access_tier=AccessTier.STAFF_ONLY)
        self.publishable_giver.templates.add(template)
        response = self.client.patch(
            self._url(template.slug),
            {"access_tier": AccessTier.OPEN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["access_tier"], AccessTier.OPEN)

    def test_flip_to_open_refused_when_any_giver_drafty(self) -> None:
        template = MissionTemplateFactory(slug="drafty-tmpl", access_tier=AccessTier.STAFF_ONLY)
        # Mix: one publishable + one drafty. Drafty should block.
        self.publishable_giver.templates.add(template)
        self.drafty_giver.templates.add(template)
        response = self.client.patch(
            self._url(template.slug),
            {"access_tier": AccessTier.OPEN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The error message names the drafty giver's slug so the Studio
        # can surface "needs-work" callouts.
        self.assertIn("drafty-giver", str(response.data))

    def test_flip_to_open_with_no_givers_passes(self) -> None:
        # No givers attached → vacuously publishable. (Won't actually be
        # offered to players, but the tier flip itself is permitted.)
        template = MissionTemplateFactory(slug="no-givers-tmpl", access_tier=AccessTier.STAFF_ONLY)
        response = self.client.patch(
            self._url(template.slug),
            {"access_tier": AccessTier.OPEN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_flip_to_staff_only_always_allowed(self) -> None:
        # Unpublish path: no guard. Even a drafty giver doesn't block
        # going back to STAFF_ONLY.
        template = MissionTemplateFactory(slug="unpublish-tmpl", access_tier=AccessTier.OPEN)
        self.drafty_giver.templates.add(template)
        response = self.client.patch(
            self._url(template.slug),
            {"access_tier": AccessTier.STAFF_ONLY},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["access_tier"], AccessTier.STAFF_ONLY)
