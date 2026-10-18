"""Journeys for an item that has fed its wearer resonance (#4461).

Ysmay wears a silk scarf carrying the Silk facet and holds a Silk thread; the daily outfit
trickle pays her resonance for it. She then sacrifices the scarf at Ombrin's shrine, or
strips the facet at the workbench. Both used to raise a database error because the
trickle's grant row still pointed at the facet. Now the grant history stays and the
scarf is soft-destroyed or the facet is marked removed.
"""

from __future__ import annotations

from decimal import Decimal

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.items.models import ItemFacet, ItemInstance
from world.magic.constants import GainSource, TargetKind
from world.magic.factories import CharacterResonanceFactory, FacetFactory, ResonanceFactory
from world.magic.models import CharacterResonance, ResonanceGrant, Thread
from world.magic.services.gain import outfit_daily_trickle_for_character
from world.worship.constants import BeingResonanceTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)


class AScarfThatHasFedItsWearer(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Shrine of Ombrin")
        profile = RoomProfileFactory(objectdb=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.watch(self.ysmay)
        sheet = self.ysmay.sheet_data

        self.ombrin = WorshippedBeingFactory(name="Ombrin")
        BeingResonanceFactory(being=self.ombrin, tier=BeingResonanceTier.FAVORED)
        ShrineDetailsFactory(feature_instance__room_profile=profile, being=self.ombrin)
        self.silk = FacetFactory(name="Silk")
        BeingFacetFactory(being=self.ombrin, facet=self.silk)

        template = ItemTemplateFactory(name="silk scarf", value=20)
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.NECK, equipment_layer=EquipmentLayer.BASE
        )
        scarf_object = ObjectDBFactory(
            db_key="silk scarf", db_typeclass_path="typeclasses.objects.Object"
        )
        scarf_object.db_location = self.ysmay
        scarf_object.save(update_fields=["db_location"])
        self.scarf = ItemInstanceFactory(
            template=template,
            holder_character_sheet=sheet,
            game_object=scarf_object,
            quality_tier=QualityTierFactory(stat_multiplier=Decimal("1.00")),
        )
        self.scarf_facet = ItemFacetFactory(
            item_instance=self.scarf,
            facet=self.silk,
            attachment_quality_tier=QualityTierFactory(stat_multiplier=Decimal("2.00")),
        )
        EquippedItemFactory(
            character=sheet,
            item_instance=self.scarf,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.BASE,
        )
        sheet.character.equipped_items.invalidate()

        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=self.resonance, balance=0, lifetime_earned=0
        )
        Thread.objects.create(
            owner=sheet,
            resonance=self.resonance,
            target_kind=TargetKind.FACET,
            target_facet=self.silk,
            level=1,
            developed_points=0,
        )
        self.assertEqual(outfit_daily_trickle_for_character(sheet), 1)
        self.earned = CharacterResonance.objects.get(
            character_sheet=sheet, resonance=self.resonance
        ).balance
        self.assertGreater(self.earned, 0)

    def _grant_still_points_at_the_facet(self) -> None:
        grant = ResonanceGrant.objects.get(source=GainSource.OUTFIT_TRICKLE)
        self.assertEqual(grant.outfit_item_facet_id, self.scarf_facet.pk)
        balance = CharacterResonance.objects.get(
            character_sheet=self.ysmay.sheet_data, resonance=self.resonance
        ).balance
        self.assertEqual(balance, self.earned)

    def test_sacrificing_the_scarf_at_the_shrine(self) -> None:
        self.telnet(self.ysmay, "sacrifice silk scarf")

        self.assertTold(self.ysmay, "Ombrin")
        self.assertIsNotNone(ItemInstance.objects.get(pk=self.scarf.pk).destroyed_at)
        self.assertTrue(ItemFacet.objects.filter(pk=self.scarf_facet.pk).exists())
        self._grant_still_points_at_the_facet()

    def test_removing_the_facet_at_the_workbench(self) -> None:
        self.telnet(self.ysmay, f"craft removefacet {self.scarf_facet.pk}")

        self.assertIsNotNone(ItemFacet.objects.get(pk=self.scarf_facet.pk).removed_at)
        self.assertEqual(outfit_daily_trickle_for_character(self.ysmay.sheet_data), 0)
        self._grant_still_points_at_the_facet()
