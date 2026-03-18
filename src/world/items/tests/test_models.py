"""Tests for item models."""

from django.test import TestCase

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    InteractionTypeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import TemplateSlot


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


class ItemTemplateTests(TestCase):
    """Tests for ItemTemplate model."""

    def test_creation(self) -> None:
        """ItemTemplate can be created with required fields."""
        template = ItemTemplateFactory(name="Iron Longsword")
        self.assertEqual(template.name, "Iron Longsword")
        self.assertFalse(template.supports_open_close)

    def test_str(self) -> None:
        """String representation uses name."""
        template = ItemTemplateFactory(name="Silk Shirt")
        self.assertEqual(str(template), "Silk Shirt")

    def test_interactions_m2m(self) -> None:
        """Template can have multiple interaction types."""
        eat = InteractionTypeFactory(name="eat", label="Eat")
        smell = InteractionTypeFactory(name="smell", label="Smell")
        template = ItemTemplateFactory(name="Muffin")
        template.interactions.add(eat, smell)
        self.assertEqual(template.interactions.count(), 2)

    def test_slot_assignments(self) -> None:
        """Template can declare region/layer slots."""
        template = ItemTemplateFactory(name="Steel Helm")
        TemplateSlot.objects.create(
            template=template,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.OVER,
        )
        self.assertEqual(template.slots.count(), 1)
        slot = template.slots.first()
        self.assertEqual(slot.body_region, BodyRegion.HEAD)
        self.assertEqual(slot.equipment_layer, EquipmentLayer.OVER)

    def test_multi_region_item(self) -> None:
        """A template can span multiple body regions."""
        template = ItemTemplateFactory(name="Full Plate Armor")
        regions = [
            BodyRegion.TORSO,
            BodyRegion.LEFT_ARM,
            BodyRegion.RIGHT_ARM,
        ]
        for region in regions:
            TemplateSlot.objects.create(
                template=template,
                body_region=region,
                equipment_layer=EquipmentLayer.OVER,
            )
        self.assertEqual(template.slots.count(), 3)

    def test_crafting_materials_m2m(self) -> None:
        """Template can reference required materials (other templates)."""
        iron = ItemTemplateFactory(name="Iron Ingot")
        wood = ItemTemplateFactory(name="Wood Plank")
        sword = ItemTemplateFactory(name="Iron Sword", is_craftable=True)
        sword.required_materials.add(iron, wood)
        self.assertEqual(sword.required_materials.count(), 2)


class ItemInstanceTests(TestCase):
    """Tests for ItemInstance model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ItemTemplateFactory(name="Silk Shirt")

    def test_creation(self) -> None:
        """ItemInstance can be created with template reference."""
        instance = ItemInstanceFactory(template=self.template)
        self.assertEqual(instance.template, self.template)

    def test_custom_name_override(self) -> None:
        """Instance custom name overrides template name in display_name."""
        instance = ItemInstanceFactory(
            template=self.template,
            custom_name="Midnight Velvet Corsage with Silver Threading",
        )
        self.assertEqual(
            instance.display_name,
            "Midnight Velvet Corsage with Silver Threading",
        )

    def test_display_name_falls_back_to_template(self) -> None:
        """display_name returns template name when no custom name set."""
        instance = ItemInstanceFactory(template=self.template, custom_name="")
        self.assertEqual(instance.display_name, "Silk Shirt")

    def test_display_description_falls_back_to_template(self) -> None:
        """display_description returns template description when no custom."""
        self.template.description = "A fine silk shirt."
        self.template.save()
        instance = ItemInstanceFactory(template=self.template, custom_description="")
        self.assertEqual(instance.display_description, "A fine silk shirt.")

    def test_display_description_custom(self) -> None:
        """Custom description overrides template."""
        instance = ItemInstanceFactory(
            template=self.template,
            custom_description="Handwoven from midnight-blue silk.",
        )
        self.assertEqual(
            instance.display_description,
            "Handwoven from midnight-blue silk.",
        )

    def test_quantity_default(self) -> None:
        """Quantity defaults to 1."""
        instance = ItemInstanceFactory(template=self.template)
        self.assertEqual(instance.quantity, 1)

    def test_is_open_default(self) -> None:
        """is_open defaults to False."""
        instance = ItemInstanceFactory(template=self.template)
        self.assertFalse(instance.is_open)

    def test_quality_tier_nullable(self) -> None:
        """Quality tier can be null (for items without quality)."""
        instance = ItemInstanceFactory(template=self.template, quality_tier=None)
        self.assertIsNone(instance.quality_tier)

    def test_quality_tier_set(self) -> None:
        """Quality tier can be assigned."""
        tier = QualityTierFactory(name="Fine")
        instance = ItemInstanceFactory(template=self.template, quality_tier=tier)
        self.assertEqual(instance.quality_tier, tier)
