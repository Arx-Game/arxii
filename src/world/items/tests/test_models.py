"""Tests for item models."""

from django.db import IntegrityError
from django.test import TestCase

from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype, OwnershipEventType
from world.items.factories import (
    InteractionTypeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import (
    CurrencyBalance,
    EquippedItem,
    OwnershipEvent,
    TemplateInteraction,
    TemplateSlot,
)
from world.roster.factories import PlayerMediaFactory


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
        """Template can have multiple interaction types via through model."""
        eat = InteractionTypeFactory(name="eat", label="Eat")
        smell = InteractionTypeFactory(name="smell", label="Smell")
        template = ItemTemplateFactory(name="Muffin")
        TemplateInteraction.objects.create(template=template, interaction_type=eat)
        TemplateInteraction.objects.create(template=template, interaction_type=smell)
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

    def test_display_image_falls_back_to_template(self) -> None:
        """display_image returns template image when no instance image set."""
        media = PlayerMediaFactory()
        self.template.image = media
        self.template.save()
        instance = ItemInstanceFactory(template=self.template, image=None)
        self.assertEqual(instance.display_image, media)

    def test_display_image_instance_overrides_template(self) -> None:
        """Instance image overrides template image."""
        template_media = PlayerMediaFactory()
        instance_media = PlayerMediaFactory()
        self.template.image = template_media
        self.template.save()
        instance = ItemInstanceFactory(template=self.template, image=instance_media)
        self.assertEqual(instance.display_image, instance_media)

    def test_display_image_none_when_no_image(self) -> None:
        """display_image returns None when neither instance nor template has image."""
        instance = ItemInstanceFactory(template=self.template, image=None)
        self.assertIsNone(instance.display_image)


class TemplateInteractionTests(TestCase):
    """Tests for TemplateInteraction through model."""

    def test_flavor_text(self) -> None:
        """Interaction binding can carry flavor text."""
        template = ItemTemplateFactory(name="Blueberry Muffin")
        eat = InteractionTypeFactory(name="eat", label="Eat")
        ti = TemplateInteraction.objects.create(
            template=template,
            interaction_type=eat,
            flavor_text="Warm blueberry with a hint of cinnamon.",
        )
        self.assertEqual(ti.flavor_text, "Warm blueberry with a hint of cinnamon.")

    def test_unique_together(self) -> None:
        """Cannot add same interaction type twice to a template."""
        template = ItemTemplateFactory(name="Potion")
        drink = InteractionTypeFactory(name="drink", label="Drink")
        TemplateInteraction.objects.create(template=template, interaction_type=drink)
        with self.assertRaises(IntegrityError):
            TemplateInteraction.objects.create(template=template, interaction_type=drink)


class EquippedItemTests(TestCase):
    """Tests for EquippedItem model."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory

        cls.character = CharacterFactory(db_key="EquipTestChar")

    def test_equip_item(self) -> None:
        """An item can be equipped at a region/layer."""
        instance = ItemInstanceFactory()
        equipped = EquippedItem.objects.create(
            character=self.character,
            item_instance=instance,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.OVER,
        )
        self.assertEqual(equipped.body_region, BodyRegion.HEAD)
        self.assertEqual(equipped.equipment_layer, EquipmentLayer.OVER)

    def test_unique_slot(self) -> None:
        """Cannot equip two items in the same region/layer on one character."""
        instance1 = ItemInstanceFactory()
        instance2 = ItemInstanceFactory()
        EquippedItem.objects.create(
            character=self.character,
            item_instance=instance1,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        with self.assertRaises(IntegrityError):
            EquippedItem.objects.create(
                character=self.character,
                item_instance=instance2,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )


class OwnershipEventTests(TestCase):
    """Tests for OwnershipEvent ledger."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.account1 = AccountDB.objects.create_user(
            username="owner1",
            email="o1@test.com",
            password="testpass123",
        )
        cls.account2 = AccountDB.objects.create_user(
            username="owner2",
            email="o2@test.com",
            password="testpass123",
        )

    def test_creation_event(self) -> None:
        """Can log item creation."""
        instance = ItemInstanceFactory()
        event = OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.CREATED,
            to_account=self.account1,
            notes="Crafted by owner1",
        )
        self.assertEqual(event.event_type, OwnershipEventType.CREATED)
        self.assertIsNone(event.from_account)
        self.assertEqual(event.to_account, self.account1)

    def test_transfer_event(self) -> None:
        """Can log ownership transfer."""
        instance = ItemInstanceFactory()
        event = OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.GIVEN,
            from_account=self.account1,
            to_account=self.account2,
        )
        self.assertEqual(event.from_account, self.account1)
        self.assertEqual(event.to_account, self.account2)

    def test_ledger_ordering(self) -> None:
        """Events can be ordered newest first with explicit ordering."""
        instance = ItemInstanceFactory()
        OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.CREATED,
            to_account=self.account1,
        )
        OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.GIVEN,
            from_account=self.account1,
            to_account=self.account2,
        )
        events = list(OwnershipEvent.objects.filter(item_instance=instance).order_by("-created_at"))
        self.assertEqual(events[0].event_type, OwnershipEventType.GIVEN)
        self.assertEqual(events[1].event_type, OwnershipEventType.CREATED)


class ItemTemplateGearFieldsTests(TestCase):
    def test_facet_capacity_defaults_to_zero(self) -> None:
        from world.items.factories import ItemTemplateFactory

        tpl = ItemTemplateFactory()
        self.assertEqual(tpl.facet_capacity, 0)

    def test_gear_archetype_defaults_to_other(self) -> None:
        from world.items.factories import ItemTemplateFactory

        tpl = ItemTemplateFactory()
        self.assertEqual(tpl.gear_archetype, GearArchetype.OTHER)

    def test_facet_capacity_and_archetype_settable(self) -> None:
        from world.items.factories import ItemTemplateFactory

        tpl = ItemTemplateFactory(facet_capacity=3, gear_archetype=GearArchetype.HEAVY_ARMOR)
        self.assertEqual(tpl.facet_capacity, 3)
        self.assertEqual(tpl.gear_archetype, GearArchetype.HEAVY_ARMOR)


class CurrencyBalanceTests(TestCase):
    """Tests for CurrencyBalance model."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory

        cls.character = CharacterFactory(db_key="RichChar")

    def test_default_balance(self) -> None:
        """New balance defaults to 0."""
        balance = CurrencyBalance.objects.create(character=self.character)
        self.assertEqual(balance.gold, 0)

    def test_one_per_character(self) -> None:
        """Only one balance per character."""
        CurrencyBalance.objects.create(character=self.character)
        with self.assertRaises(IntegrityError):
            CurrencyBalance.objects.create(character=self.character)
