"""
Integration tests to validate fixture data integrity.

These tests load the actual fixture files and verify that all
cross-references between models are valid.
"""

from django.test import TestCase

from world.distinctions.models import Distinction, DistinctionCategory, DistinctionEffect
from world.mechanics.models import ModifierCategory, ModifierType


class FixtureIntegrityTests(TestCase):
    """Tests that validate fixture data loads correctly and has valid references."""

    fixtures = [
        "world/mechanics/fixtures/initial_modifier_categories.json",
        "world/mechanics/fixtures/initial_modifier_types.json",
        "world/distinctions/fixtures/initial_categories.json",
        "world/distinctions/fixtures/initial_personality_distinctions.json",
        "world/distinctions/fixtures/physical_distinctions.json",
        "world/distinctions/fixtures/ap_distinctions.json",
        "world/distinctions/fixtures/magical_scar_distinctions.json",
    ]

    def test_fixtures_load_successfully(self):
        """Verify all fixtures load without error."""
        # If we get here, fixtures loaded successfully
        self.assertGreater(ModifierCategory.objects.count(), 0)
        self.assertGreater(ModifierType.objects.count(), 0)
        self.assertGreater(DistinctionCategory.objects.count(), 0)
        self.assertGreater(Distinction.objects.count(), 0)

    def test_all_distinction_effects_have_valid_targets(self):
        """Every DistinctionEffect must reference an existing ModifierType."""
        effects = DistinctionEffect.objects.select_related("target", "distinction")

        for effect in effects:
            self.assertIsNotNone(
                effect.target,
                f"DistinctionEffect for '{effect.distinction.name}' has no target",
            )
            self.assertTrue(
                ModifierType.objects.filter(pk=effect.target_id).exists(),
                f"DistinctionEffect for '{effect.distinction.name}' targets non-existent "
                f"ModifierType: {effect.target_id}",
            )

    def test_resonance_effects_target_resonance_category(self):
        """Effects targeting resonances must point to resonance-category ModifierTypes."""
        effects = DistinctionEffect.objects.select_related(
            "target", "target__category", "distinction"
        ).filter(target__category__name="resonance")

        for effect in effects:
            self.assertEqual(
                effect.target.category.name,
                "resonance",
                f"Effect for '{effect.distinction.name}' targets '{effect.target.name}' "
                f"which is category '{effect.target.category.name}', not 'resonance'",
            )

    def test_stat_effects_target_stat_category(self):
        """Effects targeting stats must point to stat-category ModifierTypes."""
        effects = DistinctionEffect.objects.select_related(
            "target", "target__category", "distinction"
        ).filter(target__category__name="stat")

        for effect in effects:
            self.assertEqual(
                effect.target.category.name,
                "stat",
                f"Effect for '{effect.distinction.name}' targets '{effect.target.name}' "
                f"which is category '{effect.target.category.name}', not 'stat'",
            )

    def test_all_distinctions_have_valid_category(self):
        """Every Distinction must reference an existing DistinctionCategory."""
        distinctions = Distinction.objects.select_related("category")

        for distinction in distinctions:
            self.assertIsNotNone(
                distinction.category,
                f"Distinction '{distinction.name}' has no category",
            )
            self.assertTrue(
                DistinctionCategory.objects.filter(pk=distinction.category_id).exists(),
                f"Distinction '{distinction.name}' references non-existent category",
            )

    def test_expected_latin_resonances_exist(self):
        """Verify all 24 Latin resonances are loaded."""
        expected_resonances = [
            # Celestial
            "Bene",
            "Liberare",
            "Fidelis",
            "Misera",
            "Fortis",
            "Honoris",
            "Verax",
            "Copperi",
            # Abyssal
            "Praedari",
            "Dominari",
            "Perfidus",
            "Maligna",
            "Tremora",
            "Saevus",
            "Insidia",
            "Despari",
            # Primal
            "Firma",
            "Vola",
            "Audax",
            "Medita",
            "Arderi",
            "Sereni",
            "Fera",
            "Civitas",
        ]

        resonance_category = ModifierCategory.objects.get(name="resonance")
        actual_resonances = set(
            ModifierType.objects.filter(category=resonance_category).values_list("name", flat=True)
        )

        for expected in expected_resonances:
            self.assertIn(
                expected,
                actual_resonances,
                f"Expected Latin resonance '{expected}' not found in fixtures",
            )

    def test_expected_stats_exist(self):
        """Verify all 9 stats are loaded with correct names."""
        expected_stats = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]

        stat_category = ModifierCategory.objects.get(name="stat")
        actual_stats = set(
            ModifierType.objects.filter(category=stat_category).values_list("name", flat=True)
        )

        for expected in expected_stats:
            self.assertIn(
                expected,
                actual_stats,
                f"Expected stat '{expected}' not found in fixtures",
            )

    def test_no_old_resonances_remain(self):
        """Verify old English resonances have been removed."""
        old_resonances = [
            "Allure",
            "Beast",
            "Bonds",
            "Command",
            "Cunning",
            "Death",
            "Decay",
            "Dreams",
            "Fate",
            "Fear",
            "Flame",
            "Fury",
            "Grace",
            "Growth",
            "Ice",
            "Life",
            "Majesty",
            "Mind",
            "Presence",
            "Protection",
            "Radiance",
            "Shadows",
            "Space",
            "Spirit",
            "Steel",
            "Stone",
            "Storm",
            "Time",
            "Vengeance",
            "Water",
            "Predatory",
            "Ferocious",
            "Proud",
            "Audacious",
            "Angry",
            "Serene",
            "Courageous",
            "Humble",
        ]

        resonance_category = ModifierCategory.objects.get(name="resonance")
        actual_resonances = set(
            ModifierType.objects.filter(category=resonance_category).values_list("name", flat=True)
        )

        for old in old_resonances:
            self.assertNotIn(
                old,
                actual_resonances,
                f"Old resonance '{old}' should have been removed from fixtures",
            )
