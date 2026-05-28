"""Tests for MissionTemplateViewSet.create (POST /api/missions/templates/).

Covers required-field validation, level-band validation via clean(),
category PK acceptance, default field handling, and the name-collision
auto-suffix behavior.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.missions.constants import AccessTier, ArcScope, RewardGroupRule
from world.missions.factories import MissionCategoryFactory, MissionTemplateFactory
from world.missions.models import MissionTemplate

URL = "/api/missions/templates/"


class MissionTemplateCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-create-tc", is_staff=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def _valid_body(self, **overrides) -> dict:
        body = {
            "name": "Heist the Castle",
            "summary": "An IC opening.",
            "level_band_min": 1,
            "level_band_max": 5,
            "risk_tier": 2,
            "arc_scope": ArcScope.GLOBAL.value,
            "cooldown": "P1D",
        }
        body.update(overrides)
        return body

    def test_creates_with_required_fields(self) -> None:
        res = self.client.post(URL, self._valid_body(), format="json")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["name"], "Heist the Castle")
        self.assertIn("id", body)
        # Defaults verified.
        self.assertEqual(body["access_tier"], AccessTier.STAFF_ONLY.value)
        self.assertEqual(body["base_weight"], 1)
        self.assertTrue(body["is_active"])
        self.assertEqual(body["reward_group_rule"], RewardGroupRule.ALL_EQUAL.value)
        self.assertEqual(body["categories"], [])
        self.assertEqual(MissionTemplate.objects.count(), 1)

    def test_rejects_missing_required_field(self) -> None:
        body = self._valid_body()
        del body["summary"]
        res = self.client.post(URL, body, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("summary", res.json())

    def test_rejects_inverted_level_band(self) -> None:
        res = self.client.post(
            URL, self._valid_body(level_band_min=10, level_band_max=5), format="json"
        )
        self.assertEqual(res.status_code, 400)
        # clean() raises on level_band_min — surfaces under that key.
        self.assertIn("level_band_min", res.json())

    def test_accepts_category_pks(self) -> None:
        cat_a = MissionCategoryFactory(name="courtly-tc")
        cat_b = MissionCategoryFactory(name="heist-tc")
        res = self.client.post(
            URL, self._valid_body(categories=[cat_a.pk, cat_b.pk]), format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(sorted(res.json()["categories"]), sorted([cat_a.pk, cat_b.pk]))

    def test_rejects_nonexistent_category(self) -> None:
        res = self.client.post(URL, self._valid_body(categories=[999_999]), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("categories", res.json())

    def test_auto_suffixes_on_name_collision(self) -> None:
        MissionTemplateFactory(name="Heist")
        res = self.client.post(URL, self._valid_body(name="Heist"), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["name"], "Heist 2")

    def test_auto_suffixes_to_three_when_two_exist(self) -> None:
        MissionTemplateFactory(name="Heist")
        MissionTemplateFactory(name="Heist 2")
        res = self.client.post(URL, self._valid_body(name="Heist"), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["name"], "Heist 3")

    def test_non_staff_forbidden(self) -> None:
        non_staff = AccountFactory(username="player-create-tc", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=non_staff)
        res = client.post(URL, self._valid_body(), format="json")
        self.assertEqual(res.status_code, 403)
