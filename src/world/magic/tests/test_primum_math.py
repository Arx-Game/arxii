"""The pure Primum reads (#5125): steps, a place's amount, the power curve, the split.

These are unit tests because maths and a clock cannot be reached by a journey; casting is
wired to them (and journey-tested) in a later task.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemSubstanceFactory
from world.locations.constants import KeyType, LocationParentType, StatKey
from world.locations.factories import LocationValueModifierFactory
from world.magic.constants import (
    STARTER_POWER_CURVE,
    STARTER_PRIMUM_STEPS,
    GiftKind,
    PrimumLineKind,
    SubstanceDirection,
    SubstanceRelationKind,
)
from world.magic.factories import (
    GiftFactory,
    PlacePrimumFactory,
    PrimumCallUpFactory,
    PrimumSightingFactory,
    SubstanceFactory,
    SubstanceRelationFactory,
    seed_primum_tuning,
)
from world.magic.services.primum import (
    apportion_power,
    cast_points,
    gift_substance,
    place_amount,
    points_to_power,
    room_substance_amounts,
    step_for,
    total_points,
)
from world.magic.services.primum_perception import perceived_substance_ids
from world.magic.types.primum import SourcePoints

TRACE_STARTS_AT = STARTER_PRIMUM_STEPS[0][2]
TRACE_NAME = STARTER_PRIMUM_STEPS[0][1]
SOME_NAME = STARTER_PRIMUM_STEPS[1][1]
SOME_STARTS_AT = STARTER_PRIMUM_STEPS[1][2]
SOME_POINTS = STARTER_PRIMUM_STEPS[1][3]
TRACE_POINTS = STARTER_PRIMUM_STEPS[0][3]
HIGHEST_STARTS_AT = STARTER_PRIMUM_STEPS[-1][2]


def _room():
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _lines(*points: int) -> list[SourcePoints]:
    return [
        SourcePoints(kind=PrimumLineKind.PLACE, label=str(i), points=p, substance_id=i)
        for i, p in enumerate(points)
    ]


class StepAndPlaceAmountTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_primum_tuning()
        cls.fire = SubstanceFactory(name="fire")
        cls.shadow = SubstanceFactory(
            name="shadow", stat_key=StatKey.LIGHTING, direction=SubstanceDirection.FALLING
        )
        cls.room = _room()
        cls.profile = cls.room.room_profile

    def test_step_for_picks_highest_reached_step(self) -> None:
        self.assertIsNone(step_for(TRACE_STARTS_AT - 1))
        self.assertEqual(step_for(TRACE_STARTS_AT).name, TRACE_NAME)
        self.assertEqual(step_for(SOME_STARTS_AT - 1).name, TRACE_NAME)
        self.assertEqual(step_for(SOME_STARTS_AT).name, SOME_NAME)
        self.assertEqual(step_for(HIGHEST_STARTS_AT * 50).rank, len(STARTER_PRIMUM_STEPS))

    def test_step_for_with_no_rows_is_none(self) -> None:
        from world.magic.models import PrimumStep

        PrimumStep.objects.all().delete()
        self.assertIsNone(step_for(500))

    def test_place_amount_adds_call_ups_and_extra(self) -> None:
        PlacePrimumFactory(
            room_profile=self.profile, substance=self.fire, capacity=20, stored_amount=7
        )
        PrimumCallUpFactory(room_profile=self.profile, substance=self.fire, amount_added=5)
        self.assertEqual(place_amount(self.room, self.fire), 12)
        self.assertEqual(place_amount(self.room, self.fire, extra=3), 15)
        self.assertEqual(place_amount(self.room, self.shadow), 0)
        self.assertEqual(room_substance_amounts(self.room), {self.fire.pk: 12})

    def test_place_amount_floors_at_trace_when_ordinary_condition_leans_the_way_and_not_against(
        self,
    ) -> None:
        LocationValueModifierFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.profile,
            key_type=KeyType.STAT,
            stat_key=StatKey.LIGHTING,
            value=-1,
        )
        self.assertEqual(place_amount(self.room, self.shadow), TRACE_STARTS_AT)
        self.assertEqual(room_substance_amounts(self.room), {self.shadow.pk: TRACE_STARTS_AT})
        bright = _room()
        LocationValueModifierFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=bright.room_profile,
            key_type=KeyType.STAT,
            stat_key=StatKey.LIGHTING,
            value=1,
        )
        self.assertEqual(place_amount(bright, self.shadow), 0)
        self.assertEqual(room_substance_amounts(bright), {})

    def test_dead_finite_place_reads_zero_and_no_negative_stock_when_clock_is_early(self) -> None:
        PlacePrimumFactory(
            room_profile=self.profile,
            substance=self.fire,
            capacity=20,
            stored_amount=0,
            is_finite=True,
        )
        self.assertEqual(place_amount(self.room, self.fire), 0)
        self.assertEqual(room_substance_amounts(self.room), {})
        refilling = _room()
        PlacePrimumFactory(
            room_profile=refilling.room_profile,
            substance=self.fire,
            capacity=20,
            stored_amount=4,
            refill_per_day=3,
        )
        early = timezone.now() - timedelta(days=30)
        self.assertEqual(place_amount(refilling, self.fire, now=early), 4)


class PowerCurveTests(TestCase):
    def test_points_to_power_interpolates_caps_and_mirrors(self) -> None:
        curve = list(STARTER_POWER_CURVE)
        self.assertEqual(points_to_power(3, curve, cap=12), 3)
        self.assertEqual(points_to_power(-3, curve, cap=12), -3)
        self.assertEqual(points_to_power(500, curve, cap=12), STARTER_POWER_CURVE[-1][1])
        self.assertEqual(points_to_power(500, curve, cap=5), 5)
        self.assertEqual(points_to_power(5, [], cap=12), 0)

    def test_apportion_sums_exactly_and_is_zero_safe(self) -> None:
        shares = apportion_power(_lines(7, 4, 4), 10, positive_power=10)
        self.assertEqual(sum(shares), 10)
        self.assertEqual(len(shares), 3)
        self.assertEqual(apportion_power(_lines(0, 0), 0, positive_power=0), [0, 0])
        self.assertEqual(apportion_power([], 0, positive_power=0), [])
        self.assertEqual(total_points(_lines(7, -2)), 5)

    def test_apportion_keeps_each_lines_sign_when_one_opposes(self) -> None:
        curve = list(STARTER_POWER_CURVE)
        lines = _lines(8, -4)
        positive = points_to_power(8, curve, cap=12)
        total = points_to_power(total_points(lines), curve, cap=12)
        self.assertEqual(apportion_power(lines, total, positive_power=positive), [6, -2])

    def test_apportion_net_negative_keeps_signs_and_sums_exactly(self) -> None:
        curve = list(STARTER_POWER_CURVE)
        lines = _lines(2, -8)
        positive = points_to_power(2, curve, cap=12)
        total = points_to_power(total_points(lines), curve, cap=12)
        self.assertEqual(total, -5)
        shares = apportion_power(lines, total, positive_power=positive)
        self.assertEqual(sum(shares), total)
        self.assertGreaterEqual(shares[0], 0)
        self.assertLessEqual(shares[1], 0)


class GiftSubstanceAndCastPointsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_primum_tuning()
        cls.fire = SubstanceFactory(name="fire")
        cls.ice = SubstanceFactory(name="ice")
        cls.ember = SubstanceFactory(name="ember")
        cls.void = SubstanceFactory(name="void")
        SubstanceRelationFactory(
            substance_a=cls.fire, substance_b=cls.ice, kind=SubstanceRelationKind.OPPOSED
        )
        SubstanceRelationFactory(
            substance_a=cls.fire, substance_b=cls.ember, kind=SubstanceRelationKind.RELATED
        )
        cls.gift = GiftFactory(name="Pyre", substance=cls.fire)
        cls.child = GiftFactory(name="Pyre kind", parent=cls.gift)
        cls.minor = GiftFactory(name="Odd job", kind=GiftKind.MINOR, parent=cls.gift)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.room = _room()
        cls.profile = cls.room.room_profile

    def test_gift_substance_is_own_else_nearest_ancestors_and_none_for_minor(self) -> None:
        self.assertEqual(gift_substance(self.gift), self.fire)
        self.assertEqual(gift_substance(self.child), self.fire)
        self.assertIsNone(gift_substance(self.minor))
        self.assertIsNone(gift_substance(None))

    def test_cast_points_signs_labels_and_hides_an_unperceived_opposition(self) -> None:
        for substance, amount in ((self.fire, 12), (self.ember, 5), (self.ice, 40)):
            PlacePrimumFactory(
                room_profile=self.profile, substance=substance, capacity=100, stored_amount=amount
            )
        PlacePrimumFactory(
            room_profile=self.profile, substance=self.void, capacity=100, stored_amount=50
        )
        item = ItemSubstanceFactory(
            item_instance=ItemInstanceFactory(custom_name="Ash brand"),
            substance=self.fire,
            step=step_for(TRACE_STARTS_AT),
        )
        EquippedItemFactory(
            character=self.sheet,
            item_instance=item.item_instance,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.OVER,
        )
        lines = cast_points(self.character, self.child, self.room)
        by_label = {line.label: line for line in lines}
        self.assertEqual(by_label["Surroundings: fire"].points, SOME_POINTS)
        self.assertEqual(by_label["Surroundings: ember"].points, TRACE_POINTS // 2)  # 50% share
        self.assertEqual(
            by_label["Something here works against your fire"].points, -STARTER_PRIMUM_STEPS[2][3]
        )
        self.assertEqual(by_label["Ash brand (fire)"].points, TRACE_POINTS)
        self.assertEqual(by_label["Ash brand (fire)"].kind, PrimumLineKind.ITEM)
        self.assertEqual(by_label["Ash brand (fire)"].item_id, item.item_instance_id)
        self.assertEqual(len(lines), 4, "an unrelated substance adds no line")
        PrimumSightingFactory(
            character_sheet=self.sheet, room_profile=self.profile, substance=self.ice
        )
        self.assertIn(self.ice.pk, perceived_substance_ids(self.character, self.room))
        labels = {line.label for line in cast_points(self.character, self.child, self.room)}
        self.assertIn("Ice here works against your fire", labels)
        extra = cast_points(self.character, self.gift, None, extra_place_amount=TRACE_STARTS_AT)
        self.assertEqual([line.points for line in extra if line.kind == PrimumLineKind.PLACE], [2])
        self.assertEqual(cast_points(self.character, self.minor, self.room), [])
