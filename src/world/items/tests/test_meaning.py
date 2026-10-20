"""The item meaning reader and the records it reads (#4500, #4462 section 6.1, 6a rows).

Example numbers: carry gate 14 days, +1 per further 90, at most 3; the maker tie reads the
pair tier; a gift is 1 plus the holder's claimed tier toward the giver. Every case asserts
the same thing from a different side: nothing here reads a price.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import MeaningSignalKind, OwnershipEventType
from world.items.factories import ItemInstanceFactory, meaningful_item_for
from world.items.market.models import MarketSale
from world.items.models import OwnershipEvent
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
