"""
Tests for get_projected_resonances service function and API endpoint.

Verifies that projected resonance totals are correctly calculated from
draft distinction data, including rank scaling, multi-source aggregation,
and filtering of non-resonance effects.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import get_projected_resonances
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.magic.factories import ResonanceModifierTypeFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory


class GetProjectedResonancesTest(TestCase):
    """Tests for the get_projected_resonances service function."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data for all tests in this class."""
        cls.resonance_category = ModifierCategoryFactory(
            name="resonance", description="Magical resonances"
        )
        cls.stat_category = ModifierCategoryFactory(name="stat", description="Character stats")

    def test_empty_distinctions_returns_empty_list(self):
        """Draft with no distinctions in draft_data returns empty list."""
        draft = CharacterDraftFactory(draft_data={"distinctions": []})
        result = get_projected_resonances(draft)
        self.assertEqual(result, [])

    def test_missing_distinctions_key_returns_empty_list(self):
        """Draft with no 'distinctions' key in draft_data returns empty list."""
        draft = CharacterDraftFactory(draft_data={})
        result = get_projected_resonances(draft)
        self.assertEqual(result, [])

    def test_single_distinction_with_resonance_effect(self):
        """Single distinction with one resonance effect returns correct projection."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction = DistinctionFactory(name="Patient")
        DistinctionEffectFactory(
            distinction=distinction,
            target=resonance,
            value_per_rank=10,
        )

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 1}]}
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["resonance_id"], resonance.id)
        self.assertEqual(result[0]["resonance_name"], "Sereni")
        self.assertEqual(result[0]["total"], 10)
        self.assertEqual(len(result[0]["sources"]), 1)
        self.assertEqual(result[0]["sources"][0]["distinction_name"], "Patient")
        self.assertEqual(result[0]["sources"][0]["value"], 10)

    def test_multiple_distinctions_different_resonances(self):
        """Multiple distinctions targeting different resonances produce separate entries."""
        resonance_a = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        resonance_b = ResonanceModifierTypeFactory(
            name="Tempesti", category=self.resonance_category
        )
        distinction_a = DistinctionFactory(name="Patient")
        distinction_b = DistinctionFactory(name="Fierce")
        DistinctionEffectFactory(distinction=distinction_a, target=resonance_a, value_per_rank=10)
        DistinctionEffectFactory(distinction=distinction_b, target=resonance_b, value_per_rank=5)

        draft = CharacterDraftFactory(
            draft_data={
                "distinctions": [
                    {"distinction_id": distinction_a.id, "rank": 1},
                    {"distinction_id": distinction_b.id, "rank": 1},
                ]
            }
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 2)
        result_by_name = {r["resonance_name"]: r for r in result}
        self.assertIn("Sereni", result_by_name)
        self.assertIn("Tempesti", result_by_name)
        self.assertEqual(result_by_name["Sereni"]["total"], 10)
        self.assertEqual(result_by_name["Tempesti"]["total"], 5)

    def test_rank_two_multiplies_value(self):
        """Rank 2 with linear scaling produces value_per_rank * 2."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction = DistinctionFactory(name="Very Patient", max_rank=3)
        DistinctionEffectFactory(
            distinction=distinction,
            target=resonance,
            value_per_rank=10,
        )

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 2}]}
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["total"], 20)
        self.assertEqual(result[0]["sources"][0]["value"], 20)

    def test_multiple_distinctions_same_resonance_sums(self):
        """Multiple distinctions targeting the same resonance aggregate correctly."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction_a = DistinctionFactory(name="Patient")
        distinction_b = DistinctionFactory(name="Calm")
        DistinctionEffectFactory(distinction=distinction_a, target=resonance, value_per_rank=10)
        DistinctionEffectFactory(distinction=distinction_b, target=resonance, value_per_rank=5)

        draft = CharacterDraftFactory(
            draft_data={
                "distinctions": [
                    {"distinction_id": distinction_a.id, "rank": 1},
                    {"distinction_id": distinction_b.id, "rank": 1},
                ]
            }
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["resonance_name"], "Sereni")
        self.assertEqual(result[0]["total"], 15)
        self.assertEqual(len(result[0]["sources"]), 2)

        source_names = {s["distinction_name"] for s in result[0]["sources"]}
        self.assertEqual(source_names, {"Patient", "Calm"})

    def test_non_resonance_effects_excluded(self):
        """Effects targeting non-resonance categories (e.g. stat) are excluded."""
        stat_type = ModifierTypeFactory(name="strength", category=self.stat_category)
        distinction = DistinctionFactory(name="Strong")
        DistinctionEffectFactory(distinction=distinction, target=stat_type, value_per_rank=10)

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 1}]}
        )

        result = get_projected_resonances(draft)
        self.assertEqual(result, [])

    def test_invalid_distinction_id_skipped(self):
        """A distinction_id that doesn't exist in the database is silently skipped."""
        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": 99999, "rank": 1}]}
        )

        result = get_projected_resonances(draft)
        self.assertEqual(result, [])

    def test_mixed_resonance_and_non_resonance_effects(self):
        """Distinction with both resonance and non-resonance effects only includes resonance."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        stat_type = ModifierTypeFactory(name="charm", category=self.stat_category)
        distinction = DistinctionFactory(name="Charming Patience")
        DistinctionEffectFactory(distinction=distinction, target=resonance, value_per_rank=10)
        DistinctionEffectFactory(distinction=distinction, target=stat_type, value_per_rank=5)

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 1}]}
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["resonance_name"], "Sereni")
        self.assertEqual(result[0]["total"], 10)

    def test_scaling_values_used_over_value_per_rank(self):
        """Non-linear scaling_values take precedence over value_per_rank."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction = DistinctionFactory(name="Escalating", max_rank=3)
        DistinctionEffectFactory(
            distinction=distinction,
            target=resonance,
            value_per_rank=10,
            scaling_values=[5, 15, 30],
        )

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 2}]}
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        # scaling_values[1] = 15, not value_per_rank * 2 = 20
        self.assertEqual(result[0]["total"], 15)

    def test_default_rank_is_one_when_missing(self):
        """If rank is missing from distinction entry, defaults to 1."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction = DistinctionFactory(name="Patient")
        DistinctionEffectFactory(
            distinction=distinction,
            target=resonance,
            value_per_rank=10,
        )

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id}]}
        )

        result = get_projected_resonances(draft)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["total"], 10)


class ProjectedResonancesAPITest(TestCase):
    """Tests for the projected-resonances API endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.resonance_category = ModifierCategoryFactory(
            name="resonance", description="Magical resonances"
        )

    def setUp(self):
        self.client = APIClient()

    def _url(self, draft_id):
        return f"/api/character-creation/drafts/{draft_id}/projected-resonances/"

    def test_returns_projected_resonances_for_draft(self):
        """Endpoint returns projected resonances for a draft with distinctions."""
        resonance = ResonanceModifierTypeFactory(name="Sereni", category=self.resonance_category)
        distinction = DistinctionFactory(name="Patient")
        DistinctionEffectFactory(
            distinction=distinction,
            target=resonance,
            value_per_rank=10,
        )
        draft = CharacterDraftFactory(
            account=self.account,
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 1}]},
        )

        self.client.force_login(self.account)
        response = self.client.get(self._url(draft.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["resonance_name"], "Sereni")
        self.assertEqual(response.data[0]["total"], 10)

    def test_requires_authentication(self):
        """Endpoint returns 403 when user is not logged in."""
        draft = CharacterDraftFactory(account=self.account)

        response = self.client.get(self._url(draft.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_list_when_no_distinctions(self):
        """Endpoint returns empty list when draft has no distinctions."""
        draft = CharacterDraftFactory(
            account=self.account,
            draft_data={"distinctions": []},
        )

        self.client.force_login(self.account)
        response = self.client.get(self._url(draft.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
