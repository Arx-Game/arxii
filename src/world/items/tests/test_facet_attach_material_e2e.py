"""E2E: FACET_ATTACH crafting consumes reagent materials (#707).

Proves CraftingMaterialRequirement content on the FACET_ATTACH recipe is
staged/consumed by the existing generic cost pipeline
(``stage_and_assert_affordable``/``consume_cost`` in ``world.items.crafting.cost``)
with no service-layer change — this task is content-only.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.exceptions import CraftingCostUnaffordable
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.models import ItemInstance
from world.items.seeds_facet_reagents import ensure_facet_attach_reagent_requirement
from world.items.services.crafting import craft_attach_facet
from world.magic.factories import FacetFactory
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory
from world.traits.models import Trait


class FacetAttachMaterialE2ETests(TestCase):
    def setUp(self) -> None:
        # wire_enchanting_crafting seeds the Common/Fine/Masterwork tier ladder
        # and requires_station defaults True (#1234) — a Lab station + location
        # is required below for craft_attach_facet to get past the station gate.
        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.reagent_template = ensure_facet_attach_reagent_requirement(self.recipe)

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        room_profile = RoomProfileFactory()
        self.sheet.character.location = room_profile.objectdb
        self.sheet.character.save()
        install_full_lab_station(room_profile)

        template = ItemTemplateFactory(facet_capacity=3)
        self.item_instance = ItemInstanceFactory(
            template=template, holder_character_sheet=self.sheet
        )
        self.facet = FacetFactory()

    def test_facet_attach_without_reagent_fails_affordability(self) -> None:
        with self.assertRaises(CraftingCostUnaffordable):
            craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item_instance,
                facet=self.facet,
            )

    def test_facet_attach_with_reagent_consumes_it(self) -> None:
        reagent_instance = ItemInstanceFactory(
            template=self.reagent_template, holder_character_sheet=self.sheet
        )
        with force_check_outcome(CheckOutcomeFactory(name="FacetAttachSuccess", success_level=2)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item_instance,
                facet=self.facet,
            )
        self.assertTrue(result.attached)
        self.assertFalse(ItemInstance.objects.filter(pk=reagent_instance.pk).exists())
