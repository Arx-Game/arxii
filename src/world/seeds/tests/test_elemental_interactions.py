"""Tests for the elemental interaction seed content (#2018)."""

from __future__ import annotations

from django.test import TestCase

from world.conditions.models import (
    ConditionDamageInteraction,
    ConditionTemplate,
    DamageType,
)
from world.seeds.game_content.elemental_interactions import seed_elemental_interactions


class ElementalInteractionsSeedTests(TestCase):
    """Tests that the elemental interaction seed is idempotent and complete."""

    def test_seeds_damage_types(self) -> None:
        """Six canonical damage types are seeded."""
        seed_elemental_interactions()
        for name in ["Fire", "Cold", "Lightning", "Force", "Acid", "Poison"]:
            self.assertTrue(
                DamageType.objects.filter(name=name).exists(),
                f"DamageType '{name}' not seeded",
            )

    def test_seeds_condition_templates(self) -> None:
        """Four elemental condition templates are seeded."""
        seed_elemental_interactions()
        for name in ["Wet", "Burning", "Frozen", "Soaked"]:
            self.assertTrue(
                ConditionTemplate.objects.filter(name=name).exists(),
                f"ConditionTemplate '{name}' not seeded",
            )

    def test_seeds_interaction_matrix(self) -> None:
        """Six ConditionDamageInteraction rows are seeded."""
        seed_elemental_interactions()
        self.assertGreaterEqual(ConditionDamageInteraction.objects.count(), 6)

    def test_idempotent(self) -> None:
        """Running twice does not duplicate rows."""
        seed_elemental_interactions()
        count = ConditionDamageInteraction.objects.count()
        seed_elemental_interactions()
        self.assertEqual(ConditionDamageInteraction.objects.count(), count)

    def test_narration_snippets_on_transition_interactions(self) -> None:
        """Transition interactions (removes_condition=True) have narration snippets."""
        seed_elemental_interactions()
        interaction = ConditionDamageInteraction.objects.filter(
            damage_type__name="Lightning",
            removes_condition=True,
        ).first()
        self.assertIsNotNone(interaction)
        self.assertTrue(interaction.narration_snippet)
