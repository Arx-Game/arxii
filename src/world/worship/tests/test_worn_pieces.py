"""What she wears counts with her gods (#4520, #4462 section 6.4, folds #4333 slice 8).

Example numbers (staff tune them): a worn piece's meaning points, capped at 8, times the
favored facet's ease per point (2 here); the earning bonus is 1% a point; three pieces
count and all worn ease together is capped at 40. A bought piece with no other history
adds nothing, whatever it cost or how many favored facets it carries.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.constants import BodyRegion, EquipmentLayer, MeaningSignalKind
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
    meaningful_item_for,
)
from world.items.services.equip import unequip_item
from world.items.services.facets import remove_facet_from_item
from world.items.services.meaning import item_meaning
from world.magic.constants import GainSource
from world.magic.factories import FacetFactory, ResonanceFactory
from world.magic.models import ResonanceGrant
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    DevotionConfigFactory,
    DevotionStandingFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import earning_rate
from world.worship.invocation_services import (
    invocation_difficulty,
    invocation_options,
    invoke_favor,
)
from world.worship.models import InvocationPiece
from world.worship.pledge_services import earning_rate_breakdown
from world.worship.sacrifice_services import sacrifice_difficulty
from world.worship.worn_services import worn_meaning

_REGIONS = (
    BodyRegion.TORSO,
    BodyRegion.HEAD,
    BodyRegion.NECK,
    BodyRegion.WAIST,
    BodyRegion.FEET,
)


def _stamp_grant(sheet, item_facet, resonance, amount: int) -> ResonanceGrant:
    """A trickle grant the item's facet fed ``sheet``: the record the signal reads."""
    return ResonanceGrant.objects.create(
        character_sheet=sheet,
        resonance=resonance,
        amount=amount,
        source=GainSource.OUTFIT_TRICKLE,
        outfit_item_facet=item_facet,
    )


class WornPiecesTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = DevotionConfigFactory(invocation_check_type=CheckTypeFactory())
        cls.being = WorshippedBeingFactory(name="Highwind")
        cls.kestrel = FacetFactory(name="Kestrel")
        cls.iron = FacetFactory(name="Iron")
        cls.kestrel_row = BeingFacetFactory(
            being=cls.being, facet=cls.kestrel, invocation_ease_points=2, earning_bonus_percent=1
        )

    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="Linnet")
        self.sheet = CharacterSheetFactory(character=self.character)
        self._slots = iter(_REGIONS)

    def wear(self, item, *facets):
        """Put the item on a free body region and attach ``facets`` to it."""
        region = next(self._slots)
        TemplateSlotFactory(
            template=item.template, body_region=region, equipment_layer=EquipmentLayer.BASE
        )
        EquippedItemFactory(
            character=self.sheet,
            item_instance=item,
            body_region=region,
            equipment_layer=EquipmentLayer.BASE,
        )
        for facet in facets:
            ItemFacetFactory(item_instance=item, facet=facet)
        self.character.equipped_items.invalidate()
        return item

    def made_piece(self, *facets, days: int = 30, **kwargs):
        """A piece she made and has carried ``days`` days, worn: own work plus carried."""
        item = meaningful_item_for(self.sheet, days=days, **kwargs)
        return self.wear(item, *facets)


class WornMeaningTests(WornPiecesTestBase):
    def test_a_worn_piece_with_history_and_a_favored_facet_eases_by_points_times_rate(self) -> None:
        coat = self.made_piece(self.kestrel)

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual([p.item for p in worn.counted], [coat])
        self.assertEqual((worn.counted[0].points, worn.counted[0].ease_per_point), (2, 2))
        self.assertEqual(worn.ease, 4)
        self.assertEqual(worn.earning_percent, 2)

    def test_a_bought_piece_with_the_favored_facet_adds_nothing_however_much_it_cost(self) -> None:
        template = ItemTemplateFactory(value=9999)
        self.wear(
            ItemInstanceFactory(
                holder_character_sheet=self.sheet,
                template=template,
                held_since=timezone.now() - timedelta(days=400),
            ),
            self.kestrel,
        )

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual(len(worn.pieces), 1)
        self.assertFalse(worn.pieces[0].counted)
        self.assertEqual((worn.ease, worn.earning_percent), (0, 0))

    def test_a_piece_without_a_favored_facet_is_not_read(self) -> None:
        self.made_piece(self.iron)

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())

    def test_a_piece_not_worn_is_not_read(self) -> None:
        item = meaningful_item_for(self.sheet)
        ItemFacetFactory(item_instance=item, facet=self.kestrel)

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())

    def test_only_the_highest_meaning_pieces_count_up_to_the_limit(self) -> None:
        old = self.made_piece(self.kestrel, days=400)  # carried 3 + own work 1
        mid = self.made_piece(self.kestrel, days=110)  # carried 2 + own work 1
        low_one = self.made_piece(self.kestrel, days=20)  # 2
        low_two = self.made_piece(self.kestrel, days=20)  # 2

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual([p.item for p in worn.counted][:2], [old, mid])
        self.assertEqual(len(worn.counted), 3)
        uncounted = [p.item for p in worn.pieces if not p.counted]
        self.assertEqual(len(uncounted), 1)
        self.assertIn(uncounted[0], {low_one, low_two})
        self.assertEqual(worn.ease, (4 + 3 + 2) * 2)

    def test_one_piece_counts_at_most_the_worn_item_cap_in_points(self) -> None:
        self.config.worn_item_max_points = 3
        self.config.save(update_fields=["worn_item_max_points"])
        self.made_piece(self.kestrel, days=400)

        self.assertEqual(worn_meaning(self.sheet, self.being).counted[0].points, 3)

    def test_the_total_ease_is_capped(self) -> None:
        self.config.invocation_meaning_ease_max = 5
        self.config.save(update_fields=["invocation_meaning_ease_max"])
        self.made_piece(self.kestrel, days=400)

        worn = worn_meaning(self.sheet, self.being)

        self.assertEqual((worn.raw_ease, worn.ease), (8, 5))

    def test_the_facet_that_eases_most_is_used_when_a_piece_carries_several(self) -> None:
        BeingFacetFactory(
            being=self.being, facet=self.iron, invocation_ease_points=5, earning_bonus_percent=3
        )
        self.made_piece(self.kestrel, self.iron)

        piece = worn_meaning(self.sheet, self.being).counted[0]

        self.assertEqual((piece.facet_name, piece.ease_per_point), ("Iron", 5))
        self.assertEqual(piece.earning_percent, 6)

    def test_a_facet_stripped_from_the_piece_stops_counting(self) -> None:
        piece = self.made_piece(self.kestrel)
        row = piece.item_facets.get()
        remove_facet_from_item(item_facet=row)
        self.character.equipped_items.invalidate()

        self.assertEqual(worn_meaning(self.sheet, self.being).pieces, ())

    def test_giving_the_piece_up_removes_its_ease(self) -> None:
        piece = self.made_piece(self.kestrel)
        self.assertEqual(worn_meaning(self.sheet, self.being).ease, 4)

        unequip_item(equipped_item=piece.equipped_slots.get())

        self.assertEqual(worn_meaning(self.sheet, self.being).ease, 0)

    def test_a_being_that_favors_no_facet_reads_nothing(self) -> None:
        self.made_piece(self.kestrel)

        self.assertEqual(worn_meaning(self.sheet, WorshippedBeingFactory()).pieces, ())


class ResonanceFedTests(WornPiecesTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.favored = ResonanceFactory(name="Gale")
        cls.associated = ResonanceFactory(name="Drift")
        cls.unlisted = ResonanceFactory(name="Hearth")
        BeingResonanceFactory(
            being=cls.being, resonance=cls.favored, tier=BeingResonanceTier.FAVORED
        )
        BeingResonanceFactory(
            being=cls.being, resonance=cls.associated, tier=BeingResonanceTier.ASSOCIATED
        )

    def _kinds(self, item) -> dict[str, int]:
        meaning = item_meaning(item, self.sheet, config=self.config, being=self.being)
        return {signal.kind: signal.points for signal in meaning.signals}

    def test_resonance_fed_in_a_favored_resonance_doubles(self) -> None:
        item = self.made_piece(self.kestrel)
        _stamp_grant(self.sheet, item.item_facets.get(), self.favored, 25)

        self.assertEqual(
            self._kinds(item)[MeaningSignalKind.RESONANCE_FED], 3
        )  # 2 x 2, capped at 3

    def test_an_associated_resonance_pays_once_and_an_unlisted_one_nothing(self) -> None:
        item = self.made_piece(self.kestrel)
        row = item.item_facets.get()
        _stamp_grant(self.sheet, row, self.associated, 20)
        _stamp_grant(self.sheet, row, self.unlisted, 90)

        self.assertEqual(self._kinds(item)[MeaningSignalKind.RESONANCE_FED], 2)

    def test_it_is_left_out_when_no_being_is_given(self) -> None:
        item = self.made_piece(self.kestrel)
        _stamp_grant(self.sheet, item.item_facets.get(), self.favored, 25)

        meaning = item_meaning(item, self.sheet, config=self.config)

        self.assertNotIn(MeaningSignalKind.RESONANCE_FED, {s.kind for s in meaning.signals})

    def test_a_bought_piece_worn_for_months_still_reads_zero(self) -> None:
        bought = self.wear(
            ItemInstanceFactory(
                holder_character_sheet=self.sheet,
                held_since=timezone.now() - timedelta(days=300),
            ),
            self.kestrel,
        )
        _stamp_grant(self.sheet, bought.item_facets.get(), self.favored, 500)

        meaning = item_meaning(bought, self.sheet, config=self.config, being=self.being)

        self.assertEqual(meaning.points, 0)

    def test_grants_to_a_previous_holder_or_before_the_piece_was_held_score_nothing(self) -> None:
        item = self.made_piece(self.kestrel)
        row = item.item_facets.get()
        _stamp_grant(CharacterSheetFactory(primary_persona=False), row, self.favored, 100)
        grant = _stamp_grant(self.sheet, row, self.favored, 100)
        grant.granted_at = item.held_since - timedelta(days=1)
        grant.save(update_fields=["granted_at"])

        self.assertNotIn(MeaningSignalKind.RESONANCE_FED, self._kinds(item))

    def test_a_removed_facets_grants_do_not_count(self) -> None:
        item = self.made_piece(self.kestrel)
        row = item.item_facets.get()
        _stamp_grant(self.sheet, row, self.favored, 100)
        remove_facet_from_item(item_facet=row)

        self.assertNotIn(MeaningSignalKind.RESONANCE_FED, self._kinds(item))

    def test_it_is_capped(self) -> None:
        item = self.made_piece(self.kestrel)
        _stamp_grant(self.sheet, item.item_facets.get(), self.favored, 900)

        self.assertEqual(self._kinds(item)[MeaningSignalKind.RESONANCE_FED], 3)

    def test_it_raises_what_a_worn_piece_eases(self) -> None:
        item = self.made_piece(self.kestrel)
        before = worn_meaning(self.sheet, self.being).ease
        _stamp_grant(self.sheet, item.item_facets.get(), self.favored, 30)

        self.assertEqual(worn_meaning(self.sheet, self.being).ease, before + 3 * 2)


class InvocationUsesWornPiecesTests(WornPiecesTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.standing = DevotionStandingFactory(
            character_sheet=self.sheet, being=self.being, favor=10
        )
        self.base = DIFFICULTY_VALUES[DifficultyChoice.DAUNTING]

    def test_wearing_the_piece_eases_the_difficulty_once_and_labels_it(self) -> None:
        self.made_piece(self.kestrel, days=400, template__name="riding coat")

        difficulty = invocation_difficulty(self.sheet, self.being)

        worn = [ease for ease in difficulty.eases if ease.label.startswith("What you wear")]
        self.assertEqual([ease.points for ease in worn], [8])
        self.assertIn("riding coat", worn[0].label)
        self.assertEqual(difficulty.points, self.base - 8)

    def test_nothing_worn_adds_no_ease_line(self) -> None:
        difficulty = invocation_difficulty(self.sheet, self.being)

        self.assertFalse([e for e in difficulty.eases if e.label.startswith("What you wear")])
        self.assertEqual(difficulty.points, self.base)

    def test_a_sacrifice_does_not_read_what_she_wears(self) -> None:
        self.made_piece(self.kestrel, days=400)

        self.assertEqual(sacrifice_difficulty(self.sheet, self.being, 0), self.base)

    def test_the_picker_carries_the_worn_pieces_with_the_difficulty(self) -> None:
        self.made_piece(self.kestrel)

        (option,) = invocation_options(self.sheet)

        self.assertEqual(option.worn.ease, 4)
        self.assertEqual(option.difficulty.points, self.base - 4)

    def test_the_invocation_records_the_pieces_that_counted_with_their_signals(self) -> None:
        self.made_piece(self.kestrel, days=400, template__name="riding coat")
        with force_check_outcome(CheckOutcomeFactory(name="Success", success_level=1)) as capture:
            outcome = invoke_favor(self.sheet, self.being, actor_name="Linnet")

        # The roll itself is eased once, by the same 8 the record shows.
        self.assertEqual(capture.target_difficulty, self.base - 8)
        invocation = outcome.invocation
        self.assertEqual(invocation.worn_ease, 8)
        (piece,) = InvocationPiece.objects.filter(invocation=invocation)
        self.assertEqual(
            (piece.item_name, piece.facet_name, piece.points, piece.ease),
            ("riding coat", "Kestrel", 4, 8),
        )
        self.assertEqual(
            {s.kind: s.points for s in piece.signals.all()},
            {MeaningSignalKind.CARRIED: 3, MeaningSignalKind.OWN_WORK: 1},
        )
        self.assertEqual(outcome.difficulty.points, self.base - 8)

    def test_the_snapshot_survives_the_piece_changing_afterwards(self) -> None:
        piece = self.made_piece(self.kestrel, days=400)
        with force_check_outcome(CheckOutcomeFactory(name="Success", success_level=1)):
            outcome = invoke_favor(self.sheet, self.being, actor_name="Linnet")
        piece.delete()

        self.assertEqual(outcome.invocation.pieces.count(), 1)

    def test_the_earning_rate_rises_while_worn_and_shows_in_the_breakdown(self) -> None:
        self.assertEqual(earning_rate(self.sheet, self.being), 100)
        self.made_piece(self.kestrel, days=400)

        self.assertEqual(earning_rate(self.sheet, self.being), 104)
        breakdown = earning_rate_breakdown(self.sheet, self.being)
        self.assertEqual((breakdown.worn_bonus, breakdown.total), (4, 104))


class InvocationDetailAdminTests(WornPiecesTestBase):
    """The GM's invocation detail: the pieces that counted, their signals, the favored
    facet that made each count and the ease it gave (#4520)."""

    def test_the_invocation_page_lists_each_counted_piece_with_its_signals(self) -> None:
        self.made_piece(self.kestrel, days=400, template__name="riding coat")
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=10)
        with force_check_outcome(CheckOutcomeFactory(name="Success", success_level=1)):
            outcome = invoke_favor(self.sheet, self.being, actor_name="Linnet")
        staff = AccountDB.objects.create_superuser("gmdetail", "gm@example.com", "pw-1234567")
        self.client.force_login(staff)

        response = self.client.get(
            reverse("admin:arxii_favorinvocation_change", args=(outcome.invocation.pk,))
        )

        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("riding coat", body)
        self.assertIn("Kestrel (the gate; ease 2 per point)", body)
        self.assertIn("held 400 days", body)
        self.assertIn("made by the holder", body)
        self.assertIn("4 points, eased 8 before the cap; eased 8 on the roll", body)
        self.assertNotIn("value", body.split("Worn pieces that counted")[-1].lower())

    def test_an_invocation_with_nothing_counted_says_so(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=10)
        with force_check_outcome(CheckOutcomeFactory(name="Success", success_level=1)):
            outcome = invoke_favor(self.sheet, self.being, actor_name="Linnet")
        staff = AccountDB.objects.create_superuser("gmdetail2", "gm2@example.com", "pw-1234567")
        self.client.force_login(staff)

        response = self.client.get(
            reverse("admin:arxii_favorinvocation_change", args=(outcome.invocation.pk,))
        )

        self.assertContains(response, "No worn piece counted on this invocation.")
