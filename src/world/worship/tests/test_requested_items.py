"""The items a being asks for, and the keepsakes and Relic it answers to (#4530, #4462 6.4).

Example numbers: a request is worth 3 points; requests must be cheap (value 5 or less); a
keepsake of the being eases 3 per point; a rite eases 3 per point. Checks are forced through
``force_check_outcome``; everything else is the real path.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.ceremonies.models import CeremonyOffering, OfferingSignal
from world.ceremonies.services import sacrifice_items
from world.checks.test_helpers import force_check_outcome
from world.items.constants import KeepsakeSubject, MeaningSignalKind
from world.items.factories import ItemFacetFactory, ItemInstanceFactory, KeepsakeFactory
from world.items.models import ItemInstance
from world.magic.factories import FacetFactory
from world.worship.constants import InvocationPieceSource
from world.worship.factories import RequestedItemFactory
from world.worship.invocation_services import get_devotion_config, invocation_difficulty
from world.worship.models import Relic, RequestedItem
from world.worship.pledge_services import close_pledge, pledge_card, take_pledge
from world.worship.request_services import request_lines
from world.worship.rite_services import perform_worship_rite, read_rite_gifts
from world.worship.sacrifice_services import sacrifice_slots_left
from world.worship.tests.test_pledges import PledgeTestBase
from world.worship.worn_services import worn_meaning


class RequestedItemTestBase(PledgeTestBase):
    def _held(self, template=None, *, value: int = 2, days: int = 1) -> ItemInstance:
        """An item the sheet carries and bought: no history, so no meaning of its own."""
        obj = ObjectDBFactory(db_key="errand", db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = self.sheet.character
        obj.save(update_fields=["db_location"])
        kwargs = {"template": template} if template is not None else {"template__value": value}
        return ItemInstanceFactory(
            game_object=obj,
            holder_character_sheet=self.sheet,
            held_since=timezone.now() - timedelta(days=days),
            **kwargs,
        )

    def _sacrifice(self, outcome_name: str, *items):
        with force_check_outcome(self.outcomes[outcome_name]) as capture:
            result = sacrifice_items(self.sheet, list(items))
        return result, capture


class RequestedItemSacrificeTests(RequestedItemTestBase):
    def test_a_bought_item_the_pledge_asked_for_rolls_eased_by_its_points(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        item = self._held(value=2)
        request = RequestedItemFactory(pledge=self.pledge, item_template=item.template, points=3)

        _result, capture = self._sacrifice("Success", item)

        offering = CeremonyOffering.objects.get()
        self.assertTrue(offering.counted)
        self.assertEqual(offering.pledge_details, details)
        (signal,) = offering.signals.all()
        self.assertEqual((signal.kind, signal.points), (MeaningSignalKind.REQUESTED, 3))
        self.assertEqual(signal.requested_item, request)
        self.assertIsNotNone(capture.check_type)
        # Three points ease the difficulty by thirty, never below Trivial.
        self.assertEqual(offering.difficulty_points, capture.target_difficulty)

    def test_the_same_item_not_asked_for_earns_nothing(self) -> None:
        take_pledge(self.sheet, self.pledge)
        item = self._held(value=2)

        _result, capture = self._sacrifice("Success", item)

        self.assertIsNone(capture.check_type)
        self.assertFalse(CeremonyOffering.objects.get().counted)

    def test_a_roll_a_request_eased_cannot_botch(self) -> None:
        take_pledge(self.sheet, self.pledge)
        item = self._held(value=2)
        RequestedItemFactory(pledge=self.pledge, item_template=item.template)

        self._sacrifice("Critical Failure", item)

        offering = CeremonyOffering.objects.get()
        self.assertEqual(offering.outcome_tier, self.outcomes["Failure"])
        # The being's hand stays open: a botch would have closed it for the week.
        self.assertGreater(sacrifice_slots_left(self.sheet, self.being), 0)

    def test_a_roll_with_no_request_still_botches(self) -> None:
        take_pledge(self.sheet, self.pledge)

        self._sacrifice("Critical Failure", self._carried_item())

        self.assertEqual(
            CeremonyOffering.objects.get().outcome_tier, self.outcomes["Critical Failure"]
        )
        self.assertEqual(sacrifice_slots_left(self.sheet, self.being), 0)

    def test_a_request_fills_up_to_its_quantity(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        first, second = self._held(value=2), self._held(value=2)
        RequestedItemFactory(pledge=self.pledge, item_template=first.template, quantity=1)
        second.template = first.template
        second.save(update_fields=["template"])

        self._sacrifice("Success", first)
        self._sacrifice("Success", second)

        kinds = [
            list(offering.signals.values_list("kind", flat=True))
            for offering in CeremonyOffering.objects.order_by("pk")
        ]
        self.assertEqual(kinds, [[MeaningSignalKind.REQUESTED], []])
        (line,) = request_lines(details)
        self.assertEqual((line.given, line.quantity), (1, 1))

    def test_a_facet_request_is_met_by_a_cheap_item_with_the_facet_only(self) -> None:
        take_pledge(self.sheet, self.pledge)
        wolf = FacetFactory(name="Wolf")
        RequestedItemFactory(pledge=self.pledge, item_template=None, facet=wolf, points=2)
        cheap, dear = self._held(value=3), self._held(value=500)
        ItemFacetFactory(item_instance=cheap, facet=wolf)
        ItemFacetFactory(item_instance=dear, facet=wolf)

        self._sacrifice("Success", cheap)
        self._sacrifice("Success", dear)

        counted = [o.counted for o in CeremonyOffering.objects.order_by("pk")]
        self.assertEqual(counted, [True, False])

    def test_a_request_adds_no_points_to_an_item_that_is_too_valuable(self) -> None:
        take_pledge(self.sheet, self.pledge)
        item = self._held(value=50)
        # Authored under the ceiling, then the item's template grew dear: it no longer fills it.
        RequestedItemFactory(pledge=self.pledge, item_template=item.template)

        self._sacrifice("Success", item)

        self.assertFalse(CeremonyOffering.objects.get().counted)

    def test_the_item_meaning_adds_to_the_request_for_a_history_item(self) -> None:
        take_pledge(self.sheet, self.pledge)
        item = self._carried_item(value=2, days=30)
        RequestedItemFactory(pledge=self.pledge, item_template=item.template, points=3)

        self._sacrifice("Success", item)

        kinds = {s.kind: s.points for s in OfferingSignal.objects.all()}
        self.assertEqual(
            kinds,
            {
                MeaningSignalKind.CARRIED: 1,
                MeaningSignalKind.OWN_WORK: 1,
                MeaningSignalKind.REQUESTED: 3,
            },
        )

    def test_another_pledges_request_does_not_ease_this_one(self) -> None:
        take_pledge(self.sheet, self.pledge)
        item = self._held(value=2)
        other = RequestedItemFactory(item_template=item.template)  # a different pledge
        self.assertNotEqual(other.pledge, self.pledge)

        self._sacrifice("Success", item)

        self.assertFalse(CeremonyOffering.objects.get().counted)

    def test_the_pledge_card_lists_each_request_with_the_count_given(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        item = self._held(value=2)
        RequestedItemFactory(
            pledge=self.pledge, item_template=item.template, points=3, hint="[staff-authored hint]"
        )
        RequestedItemFactory(
            pledge=None, rite=self.rite, item_template=None, facet=self.silk, points=2
        )

        before = pledge_card(details).requests
        self._sacrifice("Success", item)
        after = pledge_card(details).requests

        self.assertEqual(
            [(r.asked_for, r.given, r.quantity, r.points, r.where) for r in before],
            [
                (item.template.name, 0, 1, 3, "pledge"),
                ("any cheap item with the Silk facet", 0, 1, 2, "closing rite"),
            ],
        )
        self.assertEqual([r.given for r in after], [1, 0])
        self.assertEqual(after[0].hint, "[staff-authored hint]")


class RequestedItemAuthoringTests(RequestedItemTestBase):
    def test_a_template_above_the_value_ceiling_is_refused(self) -> None:
        dear = ItemInstanceFactory(
            template__value=get_devotion_config().requested_item_max_value + 1
        )

        with self.assertRaises(ValidationError) as refused:
            RequestedItemFactory.build(pledge=self.pledge, item_template=dear.template).clean()

        self.assertIn("item_template", refused.exception.message_dict)

    def test_points_are_limited(self) -> None:
        cheap = ItemInstanceFactory(template__value=1)
        with self.assertRaises(ValidationError) as refused:
            RequestedItemFactory.build(
                pledge=self.pledge,
                item_template=cheap.template,
                points=get_devotion_config().requested_item_max_points + 1,
            ).clean()
        self.assertIn("points", refused.exception.message_dict)

    def test_a_request_belongs_to_one_pledge_or_rite_and_asks_for_one_thing(self) -> None:
        cheap = ItemInstanceFactory(template__value=1)
        with self.assertRaises(ValidationError):
            RequestedItem(pledge=self.pledge, rite=self.rite, item_template=cheap.template).clean()
        with self.assertRaises(ValidationError):
            RequestedItem(pledge=self.pledge, item_template=cheap.template, facet=self.silk).clean()


class RiteGiftTests(RequestedItemTestBase):
    def _rite(self, *items, outcome_name: str = "Success", closing_of=None):
        with force_check_outcome(self.outcomes[outcome_name]):
            return perform_worship_rite(
                self.sheet,
                self.rite,
                scene=self.scene,
                offered_items=list(items),
                closing_of=closing_of,
            )

    def test_an_item_given_up_during_a_rite_eases_the_rite_not_a_roll_of_its_own(self) -> None:
        item = self._carried_item(days=30)  # own work 1 plus carried 1 = 2 points

        outcome = self._rite(item)

        # Two points at the config's 3 per point ease the rite's roll.
        self.assertEqual(outcome.items_ease, 6)
        self.assertEqual(outcome.items_given, (str(item),))
        offering = CeremonyOffering.objects.get()
        self.assertIsNone(offering.outcome_tier)  # no sacrifice roll of its own
        self.assertTrue(offering.counted)
        self.assertIsNotNone(ItemInstance.objects.get(pk=item.pk).destroyed_at)

    def test_an_item_with_no_meaning_is_given_up_for_nothing(self) -> None:
        item = self._held(value=2)

        outcome = self._rite(item)

        self.assertEqual(outcome.items_ease, 0)
        self.assertFalse(CeremonyOffering.objects.get().counted)

    def test_only_a_few_items_count_and_each_uses_a_weekly_slot(self) -> None:
        items = [self._carried_item(days=30) for _ in range(4)]

        gifts = read_rite_gifts(self.sheet, self.rite, items)

        self.assertEqual([g.counted for g in gifts.gifts], [True, True, True, False])
        self.assertEqual(gifts.ease, 3 * 2 * 3)
        self._rite(*items)
        self.assertEqual(sacrifice_slots_left(self.sheet, self.being), 0)

    def test_a_requested_item_lifts_a_botch_to_a_failure(self) -> None:
        item = self._held(value=2)
        RequestedItemFactory(pledge=None, rite=self.rite, item_template=item.template)

        outcome = self._rite(item, outcome_name="Critical Failure")

        self.assertEqual(outcome.outcome_name, "Failure")
        self.assertEqual(outcome.items_ease, 9)

    def test_without_a_request_the_rite_still_botches(self) -> None:
        outcome = self._rite(self._carried_item(), outcome_name="Critical Failure")

        self.assertEqual(outcome.outcome_name, "Critical Failure")

    def test_the_pledges_own_request_eases_its_closing_rite(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)
        item = self._held(value=2)
        RequestedItemFactory(pledge=self.pledge, item_template=item.template, points=3)

        with force_check_outcome(self.outcomes["Critical Failure"]):
            closed = close_pledge(self.sheet, scene=self.scene, offered_items=[item])

        self.assertEqual(closed.outcome_name, "Failure")  # lifted: it cannot botch
        (line,) = pledge_card(details).requests
        self.assertEqual(line.given, 1)


class CarriedKeepsakeAndRelicTests(RequestedItemTestBase):
    def _config(self):
        return get_devotion_config()

    def test_a_carried_keepsake_of_the_being_eases_the_call(self) -> None:
        item = self._held()
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=self.being,
        )

        worn = worn_meaning(self.sheet, self.being)

        (piece,) = worn.pieces
        self.assertEqual(piece.source, InvocationPieceSource.KEEPSAKE)
        # A keepsake of the being: 1 for the subject and 2 for the match, 3 an ease point each.
        self.assertEqual((piece.points, piece.ease), (3, 9))
        base = invocation_difficulty(self.sheet, self.being, include_worn=False).points
        eased = invocation_difficulty(self.sheet, self.being)
        self.assertEqual(eased.points, max(base - 9, 15))
        self.assertTrue(any(e.label.startswith("What you wear or carry") for e in eased.eases))

    def test_a_keepsake_still_waiting_is_listed_but_eases_nothing(self) -> None:
        item = self._held()
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=self.being,
            declared_days_ago=2,
        )

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual(worn.ease, 0)
        self.assertFalse(worn.pieces[0].counted)

    def test_a_keepsake_of_another_being_does_nothing_here(self) -> None:
        from world.worship.factories import WorshippedBeingFactory

        item = self._held()
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=WorshippedBeingFactory(),
        )

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())

    def test_a_keepsake_left_at_home_does_not_ease_the_call(self) -> None:
        item = self._held()
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=self.being,
        )
        item.game_object.db_location = self.room
        item.game_object.save(update_fields=["db_location"])

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())

    def test_the_relic_she_carries_eases_by_the_points_staff_set(self) -> None:
        relic_item = self._held()
        Relic.objects.create(being=self.being, item_instance=relic_item, invocation_points=2)

        worn = worn_meaning(self.sheet, self.being)

        (piece,) = worn.pieces
        self.assertEqual(piece.source, InvocationPieceSource.RELIC)
        self.assertEqual((piece.points, piece.ease), (2, 6))

    def test_keepsakes_and_a_relic_together_stay_within_the_cap(self) -> None:
        config = self._config()
        config.invocation_meaning_ease_max = 10
        config.save(update_fields=["invocation_meaning_ease_max"])
        relic_item = self._held()
        Relic.objects.create(being=self.being, item_instance=relic_item, invocation_points=4)
        kept = self._held()
        KeepsakeFactory(
            item_instance=kept,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=self.being,
        )

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual(worn.raw_ease, 12 + 9)
        self.assertEqual(worn.ease, 10)

    def test_a_relic_with_no_points_only_has_lore(self) -> None:
        Relic.objects.create(being=self.being, item_instance=self._held())

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())


class FacetMergeTests(RequestedItemTestBase):
    def test_a_request_for_a_merged_facet_follows_the_surviving_facet(self) -> None:
        from world.magic.services.facets import merge_facets

        winner, loser = FacetFactory(name="Kestrel"), FacetFactory(name="Kestril")
        request = RequestedItemFactory(pledge=self.pledge, item_template=None, facet=loser)

        merge_facets(winner, [loser])

        request.refresh_from_db()
        self.assertEqual(request.facet, winner)
