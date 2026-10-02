"""Shattered gems and fenced goods leave play by the canonical destroy rule (#4099).

Same defect class as ``consume_materials``: a bare ``ItemInstance.delete()`` leaves the
item's game object on its holder (``game_object`` cascades the other way), skips the
soft-delete an item with provenance is owed, and orphans its ownership ledger rows.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.action_points.factories import ActionPointPoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.constants import OwnershipEventType
from world.items.crafting.constants import CraftingRecipeKind
from world.items.factories import (
    CraftingRecipeFactory,
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.gems.constants import GemAxis
from world.items.gems.models import Adornment
from world.items.gems.services import adorn_item, cut_gem, pry_adornment
from world.items.models import ItemInstance, OwnershipEvent
from world.magic.tests.price_cost_helpers import carry
from world.traits.factories import CheckOutcomeFactory


def _make_gem(instance: ItemInstance) -> ItemInstance:
    GemInstanceDetailsFactory(
        item_instance=instance,
        size_grade=GemGradeFactory(axis=GemAxis.SIZE, multiplier=Decimal("1.0")),
        purity_grade=GemGradeFactory(axis=GemAxis.PURITY, multiplier=Decimal("1.0")),
        cut_grade=GemGradeFactory(axis=GemAxis.CUT, sort_order=1, multiplier=Decimal("1.0")),
    )
    instance.refresh_from_db()
    return instance


class ShatteredGemTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        ActionPointPoolFactory(character=self.sheet, current=200, maximum=200)

    def test_a_loose_gem_shattered_while_cutting_leaves_no_ghost(self) -> None:
        gem = _make_gem(carry(self.character, ItemTemplateFactory(value=100)))
        game_object_pk = gem.game_object_id
        recipe = CraftingRecipeFactory(
            kind=CraftingRecipeKind.GEM_CUT, check_type=CheckTypeFactory(), min_success_level=1
        )
        with force_check_outcome(CheckOutcomeFactory(name="GhostCut", success_level=-1)):
            result = cut_gem(gem_instance=gem, crafter_character=self.character, recipe=recipe)

        self.assertTrue(result.shattered)
        self.assertFalse(ItemInstance.objects.filter(pk=gem.pk).exists())
        self.assertFalse(ObjectDB.objects.filter(pk=game_object_pk).exists())
        self.assertEqual(list(self.character.carried_items), [])

    def test_a_set_gem_with_provenance_shattered_while_prying_is_kept_out_of_play(self) -> None:
        gem = _make_gem(carry(self.character, ItemTemplateFactory(value=100)))
        OwnershipEvent.objects.create(
            item_instance=gem, event_type=OwnershipEventType.GIVEN, to_character_sheet=self.sheet
        )
        host = ItemInstanceFactory(
            template=ItemTemplateFactory(value=50, adornment_capacity=3), lore_value=0
        )
        adornment = adorn_item(host_instance=host, gem_instance=gem)
        with force_check_outcome(CheckOutcomeFactory(name="GhostPry", success_level=-1)):
            result = pry_adornment(
                adornment=adornment,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                check_type=CheckTypeFactory(),
            )

        self.assertTrue(result.shattered)
        gem.refresh_from_db()
        self.assertIsNotNone(gem.destroyed_at)
        self.assertIsNone(ObjectDB.objects.get(pk=gem.game_object_id).location)
        self.assertFalse(Adornment.objects.filter(pk=adornment.pk).exists())
        self.assertTrue(
            gem.ownership_events.filter(event_type=OwnershipEventType.CONSUMED).exists()
        )
