"""Tests for attach_style_to_item service function (#546)."""

from django.test import TestCase

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import StyleAlreadyAttached, StyleCapacityExceeded
from world.items.models import ItemStyle
from world.items.services.styles import attach_style_to_item


class AttachStyleToItemTests(TestCase):
    """Tests for attach_style_to_item."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            StyleFactory,
            TemplateSlotFactory,
        )

        cls.crafter = AccountFactory(username="StyleCrafter")
        cls.quality = QualityTierFactory()
        # Template with style_capacity=2 for most tests; capacity=1 for overflow test.
        cls.template_cap2 = ItemTemplateFactory(name="Style Cap2 Item", style_capacity=2)
        cls.template_cap1 = ItemTemplateFactory(name="Style Cap1 Item", style_capacity=1)
        cls.item_cap2 = ItemInstanceFactory(template=cls.template_cap2)
        cls.item_cap1 = ItemInstanceFactory(template=cls.template_cap1)
        cls.style_a = StyleFactory(name="StyleA")
        cls.style_b = StyleFactory(name="StyleB")

        # Build a character that wears item_cap2 so we can test cache invalidation.
        cls.character = CharacterFactory(db_key="StyleTestChar")
        TemplateSlotFactory(
            template=cls.template_cap2,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.equipped = EquippedItemFactory(
            character=cls.character,
            item_instance=cls.item_cap2,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def tearDown(self) -> None:
        # Remove any ItemStyle rows created during the test.
        ItemStyle.objects.filter(item_instance__in=[self.item_cap2, self.item_cap1]).delete()
        self.character.equipped_items.invalidate()

    def test_happy_path_creates_item_style(self) -> None:
        row = attach_style_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            style=self.style_a,
            attachment_quality_tier=self.quality,
        )
        self.assertIsNotNone(row.pk)
        self.assertEqual(row.item_instance, self.item_cap2)
        self.assertEqual(row.style, self.style_a)
        self.assertEqual(row.applied_by_account, self.crafter)
        self.assertEqual(row.attachment_quality_tier, self.quality)
        self.assertTrue(ItemStyle.objects.filter(pk=row.pk).exists())

    def test_style_already_attached_raises_on_duplicate(self) -> None:
        attach_style_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            style=self.style_a,
            attachment_quality_tier=self.quality,
        )
        with self.assertRaises(StyleAlreadyAttached):
            attach_style_to_item(
                crafter=self.crafter,
                item_instance=self.item_cap2,
                style=self.style_a,
                attachment_quality_tier=self.quality,
            )

    def test_style_capacity_exceeded_when_full(self) -> None:
        # Fill the single slot.
        attach_style_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap1,
            style=self.style_a,
            attachment_quality_tier=self.quality,
        )
        with self.assertRaises(StyleCapacityExceeded):
            attach_style_to_item(
                crafter=self.crafter,
                item_instance=self.item_cap1,
                style=self.style_b,
                attachment_quality_tier=self.quality,
            )

    def test_cache_invalidated_and_db_row_visible_for_wearer(self) -> None:
        """After attach, the DB row exists and a fresh handler sees the new style.

        Verifies the cache-invalidation path: del item_instance.cached_item_styles
        and the EquippedItem wearer loop both run without error.
        """
        row = attach_style_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            style=self.style_b,
            attachment_quality_tier=self.quality,
        )
        self.assertTrue(
            ItemStyle.objects.filter(item_instance=self.item_cap2, style=self.style_b).exists()
        )

        # cached_item_styles on a fresh fetch must include the attached style.
        from world.items.models import ItemInstance

        fresh_inst = ItemInstance.objects.get(pk=self.item_cap2.pk)
        style_ids = [is_.style_id for is_ in fresh_inst.cached_item_styles]
        self.assertIn(row.style_id, style_ids)
