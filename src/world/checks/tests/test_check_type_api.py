"""Tests for the CheckType catalog read API (#3070).

Covers the GM-only permission gate, active/owner_sheet scoping, and the
``search``/``category`` filters -- the web sibling of telnet's
``gm check find``, feeding the GM adjudication panel's Call Check picker.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckType
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.traits.constants import TraitCategory, TraitType
from world.traits.factories import TraitFactory


class CheckTypeAPISetupMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = CheckCategoryFactory(name="AdjudicationCombat")
        cls.check_type = CheckTypeFactory(
            name="Power Strike",
            category=cls.category,
            description="A heavy blow",
        )
        cls.trait = TraitFactory(
            name="adj_api_strength", trait_type=TraitType.STAT, category=TraitCategory.PHYSICAL
        )
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.trait, weight=Decimal("1.0"))
        cls.inactive_check_type = CheckTypeFactory(
            name="Retired Check", category=cls.category, is_active=False
        )

        cls.owner_char = CharacterFactory()
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_char)
        cls.synthesized_check_type = CheckTypeFactory(
            name="Signature Magic Check", category=cls.category, owner_sheet=cls.owner_sheet
        )

        cls.gm_account = AccountFactory()
        GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()


class CheckTypeAPIPermissionTests(CheckTypeAPISetupMixin, TestCase):
    def test_anonymous_is_refused(self) -> None:
        client = APIClient()
        response = client.get("/api/checks/check-types/")
        self.assertEqual(response.status_code, 403)

    def test_non_gm_player_is_refused(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.get("/api/checks/check-types/")
        self.assertEqual(response.status_code, 403)

    def test_gm_may_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get("/api/checks/check-types/")
        self.assertEqual(response.status_code, 200)

    def test_staff_may_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get("/api/checks/check-types/")
        self.assertEqual(response.status_code, 200)


class CheckTypeAPIListTests(CheckTypeAPISetupMixin, TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.gm_account)

    def test_active_check_type_is_listed(self) -> None:
        response = self.client.get("/api/checks/check-types/")
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.check_type.name, names)

    def test_inactive_check_type_is_excluded(self) -> None:
        response = self.client.get("/api/checks/check-types/")
        names = [row["name"] for row in response.json()["results"]]
        self.assertNotIn(self.inactive_check_type.name, names)

    def test_synthesized_owner_sheet_check_type_is_excluded(self) -> None:
        """A per-character synthesized magic check never appears in the general
        catalog browse (#2724 export-filter rationale, mirrored here)."""
        response = self.client.get("/api/checks/check-types/")
        names = [row["name"] for row in response.json()["results"]]
        self.assertNotIn(self.synthesized_check_type.name, names)

    def test_trait_summary_lists_weighted_traits(self) -> None:
        response = self.client.get("/api/checks/check-types/")
        row = next(r for r in response.json()["results"] if r["name"] == self.check_type.name)
        self.assertIn(self.trait.name, row["trait_summary"])

    def test_search_by_name_matches(self) -> None:
        response = self.client.get("/api/checks/check-types/", {"search": "Power"})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.check_type.name, names)

    def test_search_by_trait_name_matches(self) -> None:
        response = self.client.get("/api/checks/check-types/", {"search": self.trait.name})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(self.check_type.name, names)

    def test_search_with_no_matches_returns_empty(self) -> None:
        response = self.client.get("/api/checks/check-types/", {"search": "zzz_no_such_check"})
        self.assertEqual(response.json()["results"], [])

    def test_category_filter(self) -> None:
        other_category = CheckCategoryFactory(name="AdjudicationOther")
        other_check_type = CheckTypeFactory(name="Other Check", category=other_category)
        response = self.client.get("/api/checks/check-types/", {"category": other_category.name})
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn(other_check_type.name, names)
        self.assertNotIn(self.check_type.name, names)


class CheckTypeAPIQuerysetSanityTests(CheckTypeAPISetupMixin, TestCase):
    def test_queryset_excludes_synthesized_at_model_level(self) -> None:
        """Belt-and-suspenders: the ViewSet's own queryset (not just the API
        response) never includes an owner_sheet row."""
        from world.checks.views import CheckTypeViewSet

        qs = CheckTypeViewSet.queryset
        self.assertFalse(qs.filter(pk=self.synthesized_check_type.pk).exists())
        self.assertTrue(CheckType.objects.filter(pk=self.synthesized_check_type.pk).exists())
