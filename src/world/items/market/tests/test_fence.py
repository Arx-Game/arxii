"""The fence (#2862): sell-to-NPC + the first live contraband/smuggling heat."""

from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.market.models import MarketSale, MarketSquare, MarketStall
from world.items.market.services import MarketServiceError, sell_to_fence


class FenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.areas.models import Area

        cls.area = Area.objects.create(name="Test Docks", level=20)
        cls.square = MarketSquare.objects.create(name="Dock Market", area=cls.area)
        cls.fence = MarketStall.objects.create(
            square=cls.square,
            name="The Back Door",
            stall_kind=MarketStall.StallKind.FENCE,
        )
        cls.honest = MarketStall.objects.create(square=cls.square, name="Honest Stall")

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona

    def _held_item(self, value=100, template=None):
        obj = create_object("typeclasses.objects.Object", key="trinket", nohome=True)
        template = template or ItemTemplateFactory(value=value)
        return ItemInstanceFactory(
            template=template,
            holder_character_sheet=self.sheet,
            game_object=obj,
        )

    def test_fence_pays_the_cut_rate_and_consumes_the_item(self):
        from world.currency.services import get_or_create_purse
        from world.items.models import ItemInstance

        instance = self._held_item(value=100)
        price = sell_to_fence(self.persona, self.fence, instance)
        self.assertEqual(price, 40)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 40)
        self.assertFalse(ItemInstance.objects.filter(pk=instance.pk).exists())
        sale = MarketSale.objects.get()
        self.assertEqual(sale.kind, MarketSale.SaleKind.FENCE)
        self.assertIsNone(sale.buyer_persona)

    def test_honest_stalls_do_not_buy(self):
        instance = self._held_item()
        with self.assertRaises(MarketServiceError):
            sell_to_fence(self.persona, self.honest, instance)

    def test_worthless_goods_are_refused(self):
        instance = self._held_item(value=0)
        with self.assertRaises(MarketServiceError):
            sell_to_fence(self.persona, self.fence, instance)

    def test_vice_sale_mints_contraband_heat(self):
        from world.seeds.game_content.items import seed_consumable_catalog

        seed_consumable_catalog()
        from world.items.models import ItemTemplate

        dust = ItemTemplate.objects.get(name="Dream Dust")
        if not dust.value:
            dust.value = 50
            dust.save(update_fields=["value"])
        instance = self._held_item(template=dust)
        with patch("world.items.market.services._accrue_fence_heat") as heat:
            sell_to_fence(self.persona, self.fence, instance)
        heat.assert_called_once()
        self.assertEqual(heat.call_args.args[2], "contraband")

    def test_hot_goods_mint_smuggling_heat(self):
        instance = self._held_item(value=100)
        with (
            patch(
                "world.items.services.provenance.has_unresolved_stolen_provenance",
                return_value=True,
            ),
            patch("world.items.market.services._accrue_fence_heat") as heat,
        ):
            sell_to_fence(self.persona, self.fence, instance)
        heat.assert_called_once()
        self.assertEqual(heat.call_args.args[2], "smuggling")

    def test_honest_goods_mint_nothing(self):
        instance = self._held_item(value=100)
        with patch("world.items.market.services._accrue_fence_heat") as heat:
            sell_to_fence(self.persona, self.fence, instance)
        heat.assert_not_called()
