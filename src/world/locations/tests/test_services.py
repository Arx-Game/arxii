from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import (
    STAT_CLAMPS,
    STAT_DEFAULTS,
    LocationParentType,
    StatKey,
)
from world.locations.models import LocationStatModifier, LocationStatOverride
from world.locations.services import effective_stat


class CascadeDefaultsTests(TestCase):
    def test_returns_default_when_no_rows(self) -> None:
        room = RoomProfileFactory().objectdb
        self.assertEqual(
            effective_stat(room, StatKey.ORDER),
            STAT_DEFAULTS[StatKey.ORDER],
        )

    def test_room_with_no_profile_returns_default(self) -> None:
        # Profile is auto-created by Evennia; manually delete to simulate
        # a room with no profile.
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        self.assertEqual(
            effective_stat(room, StatKey.CRIME),
            STAT_DEFAULTS[StatKey.CRIME],
        )

    def test_clamps_to_bounds(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        # Override well above the clamp range
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=999,
        )
        clamp_max = STAT_CLAMPS[StatKey.CRIME][1]
        self.assertEqual(
            effective_stat(profile.objectdb, StatKey.CRIME),
            clamp_max,
        )

    def test_modifier_path_clamps_to_bounds(self) -> None:
        """The cascade also clamps when no override exists and modifiers
        sum past the per-stat ceiling."""
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        # Two modifiers that together exceed the clamp ceiling.
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        clamp_max = STAT_CLAMPS[StatKey.CRIME][1]
        # 0 default + 80 + 80 = 160, clamps to 100
        self.assertEqual(
            effective_stat(profile.objectdb, StatKey.CRIME),
            clamp_max,
        )

    def test_room_with_profile_but_no_area_returns_default(self) -> None:
        """If a room has a profile but profile.area is None, the cascade
        skips area lookup and returns the per-stat default."""
        profile = RoomProfileFactory()  # area defaults to None
        self.assertIsNone(profile.area)
        self.assertEqual(
            effective_stat(profile.objectdb, StatKey.ORDER),
            STAT_DEFAULTS[StatKey.ORDER],
        )


class CascadeOverrideTests(TestCase):
    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_room_override_wins_over_area_override(self) -> None:
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=0,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 0)

    def test_more_specific_area_override_wins(self) -> None:
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=30,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=70,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 70)

    def test_override_anywhere_hides_modifiers(self) -> None:
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=50,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 10)

    def test_room_override_hides_area_modifiers(self) -> None:
        """A room-level Override short-circuits even modifiers stacked
        higher in the chain."""
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=50,
        )
        LocationStatOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=0,
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 0)


class CascadeModifierStackingTests(TestCase):
    def setUp(self) -> None:
        self.region = AreaFactory(level=AreaLevel.REGION)
        self.city = AreaFactory(level=AreaLevel.CITY, parent=self.region)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_modifiers_at_multiple_levels_sum(self) -> None:
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.region,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=20,
        )
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=5,
        )
        # 0 default + 10 + 20 + 5 = 35
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 35)

    def test_decayed_modifier_contributes_zero(self) -> None:
        # value 10, decay -1/day, applied 30 days ago → 0
        LocationStatModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        self.assertEqual(effective_stat(self.room, StatKey.CRIME), 0)
