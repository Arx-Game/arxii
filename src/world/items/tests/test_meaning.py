"""The item meaning reader and the records it reads (#4500, #4462 section 6.1, 6a rows).

Example numbers: carry gate 14 days, +1 per further 90, at most 3; the maker tie reads the
pair tier; a gift is 1 plus the holder's claimed tier toward the giver. Every case asserts
the same thing from a different side: nothing here reads a price.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import (
    BodyRegion,
    EquipmentLayer,
    MeaningSignalKind,
    OwnershipEventType,
    ShowcaseMode,
)
from world.items.factories import (
    ItemInstanceFactory,
    OutfitFactory,
    OutfitSlotFactory,
    meaningful_item_for,
)
from world.items.market.models import MarketSale
from world.items.models import FashionShowing, ItemLineage, OwnershipEvent
from world.items.services.holding import set_item_holder
from world.items.services.meaning import item_meaning
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTierFactory
from world.relationships.helpers import pair_tier
from world.worship.invocation_services import get_devotion_config


def _kinds(meaning) -> dict[str, int]:
    return {signal.kind: signal.points for signal in meaning.signals}


class PairTierTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()

    def test_no_tie_is_tier_zero(self) -> None:
        self.assertEqual(pair_tier(self.a, self.b), 0)

    def test_the_two_sides_depth_adds_up(self) -> None:
        CharacterRelationshipFactory(source=self.a, target=self.b, scene_depth=120)
        self.assertEqual(pair_tier(self.a, self.b), 1)
        CharacterRelationshipFactory(source=self.b, target=self.a, invested_depth=100)
        self.assertEqual(pair_tier(self.a, self.b), 2)
        self.assertEqual(pair_tier(self.b, self.a), 2)


class ItemMeaningTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_devotion_config()
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        cls.holder = CharacterSheetFactory()
        cls.other = CharacterSheetFactory()

    def _item(self, days: int = 30, **kwargs):
        return ItemInstanceFactory(
            holder_character_sheet=self.holder,
            held_since=timezone.now() - timedelta(days=days),
            **kwargs,
        )

    def test_a_bought_item_with_no_history_is_worth_nothing_however_long_held(self) -> None:
        item = self._item(days=400, template__value=9999)

        self.assertEqual(item_meaning(item, self.holder, config=self.config).points, 0)

    def test_carried_alone_never_counts_and_nothing_counts_before_the_gate(self) -> None:
        fresh = meaningful_item_for(self.holder, days=3)

        self.assertEqual(item_meaning(fresh, self.holder, config=self.config).points, 0)

    def test_own_work_after_the_gate_is_one_plus_carried(self) -> None:
        item = meaningful_item_for(self.holder, days=30)

        meaning = item_meaning(item, self.holder, config=self.config)

        self.assertEqual(
            _kinds(meaning), {MeaningSignalKind.CARRIED: 1, MeaningSignalKind.OWN_WORK: 1}
        )

    def test_carried_grows_per_ninety_days_and_stops_at_the_cap(self) -> None:
        by_days = {}
        for days in (14, 103, 104, 400):
            item = meaningful_item_for(self.holder, days=days)
            by_days[days] = _kinds(item_meaning(item, self.holder, config=self.config))[
                MeaningSignalKind.CARRIED
            ]

        self.assertEqual(by_days, {14: 1, 103: 1, 104: 2, 400: 3})

    def test_a_gift_is_one_plus_the_claimed_tier_toward_the_giver(self) -> None:
        CharacterRelationshipFactory(source=self.holder, target=self.other, tier=3)
        item = self._item()
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=self.other,
            to_character_sheet=self.holder,
        )
        set_item_holder(item, self.holder, event=event)
        item.held_since = timezone.now() - timedelta(days=120)
        item.save(update_fields=["held_since"])

        meaning = item_meaning(item, self.holder, config=self.config)

        self.assertEqual(_kinds(meaning), {MeaningSignalKind.CARRIED: 2, MeaningSignalKind.GIFT: 4})

    def test_a_gift_from_a_stranger_is_one(self) -> None:
        item = self._item()
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=self.other,
            to_character_sheet=self.holder,
        )
        item.holding_event = event
        item.save(update_fields=["holding_event"])

        self.assertEqual(
            _kinds(item_meaning(item, self.holder, config=self.config))[MeaningSignalKind.GIFT], 1
        )

    def test_heirloom_counts_each_inheritance_to_three(self) -> None:
        item = self._item()
        for _ in range(5):
            OwnershipEvent.objects.create(
                item_instance=item,
                event_type=OwnershipEventType.INHERITED,
                from_character_sheet=self.other,
                to_character_sheet=self.holder,
            )

        meaning = item_meaning(item, self.holder, config=self.config)

        self.assertEqual(_kinds(meaning)[MeaningSignalKind.HEIRLOOM], 3)

    def test_made_by_a_tie_reads_the_pair_tier_and_takes_the_best_maker(self) -> None:
        tailor = CharacterSheetFactory()
        CharacterRelationshipFactory(source=self.holder, target=self.other, scene_depth=120)
        CharacterRelationshipFactory(source=self.holder, target=tailor, scene_depth=260)
        item = self._item(crafter_character_sheet=self.other)
        MarketSale.objects.create(
            kind=MarketSale.SaleKind.SERVICE,
            buyer_persona=self.holder.primary_persona,
            seller_persona=tailor.primary_persona,
            item_instance=item,
            price=40,
        )

        meaning = item_meaning(item, self.holder, config=self.config)

        # Pair tier with the tailor is 2 (260 depth); with the crafter 1. The best counts.
        self.assertEqual(_kinds(meaning)[MeaningSignalKind.MADE_BY_TIE], 2)
        # A fee is paid for the service: it is not meaning and is never read.
        self.assertNotIn(MeaningSignalKind.GIFT, _kinds(meaning))

    def test_a_maker_with_no_tie_adds_nothing(self) -> None:
        item = self._item(crafter_character_sheet=self.other)

        self.assertEqual(item_meaning(item, self.holder, config=self.config).points, 0)

    def test_the_tie_counts_once_when_the_maker_is_also_the_giver(self) -> None:
        CharacterRelationshipFactory(source=self.holder, target=self.other, scene_depth=260)
        item = self._item(crafter_character_sheet=self.other)
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=self.other,
            to_character_sheet=self.holder,
        )
        item.holding_event = event
        item.save(update_fields=["holding_event"])

        kinds = _kinds(item_meaning(item, self.holder, config=self.config))

        self.assertEqual(kinds[MeaningSignalKind.MADE_BY_TIE], 2)
        self.assertEqual(kinds[MeaningSignalKind.GIFT], 1)  # the further act, not the tie again


class CommissionLoopSignalTests(TestCase):
    """The signals the commission loop adds (#4512): designed by you, made for, made from,
    shown. Example numbers: made for is 1 plus the claimed tier toward the dedicator, up to
    4; made from is the recorded points up to 3; shown is 1 per 2 engagements, up to 3."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_devotion_config()
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        cls.holder = CharacterSheetFactory()
        cls.maker = CharacterSheetFactory()

    def _item(self, **kwargs):
        return ItemInstanceFactory(
            holder_character_sheet=self.holder,
            held_since=timezone.now() - timedelta(days=30),
            **kwargs,
        )

    def _dedicated(self, item, *, by=None, to=None) -> None:
        by = by or self.maker
        to = to or self.holder
        item.dedicated_by_persona = by.primary_persona
        item.dedicated_to_persona = to.primary_persona
        item.dedicated_at = timezone.now()
        item.save(update_fields=["dedicated_by_persona", "dedicated_to_persona", "dedicated_at"])

    def test_designed_by_you_is_one_for_the_designer_and_nothing_for_a_payer(self) -> None:
        written = self._item(designer_character_sheet=self.holder)
        paid = self._item(designer_character_sheet=self.maker)

        self.assertEqual(
            _kinds(item_meaning(written, self.holder, config=self.config)),
            {MeaningSignalKind.CARRIED: 1, MeaningSignalKind.DESIGNED: 1},
        )
        self.assertEqual(item_meaning(paid, self.holder, config=self.config).points, 0)

    def test_made_for_is_one_plus_the_claimed_tier_toward_the_dedicator(self) -> None:
        CharacterRelationshipFactory(source=self.holder, target=self.maker, tier=2)
        item = self._item()
        self._dedicated(item)

        kinds = _kinds(item_meaning(item, self.holder, config=self.config))

        self.assertEqual(kinds[MeaningSignalKind.MADE_FOR], 3)

    def test_made_for_counts_only_for_the_dedicatee_and_not_when_bought_from_the_dedicator(
        self,
    ) -> None:
        bystander = CharacterSheetFactory()
        item = self._item()
        self._dedicated(item, to=bystander)
        self.assertEqual(item_meaning(item, self.holder, config=self.config).points, 0)

        bought = self._item()
        self._dedicated(bought)
        MarketSale.objects.create(
            kind=MarketSale.SaleKind.WARE,
            buyer_persona=self.holder.primary_persona,
            seller_persona=self.maker.primary_persona,
            item_instance=bought,
            price=900,
        )
        self.assertEqual(item_meaning(bought, self.holder, config=self.config).points, 0)

    def test_the_makers_tie_counts_once_and_the_dedication_adds_one(self) -> None:
        CharacterRelationshipFactory(source=self.holder, target=self.maker, scene_depth=260)
        item = self._item(crafter_character_sheet=self.maker, designer_character_sheet=self.holder)
        self._dedicated(item)

        kinds = _kinds(item_meaning(item, self.holder, config=self.config))

        self.assertEqual(kinds[MeaningSignalKind.MADE_BY_TIE], 2)
        self.assertEqual(kinds[MeaningSignalKind.MADE_FOR], 1)
        self.assertEqual(kinds[MeaningSignalKind.DESIGNED], 1)

    def test_made_from_is_the_recorded_points_to_the_cap_and_ignores_the_source_after(
        self,
    ) -> None:
        item = self._item(crafter_character_sheet=self.holder)
        ItemLineage.objects.create(item=item, source_item=None, source_name="worn saddle", points=4)

        meaning = item_meaning(item, self.holder, config=self.config)

        self.assertEqual(_kinds(meaning)[MeaningSignalKind.MADE_FROM], 3)

    def test_made_from_does_not_pass_to_a_stranger(self) -> None:
        item = self._item(crafter_character_sheet=self.maker)
        ItemLineage.objects.create(item=item, source_item=None, source_name="saddle", points=4)

        self.assertEqual(item_meaning(item, self.holder, config=self.config).points, 0)

    def test_shown_counts_settled_successful_showings_without_the_carry_gate(self) -> None:
        fresh = ItemInstanceFactory(holder_character_sheet=self.holder)
        for roll_success, settled, engaged in (
            (True, True, 3),  # one point
            (True, True, 5),  # two points
            (False, True, 9),  # a failed roll counts nothing
            (True, False, 9),  # unsettled counts nothing
        ):
            FashionShowing.objects.create(
                character_sheet=self.holder,
                mode=ShowcaseMode.PIECE,
                statement_item=fresh,
                stake=1,
                roll_success=roll_success,
                settled=settled,
                engagement_count=engaged,
            )

        meaning = item_meaning(fresh, self.holder, config=self.config)

        # Brand-new, so carried and every personal signal wait for the gate; shown does not.
        self.assertEqual(_kinds(meaning), {MeaningSignalKind.SHOWN: 3})

    def test_shown_reads_a_showing_of_the_statement_outfit_and_stops_at_the_cap(self) -> None:
        item = self._item()
        wardrobe = ItemInstanceFactory(holder_character_sheet=self.holder)
        outfit = OutfitFactory(character_sheet=self.holder, wardrobe=wardrobe)
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        for _ in range(3):
            FashionShowing.objects.create(
                character_sheet=self.holder,
                mode=ShowcaseMode.ENSEMBLE,
                statement_outfit=outfit,
                stake=1,
                roll_success=True,
                settled=True,
                engagement_count=8,
            )

        kinds = _kinds(item_meaning(item, self.holder, config=self.config))

        self.assertEqual(kinds, {MeaningSignalKind.CARRIED: 1, MeaningSignalKind.SHOWN: 3})


class SetItemHolderTests(TestCase):
    def test_it_restarts_the_carry_clock_and_records_the_event(self) -> None:
        old, new = CharacterSheetFactory(), CharacterSheetFactory()
        item = ItemInstanceFactory(
            holder_character_sheet=old, held_since=timezone.now() - timedelta(days=200)
        )
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=old,
            to_character_sheet=new,
        )

        set_item_holder(item, new, event=event)

        item.refresh_from_db()
        self.assertEqual(item.holder_character_sheet, new)
        self.assertEqual(item.holding_event, event)
        self.assertLess(timezone.now() - item.held_since, timedelta(minutes=1))
