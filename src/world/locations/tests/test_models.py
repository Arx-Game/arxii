from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationStatModifier, LocationStatOverride


class LocationStatOverrideTests(TestCase):
    def test_create_with_area(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        row = LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        self.assertEqual(row.area, area)
        self.assertIsNone(row.room_profile)

    def test_create_with_room(self) -> None:
        room = RoomProfileFactory()
        row = LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=-2,
        )
        self.assertEqual(row.room_profile, room)
        self.assertIsNone(row.area)

    def test_clean_rejects_both_fks(self) -> None:
        area = AreaFactory()
        room = RoomProfileFactory()
        row = LocationStatOverride(
            parent_type=LocationParentType.AREA,
            area=area,
            room_profile=room,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_fk(self) -> None:
        row = LocationStatOverride(
            parent_type=LocationParentType.AREA,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_unique_override_per_area_stat(self) -> None:
        area = AreaFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationStatOverride.objects.create(
                parent_type=LocationParentType.AREA,
                area=area,
                stat_key=StatKey.CRIME,
                value=20,
            )

    def test_unique_override_per_room_stat(self) -> None:
        room = RoomProfileFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=-2,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationStatOverride.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=room,
                stat_key=StatKey.LIGHTING,
                value=2,
            )

    def test_different_stats_on_same_area_ok(self) -> None:
        area = AreaFactory()
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.ORDER,
            value=80,
        )
        self.assertEqual(
            LocationStatOverride.objects.filter(area=area).count(),
            2,
        )


class LocationStatModifierCurrentValueTests(TestCase):
    def test_change_per_day_zero_is_static(self) -> None:
        area = AreaFactory()
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=0,
            applied_at=timezone.now() - timedelta(days=10),
        )
        self.assertEqual(mod.current_value(), 20)

    def test_decay_positive_value(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=5)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=-1,
            applied_at=anchor,
        )
        # 20 + (-1 * 5) = 15
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=5)), 15)

    def test_decayed_past_zero_returns_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=30)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=anchor,
        )
        # 10 + (-1 * 30) = -20 -> clamped to 0
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=30)), 0)

    def test_growth_positive_value(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=10)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=2,
            applied_at=anchor,
        )
        # 5 + (2 * 10) = 25 (unbounded; cascade resolver clamps)
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=10)), 25)

    def test_negative_value_growing_toward_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=3)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=-10,
            change_per_day=2,
            applied_at=anchor,
        )
        # -10 + (2 * 3) = -4 (still negative, returned as-is)
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=3)), -4)

    def test_negative_value_passing_zero_returns_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=10)
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=-10,
            change_per_day=2,
            applied_at=anchor,
        )
        # -10 + (2 * 10) = 10 -> original sign was negative, crossed -> 0
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=10)), 0)

    def test_zero_value_is_static_regardless_of_change_per_day(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(days=10)
        # value=0 with positive change_per_day shouldn't grow
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=0,
            change_per_day=2,
            applied_at=anchor,
        )
        self.assertEqual(mod.current_value(now=anchor + timedelta(days=10)), 0)

    def test_partial_day_truncates_toward_zero(self) -> None:
        area = AreaFactory()
        anchor = timezone.now() - timedelta(hours=12)  # half a day
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-2,
            applied_at=anchor,
        )
        # int(-2 * 0.5) = int(-1.0) = -1; 10 + (-1) = 9
        # Note: int truncates toward zero, so on a half-day at -2/day,
        # we get -1, not -2 (which a math.floor would give).
        self.assertEqual(mod.current_value(now=anchor + timedelta(hours=12)), 9)


class LocationStatModifierStackingTests(TestCase):
    def test_multiple_modifiers_on_same_area_and_stat_allowed(self) -> None:
        area = AreaFactory()
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            source="rebellion",
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            source="market_day",
        )
        self.assertEqual(
            LocationStatModifier.objects.filter(area=area, stat_key=StatKey.CRIME).count(),
            2,
        )

    def test_create_with_room_profile(self) -> None:
        room = RoomProfileFactory()
        mod = LocationStatModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=1,
        )
        self.assertEqual(mod.room_profile, room)
        self.assertIsNone(mod.area)
