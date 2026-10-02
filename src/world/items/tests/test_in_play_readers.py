"""A soft-deleted item keeps its holder, so every holder-keyed reader must skip it (#4099).

``destroy_consumed_item_instance`` soft-deletes an item with a history: it stamps
``destroyed_at`` and takes the game object out of play, but the row keeps its
``holder_character_sheet``. A reader keyed on the holder that does not use
``ItemInstance.objects.in_play()`` keeps seeing it, which is how a fenced item could be
fenced again for a second payout.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer, OwnershipEventType
from world.items.crafting.cost import stage_and_assert_affordable
from world.items.exceptions import CraftingCostUnaffordable
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.market.models import MarketSquare, MarketStall
from world.items.market.services import MarketServiceError, sell_to_fence
from world.items.models import EquippedItem, ItemInstance, OwnershipEvent


def _held_with_history(sheet, *, value: int = 100, quantity: int = 1) -> ItemInstance:
    """A held item with a game object and STOLEN provenance, so destroying it soft-deletes."""
    obj = create_object("typeclasses.objects.Object", key="trinket", nohome=True)
    instance = ItemInstanceFactory(
        template=ItemTemplateFactory(value=value),
        holder_character_sheet=sheet,
        game_object=obj,
        quantity=quantity,
    )
    OwnershipEvent.objects.create(
        item_instance=instance, event_type=OwnershipEventType.STOLEN, to_character_sheet=sheet
    )
    return instance


class _FenceFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.areas.models import Area

        area = Area.objects.create(name="In-play Docks", level=20)
        square = MarketSquare.objects.create(name="In-play Market", area=area)
        cls.fence = MarketStall.objects.create(
            square=square, name="Twice Door", stall_kind=MarketStall.StallKind.FENCE
        )

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona


class FenceTwiceTests(_FenceFixture):
    def test_the_same_item_cannot_be_fenced_twice(self):
        from world.currency.services import get_or_create_purse

        instance = _held_with_history(self.sheet)
        self.assertEqual(sell_to_fence(self.persona, self.fence, instance), 40)
        with self.assertRaises(MarketServiceError) as ctx:
            sell_to_fence(self.persona, self.fence, instance)
        self.assertTrue(ctx.exception.user_message)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 40)

    def test_the_fence_action_does_not_find_a_fenced_item(self):
        from actions.definitions.market import SellToFenceAction
        from world.currency.services import get_or_create_purse

        instance = _held_with_history(self.sheet)
        actor = self.sheet.character
        first = SellToFenceAction().execute(
            actor, stall_id=self.fence.pk, item_name=instance.template.name
        )
        self.assertTrue(first.success, first.message)
        second = SellToFenceAction().execute(
            actor, stall_id=self.fence.pk, item_name=instance.template.name
        )
        self.assertFalse(second.success)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 40)


class CraftingSkipsSoftDeletedTests(_FenceFixture):
    def test_a_fenced_stack_cannot_pay_a_crafting_cost(self):
        stack = _held_with_history(self.sheet, quantity=3)
        sell_to_fence(self.persona, self.fence, stack)
        stack.refresh_from_db()
        self.assertIsNotNone(stack.destroyed_at)
        self.assertEqual(stack.holder_character_sheet_id, self.sheet.pk)

        requirement = CraftingMaterialRequirementFactory(item_template=stack.template, quantity=1)
        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=requirement.recipe,
                crafter_character=self.sheet.character,
                crafter_character_sheet=self.sheet,
            )


class EstateSkipsSoftDeletedTests(_FenceFixture):
    def test_an_heir_does_not_inherit_a_destroyed_item(self):
        from world.estates.services import _sweep_residuary_items

        instance = _held_with_history(self.sheet)
        sell_to_fence(self.persona, self.fence, instance)
        heir = CharacterSheetFactory().primary_persona

        _sweep_residuary_items(self.sheet, heir, set())

        instance.refresh_from_db()
        self.assertEqual(instance.holder_character_sheet_id, self.sheet.pk)
        self.assertFalse(
            instance.ownership_events.filter(event_type=OwnershipEventType.INHERITED).exists()
        )


class DestroyUnequipsTests(TestCase):
    def test_a_consumed_equipped_item_is_no_longer_worn(self):
        from world.items.services.usage import consume_item_charges

        sheet = CharacterSheetFactory()
        obj = create_object("typeclasses.objects.Object", key="draught", nohome=True)
        obj.location = sheet.character
        obj.save()
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(is_consumable=True, max_charges=1),
            holder_character_sheet=sheet,
            game_object=obj,
            charges=1,
            custom_name="Grandmother's flask",
        )
        EquippedItemFactory(
            character=sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        list(sheet.character.equipped_items)

        consume_item_charges(item_instance=item, amount=1)

        item.refresh_from_db()
        self.assertIsNotNone(item.destroyed_at)
        self.assertFalse(EquippedItem.objects.filter(item_instance=item).exists())
        self.assertNotIn(item, [e.item_instance for e in sheet.character.equipped_items])
