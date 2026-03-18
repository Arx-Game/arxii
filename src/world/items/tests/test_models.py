"""Tests for item models."""

from django.test import TestCase

from world.items.factories import InteractionTypeFactory, QualityTierFactory


class QualityTierTests(TestCase):
    """Tests for QualityTier model."""

    def test_creation(self) -> None:
        """QualityTier can be created with all fields."""
        tier = QualityTierFactory(
            name="Fine",
            color_hex="#00FF00",
            numeric_min=36,
            numeric_max=55,
            stat_multiplier=1.0,
            sort_order=3,
        )
        self.assertEqual(tier.name, "Fine")
        self.assertEqual(tier.color_hex, "#00FF00")
        self.assertEqual(tier.stat_multiplier, 1.0)

    def test_str(self) -> None:
        """String representation uses name."""
        tier = QualityTierFactory(name="Masterwork")
        self.assertEqual(str(tier), "Masterwork")

    def test_ordering(self) -> None:
        """Tiers are ordered by sort_order."""
        from world.items.models import QualityTier

        tier_b = QualityTierFactory(name="Superior", sort_order=4)
        tier_a = QualityTierFactory(name="Common", sort_order=2)
        tiers = list(QualityTier.objects.filter(id__in=[tier_a.id, tier_b.id]))
        self.assertEqual(tiers[0].name, "Common")
        self.assertEqual(tiers[1].name, "Superior")


class InteractionTypeTests(TestCase):
    """Tests for InteractionType model."""

    def test_creation(self) -> None:
        """InteractionType can be created."""
        interaction = InteractionTypeFactory(name="eat", label="Eat")
        self.assertEqual(interaction.name, "eat")
        self.assertEqual(interaction.label, "Eat")

    def test_str(self) -> None:
        """String representation uses label."""
        interaction = InteractionTypeFactory(name="drink", label="Drink")
        self.assertEqual(str(interaction), "Drink")
