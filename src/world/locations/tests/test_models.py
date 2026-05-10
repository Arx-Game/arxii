from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationStatOverride


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
