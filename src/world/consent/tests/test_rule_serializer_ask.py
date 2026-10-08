"""``ask`` is offered only by a category that asks before acting (#4187)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory, SocialConsentPreferenceFactory
from world.consent.tests.test_api import _force_api_user
from world.roster.factories import PlayerDataFactory, RosterTenureFactory


class AskModeRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = PlayerDataFactory()
        cls.tenure = RosterTenureFactory(player_data=cls.player)
        cls.pref = SocialConsentPreferenceFactory(tenure=cls.tenure)
        cls.hostile = SocialConsentCategoryFactory(key="hostile", name="Hostile")
        cls.makeover = SocialConsentCategoryFactory(
            key="makeover",
            name="Makeovers & Styling",
            default_mode=ConsentMode.ASK,
            asks_before_acting=True,
        )

    def setUp(self):
        self.client = APIClient()
        _force_api_user(
            self.client, self.player, self.tenure.roster_entry.character_sheet.character
        )

    def post_rule(self, category, mode):
        return self.client.post(
            "/api/consent/category-rules/",
            {"preference": self.pref.pk, "category": category.pk, "mode": mode},
            format="json",
        )

    def test_ask_is_rejected_on_a_category_that_does_not_ask(self):
        response = self.post_rule(self.hostile, ConsentMode.ASK)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mode", response.data)

    def test_ask_is_accepted_on_an_asking_category(self):
        response = self.post_rule(self.makeover, ConsentMode.ASK)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_category_list_carries_the_flag(self):
        response = self.client.get("/api/consent/categories/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        by_key = {row["key"]: row for row in rows}
        self.assertTrue(by_key["makeover"]["asks_before_acting"])
        self.assertFalse(by_key["hostile"]["asks_before_acting"])
