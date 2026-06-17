"""Tests for craft_attach_style service function (#1151)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.exceptions import StyleAlreadyAttached, StyleCapacityExceeded
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.traits.factories import CharacterTraitValueFactory


class CraftAttachStyleTests(TestCase):
    def setUp(self) -> None:
        from world.items.factories import StyleFactory, wire_enchanting_crafting
        from world.traits.models import Trait

        self.config = wire_enchanting_crafting(base_difficulty=0)
        QualityTierFactory(name="Common", numeric_min=0, numeric_max=9999, sort_order=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        CharacterTraitValueFactory(
            character=self.sheet.character,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        template = ItemTemplateFactory(style_capacity=2)
        self.item = ItemInstanceFactory(template=template)
        self.style = StyleFactory(name="TestStyle")

    def test_success_attaches_with_resolved_tier(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemStyle
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleCraftSuccess", success_level=2)):
            result = craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )
        self.assertTrue(result.attached)
        self.assertIsNotNone(result.item_style)
        self.assertIsNotNone(result.quality_tier)
        self.assertEqual(
            ItemStyle.objects.filter(item_instance=self.item, style=self.style).count(), 1
        )
        self.assertEqual(result.item_style.attachment_quality_tier, result.quality_tier)

    def test_failed_roll_attaches_nothing(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemStyle
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleCraftBotch", success_level=-1)):
            result = craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )
        self.assertFalse(result.attached)
        self.assertIsNone(result.item_style)
        self.assertIsNone(result.quality_tier)
        self.assertFalse(ItemStyle.objects.filter(item_instance=self.item).exists())

    def test_capacity_full_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        full_item = ItemInstanceFactory(template=ItemTemplateFactory(style_capacity=0))
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRollStyle", success_level=2)
        ) as capture:
            with self.assertRaises(StyleCapacityExceeded):
                craft_attach_style(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=full_item,
                    style=self.style,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached

    def test_duplicate_style_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.factories import ItemStyleFactory
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        ItemStyleFactory(item_instance=self.item, style=self.style)
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRollDupStyle", success_level=2)
        ) as capture:
            with self.assertRaises(StyleAlreadyAttached):
                craft_attach_style(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=self.item,
                    style=self.style,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached

    def test_unconfigured_check_type_raises(self) -> None:
        from world.items.exceptions import CraftingNotConfigured
        from world.items.services.crafting import craft_attach_style

        self.config.check_type = None
        self.config.save()
        with self.assertRaises(CraftingNotConfigured):
            craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )
