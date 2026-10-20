"""The commission loop (#4512, slice 2 of #4462): design text, dedication, lineage.

Example numbers only. Nothing here reads a fee or a price: the fee is paid and counts for
nothing, and credit follows the words a person wrote.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.definitions.crafting import CreateItemAction
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse, transfer
from world.items.constants import MeaningSignalKind
from world.items.crafting.constants import CraftingRecipeKind
from world.items.exceptions import (
    CannotDedicateToSelf,
    DesignAlreadyWritten,
    ItemAlreadyDedicated,
    WorkedFromUnavailable,
)
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    meaningful_item_for,
    wire_enchanting_crafting,
)
from world.items.market.models import CraftingServiceOffer, MarketSale
from world.items.market.services import MarketServiceError, run_service_craft
from world.items.models import ItemInstance, ItemLineage, ItemTemplate
from world.items.services.cleanup import purge_expired_soft_deleted_items
from world.items.services.crafted_display import crafted_provenance_line
from world.items.services.dedication import dedicate_item
from world.items.services.meaning import item_meaning
from world.magic.factories import FacetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.invocation_services import get_devotion_config


def _player(room_profile, name: str):
    """A sheet whose character stands in ``room_profile`` and is played by an account."""
    sheet = CharacterSheetFactory(character__db_key=name)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=AccountFactory()))
    sheet.character.location = room_profile.objectdb
    sheet.character.save()
    return sheet


class _CommissionCase(TestCase):
    def setUp(self) -> None:
        wire_enchanting_crafting(base_difficulty=0)
        self.shop = RoomProfileFactory()
        install_full_lab_station(self.shop)
        self.corwen = _player(self.shop, "Corwen")
        self.linnet = _player(self.shop, "Linnet")
        self.success = CheckOutcomeFactory(name="CommissionSuccess", success_level=5)
        self.config = get_devotion_config()

    def _make(self, maker, **kwargs):
        with force_check_outcome(self.success):
            return CreateItemAction().run(
                actor=maker.character,
                output_template=ItemTemplate.objects.get(name="Craftable Dagger"),
                **kwargs,
            )


class MakingTests(_CommissionCase):
    def test_blank_text_leaves_the_designer_empty_and_text_credits_the_maker(self) -> None:
        blank = self._make(self.corwen).data["result"].item_instance
        written = self._make(self.corwen, custom_name="Fang").data["result"].item_instance

        self.assertIsNone(blank.designer_character_sheet)
        self.assertEqual(written.designer_character_sheet, self.corwen)

    def test_making_for_someone_writes_a_permanent_dedication(self) -> None:
        item = (
            self._make(self.corwen, dedicate_to=self.linnet.primary_persona)
            .data["result"]
            .item_instance
        )

        self.assertEqual(item.dedicated_to_persona, self.linnet.primary_persona)
        self.assertEqual(item.dedicated_by_persona, self.corwen.primary_persona)
        self.assertIsNotNone(item.dedicated_at)
        with self.assertRaises(ItemAlreadyDedicated):
            dedicate_item(item, by=self.corwen.primary_persona, to=self.linnet.primary_persona)

    def test_a_piece_cannot_be_made_for_its_maker_and_nothing_is_made(self) -> None:
        before = ItemInstance.objects.count()

        result = self._make(self.corwen, dedicate_to=self.corwen.primary_persona)

        self.assertFalse(result.success)
        self.assertEqual(result.message, CannotDedicateToSelf.user_message)
        self.assertEqual(ItemInstance.objects.count(), before)

    def test_working_an_heirloom_in_uses_it_up_and_records_it(self) -> None:
        saddle = meaningful_item_for(
            self.corwen, days=400, template=ItemTemplateFactory(name="worn saddle"), custom_name=""
        )
        expected = item_meaning(saddle, self.corwen, config=self.config).points

        boots = self._make(self.corwen, worked_from=saddle).data["result"].item_instance

        saddle.refresh_from_db()
        self.assertIsNotNone(saddle.destroyed_at)
        self.assertIsNone(saddle.holder_character_sheet)
        row = ItemLineage.objects.get(item=boots)
        self.assertEqual(
            (row.source_item, row.source_name, row.points), (saddle, "worn saddle", expected)
        )
        self.assertGreater(expected, 0)
        self.assertIn("Worked from worn saddle, which is gone.", crafted_provenance_line(boots))

    def test_an_item_the_maker_does_not_hold_cannot_be_worked_in(self) -> None:
        theirs = ItemInstanceFactory(holder_character_sheet=self.linnet)

        result = self._make(self.corwen, worked_from=theirs)

        self.assertFalse(result.success)
        self.assertEqual(result.message, WorkedFromUnavailable.user_message)
        theirs.refresh_from_db()
        self.assertIsNone(theirs.destroyed_at)

    def test_made_from_and_made_for_count_for_the_dedicatee(self) -> None:
        saddle = meaningful_item_for(self.corwen, days=400)
        boots = (
            self._make(self.corwen, dedicate_to=self.linnet.primary_persona, worked_from=saddle)
            .data["result"]
            .item_instance
        )
        boots.holder_character_sheet = self.linnet
        boots.held_since = timezone.now() - timedelta(days=30)
        boots.save(update_fields=["holder_character_sheet", "held_since"])

        kinds = {s.kind for s in item_meaning(boots, self.linnet, config=self.config).signals}

        self.assertIn(MeaningSignalKind.MADE_FOR, kinds)
        self.assertIn(MeaningSignalKind.MADE_FROM, kinds)

    def test_the_purge_spares_a_dedicated_piece_and_a_lineage(self) -> None:
        old = timezone.now() - timedelta(days=400)
        plain = ItemInstanceFactory(destroyed_at=old)
        dedicated = ItemInstanceFactory(destroyed_at=old)
        dedicate_item(dedicated, by=self.corwen.primary_persona, to=self.linnet.primary_persona)
        worked = ItemInstanceFactory(destroyed_at=old)
        ItemLineage.objects.create(item=worked, source_item=None, source_name="saddle", points=2)

        purge_expired_soft_deleted_items()

        self.assertFalse(ItemInstance.objects.filter(pk=plain.pk).exists())
        self.assertTrue(ItemInstance.objects.filter(pk=dedicated.pk).exists())
        self.assertTrue(ItemInstance.objects.filter(pk=worked.pk).exists())

    def test_a_nameless_dedicated_piece_destroyed_by_use_is_kept(self) -> None:
        bare = ItemInstanceFactory(quality_tier=None)
        self.assertFalse(bare.differs_from_template)
        dedicate_item(bare, by=self.corwen.primary_persona, to=self.linnet.primary_persona)
        self.assertTrue(bare.differs_from_template)


class CommissionTests(_CommissionCase):
    def setUp(self) -> None:
        super().setUp()
        self.facet = FacetFactory(name="Kestrel")
        self.offer = CraftingServiceOffer.objects.create(
            crafter_persona=self.corwen.primary_persona,
            recipe_kind=CraftingRecipeKind.FACET_ATTACH,
            shop_room=self.shop,
            fee=40,
        )
        # As the action loads it: the kind is a plain string, not the enum member.
        self.offer.refresh_from_db()
        transfer(amount=500, reason="test", to_purse=get_or_create_purse(self.linnet))
        self.coat = ItemInstanceFactory(
            template=ItemTemplateFactory(name="riding coat", facet_capacity=2),
            holder_character_sheet=self.linnet,
            crafter_character_sheet=self.corwen,
            designer_character_sheet=None,
        )

    def _commission(self, item=None, **kwargs):
        with force_check_outcome(self.success):
            return run_service_craft(
                offer=self.offer,
                buyer=self.linnet.primary_persona,
                buyer_character=self.linnet.character,
                item_instance=item or self.coat,
                target=self.facet,
                **kwargs,
            )

    def test_the_commissioner_who_writes_text_is_the_designer_and_it_is_credited(self) -> None:
        self._commission(name="Highwind Coat", description="Grey wool, cut for riding.")

        self.coat.refresh_from_db()
        self.assertEqual(self.coat.custom_name, "Highwind Coat")
        self.assertEqual(self.coat.designer_character_sheet, self.linnet)
        line = crafted_provenance_line(self.coat)
        self.assertIn("Made by", line)
        self.assertIn("Designed by", line)
        self.assertIn(f"Facet work by {self.corwen.primary_persona.name}.", line)
        self.assertEqual(MarketSale.objects.filter(item_instance=self.coat).count(), 1)

    def test_the_fee_alone_makes_nobody_a_designer(self) -> None:
        _result, fee = self._commission()

        self.coat.refresh_from_db()
        self.assertIsNone(self.coat.designer_character_sheet)
        self.assertEqual(get_or_create_purse(self.linnet).balance, 500 - fee)
        self.assertNotIn(
            MeaningSignalKind.DESIGNED,
            {s.kind for s in item_meaning(self.coat, self.linnet, config=self.config).signals},
        )

    def test_an_artists_words_are_never_written_over(self) -> None:
        self.coat.custom_name = "Corwen's Riding Coat"
        self.coat.designer_character_sheet = self.corwen
        self.coat.save(update_fields=["custom_name", "designer_character_sheet"])
        balance = get_or_create_purse(self.linnet).balance

        with self.assertRaises(DesignAlreadyWritten):
            self._commission(name="Mine now")

        self.coat.refresh_from_db()
        self.assertEqual(self.coat.custom_name, "Corwen's Riding Coat")
        self.assertEqual(get_or_create_purse(self.linnet).balance, balance)

    def test_a_designer_may_rewrite_their_own_words(self) -> None:
        self.coat.custom_name = "Old name"
        self.coat.designer_character_sheet = self.linnet
        self.coat.save(update_fields=["custom_name", "designer_character_sheet"])

        self._commission(name="New name")

        self.coat.refresh_from_db()
        self.assertEqual(self.coat.custom_name, "New name")

    def test_the_dedication_is_written_once_and_never_to_the_commissioner(self) -> None:
        with self.assertRaises(CannotDedicateToSelf):
            self._commission(dedicate_to=self.linnet.primary_persona)

        self._commission(dedicate_to=self.corwen.primary_persona)
        self.coat.refresh_from_db()
        self.assertEqual(self.coat.dedicated_to_persona, self.corwen.primary_persona)
        self.assertEqual(self.coat.dedicated_by_persona, self.linnet.primary_persona)

        with self.assertRaises(ItemAlreadyDedicated):
            self._commission(dedicate_to=self.corwen.primary_persona)

    def test_a_commission_for_a_piece_not_in_hand_is_refused_before_paying(self) -> None:
        theirs = ItemInstanceFactory(holder_character_sheet=self.corwen)
        balance = get_or_create_purse(self.linnet).balance

        with self.assertRaises(MarketServiceError):
            self._commission(item=theirs, name="Mine")

        self.assertEqual(get_or_create_purse(self.linnet).balance, balance)

    def test_a_failed_attempt_still_costs_the_fee_and_keeps_her_words_but_credits_no_facet_work(
        self,
    ) -> None:
        botch = CheckOutcomeFactory(name="CommissionBotch", success_level=-5)

        with force_check_outcome(botch):
            result, fee = run_service_craft(
                offer=self.offer,
                buyer=self.linnet.primary_persona,
                buyer_character=self.linnet.character,
                item_instance=self.coat,
                target=self.facet,
                name="Highwind Coat",
            )

        self.assertFalse(result.attached)
        self.coat.refresh_from_db()
        self.assertEqual(self.coat.custom_name, "Highwind Coat")
        self.assertEqual(get_or_create_purse(self.linnet).balance, 500 - fee)
        self.assertFalse(MarketSale.objects.filter(item_instance=self.coat).exists())
        self.assertNotIn("Facet work", crafted_provenance_line(self.coat))


class GoneNoteTests(_CommissionCase):
    def test_a_given_up_piece_is_marked_gone_with_the_place_and_not_the_reason(self) -> None:
        from world.items.constants import OwnershipEventType
        from world.items.models import OwnershipEvent

        item = ItemInstanceFactory(destroyed_at=timezone.now())
        OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.CONSUMED,
            notes="Given up to the Highwind: sacrifice:shrine",
        )

        self.assertIn("Gone: Given up to the Highwind.", crafted_provenance_line(item))
        self.assertNotIn("sacrifice:shrine", crafted_provenance_line(item))

    def test_facet_workers_read_oldest_first_whichever_path_loaded_the_item(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory

        first, second = self.corwen.primary_persona, self.linnet.primary_persona
        item = ItemInstanceFactory(holder_character_sheet=self.linnet)
        obj = ObjectDBFactory(db_key="coat", db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = self.linnet.character
        obj.save(update_fields=["db_location"])
        item.game_object = obj
        item.save(update_fields=["game_object"])
        for seller in (first, second):
            MarketSale.objects.create(
                kind=MarketSale.SaleKind.SERVICE,
                buyer_persona=second if seller is first else first,
                seller_persona=seller,
                item_instance=item,
                price=10,
            )
        cold = [sale.seller_persona for sale in item.cached_service_sales]

        self.linnet.character.carried_items.invalidate()
        handler_item = self.linnet.character.carried_items.get(item.pk)
        self.assertIsNotNone(handler_item)
        warm = [sale.seller_persona for sale in handler_item.cached_service_sales]

        self.assertEqual(cold, [first, second])
        self.assertEqual(warm, cold)
