"""Phase D D1.1-D1.2: MissionTemplateViewSet list + filters.

Staff-only browse endpoint for the mission authoring tool. Tests cover
permission gating, basic round-trip, filtering by name/risk/status/
category/org, and stable pagination ordering.

Detail/§5-footprint coverage lives in test_api_template_detail.py
(D1.3); editor CRUD coverage lives in test_api_editor_* (D2); giver
library lives in test_api_giver_*  (D3).
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.constants import ArcScope
from world.missions.factories import (
    MissionCategoryFactory,
    MissionGiverFactory,
    MissionTemplateFactory,
)
from world.societies.factories import OrganizationFactory

LIST_URL = "/api/missions/templates/"


class TemplateListPermissionTests(TestCase):
    """The endpoint is staff-only."""

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.get(LIST_URL)
        # DRF returns 401 for unauthenticated when IsAuthenticated kicks
        # in (the default for the API), and 403 for non-staff.
        self.assertIn(
            response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
        )

    def test_player_denied(self) -> None:
        account = AccountFactory(is_staff=False)
        client = APIClient()
        client.force_authenticate(account)
        response = client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_allowed(self) -> None:
        staff = AccountFactory(is_staff=True)
        client = APIClient()
        client.force_authenticate(staff)
        response = client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TemplateListRoundTripTests(TestCase):
    """List returns paginated MissionTemplate rows in a deterministic order."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-list-rt", is_staff=True)
        cls.t_a = MissionTemplateFactory(name="Alpha", slug="alpha", risk_tier=1)
        cls.t_b = MissionTemplateFactory(name="Bravo", slug="bravo", risk_tier=3)
        cls.t_c = MissionTemplateFactory(name="Charlie", slug="charlie", risk_tier=5)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_returns_all_active_templates(self) -> None:
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        slugs = {r["slug"] for r in results}
        self.assertEqual(slugs, {"alpha", "bravo", "charlie"})

    def test_list_is_paginated(self) -> None:
        # Pagination shape: response.data has count/next/previous/results.
        response = self.client.get(LIST_URL)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    def test_list_is_ordered_deterministically(self) -> None:
        # Two calls return the same order (cursor- or PK-stable).
        first = self.client.get(LIST_URL).data["results"]
        second = self.client.get(LIST_URL).data["results"]
        self.assertEqual(
            [r["slug"] for r in first],
            [r["slug"] for r in second],
        )


class TemplateListFilterTests(TestCase):
    """FilterSet covers name search, risk, status, category, org."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-list-flt", is_staff=True)
        cls.cat_courtly = MissionCategoryFactory(name="courtly")
        cls.cat_heist = MissionCategoryFactory(name="heist")
        cls.org = OrganizationFactory(name="Crime Guild")
        cls.org_giver = MissionGiverFactory(name="org-giver", slug="org-giver", org=cls.org)

        cls.low_risk = MissionTemplateFactory(
            name="Low Risk", slug="low-risk", risk_tier=1, is_active=True
        )
        cls.low_risk.categories.add(cls.cat_courtly)

        cls.high_risk = MissionTemplateFactory(
            name="High Risk", slug="high-risk", risk_tier=5, is_active=True
        )
        cls.high_risk.categories.add(cls.cat_heist)
        cls.org_giver.templates.add(cls.high_risk)

        cls.inactive = MissionTemplateFactory(
            name="Inactive", slug="inactive", risk_tier=2, is_active=False
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _slugs(self, response) -> set[str]:
        return {r["slug"] for r in response.data["results"]}

    def test_filter_by_name_substring(self) -> None:
        response = self.client.get(LIST_URL, {"name": "Risk"})
        self.assertEqual(self._slugs(response), {"low-risk", "high-risk"})

    def test_filter_by_risk_tier_exact(self) -> None:
        response = self.client.get(LIST_URL, {"risk_tier": 5})
        self.assertEqual(self._slugs(response), {"high-risk"})

    def test_filter_by_is_active(self) -> None:
        response = self.client.get(LIST_URL, {"is_active": False})
        self.assertEqual(self._slugs(response), {"inactive"})

    def test_filter_by_category_name(self) -> None:
        response = self.client.get(LIST_URL, {"category": "heist"})
        self.assertEqual(self._slugs(response), {"high-risk"})

    def test_filter_by_org_name(self) -> None:
        # Templates available via any giver fronting for this org.
        response = self.client.get(LIST_URL, {"org": "Crime Guild"})
        self.assertEqual(self._slugs(response), {"high-risk"})

    def test_filter_by_arc_scope(self) -> None:
        cls = type(self)
        cls.high_risk.arc_scope = ArcScope.ORG
        cls.high_risk.save()
        response = self.client.get(LIST_URL, {"arc_scope": "org"})
        self.assertEqual(self._slugs(response), {"high-risk"})
