"""A finished ware's new name reaches the name look shows (#4338)."""

from __future__ import annotations

from django.test import TestCase

from world.items.factories import ItemTemplateFactory
from world.items.market.models import MarketStall
from world.items.market.services import finish_ware, list_ware, purchase_ware
from world.items.market.tests.test_regard_gating import _persona, _square
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object


class FinishWareNameTests(TestCase):
    def test_the_finished_name_reaches_the_game_object(self) -> None:
        """The inventory reads the instance and look reads the key; both show the new name."""
        crafter = _persona("Crafter")
        buyer = _persona("Buyer", gold=5000)
        stall = MarketStall.objects.create(square=_square(), name="PC Stall", owner_persona=crafter)
        instance = ItemInstance.objects.create(
            template=ItemTemplateFactory(name="Unfinished Plate"),
            holder_character_sheet=crafter.character_sheet,
            crafter_character_sheet=crafter.character_sheet,
        )
        game_object = materialize_item_game_object(instance, crafter.character_sheet)
        listing = list_ware(stall=stall, seller=crafter, item_instance=instance, price=500)
        finishing_pass = purchase_ware(listing=listing, buyer=buyer)

        finish_ware(finishing_pass=finishing_pass, actor=buyer, name="Heron Plate", description="")

        game_object.refresh_from_db()
        assert instance.display_name == "Heron Plate"
        assert game_object.db_key == "Heron Plate"
