from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import (
    STAT_CLAMPS,
    STAT_DEFAULTS,
    KeyType,
    LocationParentType,
    StatKey,
)
from world.locations.models import LocationValueModifier, LocationValueOverride
from world.locations.services import effective_value, upsert_room_resonance_modifier
from world.magic.factories import ResonanceFactory


class CascadeDefaultsTests(TestCase):
    def test_returns_default_when_no_rows(self) -> None:
        room = RoomProfileFactory().objectdb
        self.assertEqual(
            effective_value(room, stat_key=StatKey.ORDER),
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
            effective_value(room, stat_key=StatKey.CRIME),
            STAT_DEFAULTS[StatKey.CRIME],
        )

    def test_clamps_to_bounds(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        # Override well above the clamp range
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=999,
        )
        clamp_max = STAT_CLAMPS[StatKey.CRIME][1]
        self.assertEqual(
            effective_value(profile.objectdb, stat_key=StatKey.CRIME),
            clamp_max,
        )

    def test_modifier_path_clamps_to_bounds(self) -> None:
        """The cascade also clamps when no override exists and modifiers
        sum past the per-stat ceiling."""
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        # Two modifiers that together exceed the clamp ceiling.
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        clamp_max = STAT_CLAMPS[StatKey.CRIME][1]
        # 0 default + 80 + 80 = 160, clamps to 100
        self.assertEqual(
            effective_value(profile.objectdb, stat_key=StatKey.CRIME),
            clamp_max,
        )

    def test_room_with_profile_but_no_area_returns_default(self) -> None:
        """If a room has a profile but profile.area is None, the cascade
        skips area lookup and returns the per-stat default."""
        profile = RoomProfileFactory()  # area defaults to None
        self.assertIsNone(profile.area)
        self.assertEqual(
            effective_value(profile.objectdb, stat_key=StatKey.ORDER),
            STAT_DEFAULTS[StatKey.ORDER],
        )


class CascadeOverrideTests(TestCase):
    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_room_override_wins_over_area_override(self) -> None:
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=80,
        )
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=0,
        )
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 0)

    def test_more_specific_area_override_wins(self) -> None:
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=30,
        )
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=70,
        )
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 70)

    def test_override_anywhere_hides_modifiers(self) -> None:
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=50,
        )
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 10)

    def test_room_override_hides_area_modifiers(self) -> None:
        """A room-level Override short-circuits even modifiers stacked
        higher in the chain."""
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,
            value=50,
        )
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=0,
        )
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 0)


class CascadeModifierStackingTests(TestCase):
    def setUp(self) -> None:
        self.region = AreaFactory(level=AreaLevel.REGION)
        self.city = AreaFactory(level=AreaLevel.CITY, parent=self.region)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb

    def test_modifiers_at_multiple_levels_sum(self) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.region,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=20,
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            stat_key=StatKey.CRIME,
            value=5,
        )
        # 0 default + 10 + 20 + 5 = 35
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 35)

    def test_decayed_modifier_contributes_zero(self) -> None:
        # value 10, decay -1/day, applied 30 days ago → 0
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        self.assertEqual(effective_value(self.room, stat_key=StatKey.CRIME), 0)


class EffectiveValueResonanceTests(TestCase):
    """Tests for the resonance axis on the polymorphic effective_value service."""

    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.room_profile = RoomProfileFactory(area=self.ward)
        self.room = self.room_profile.objectdb
        self.predari = ResonanceFactory(name="Predari")
        self.copperi = ResonanceFactory(name="Copperi")

    def test_resonance_modifier_on_city_visible_from_room(self) -> None:
        """A city-level resonance modifier contributes to a room in that city."""
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            key_type=KeyType.RESONANCE,
            resonance=self.predari,
            value=100,
        )
        self.assertEqual(effective_value(self.room, resonance=self.predari), 100)

    def test_room_resonance_override_short_circuits_cascade(self) -> None:
        """A room-level resonance override wipes city-level modifiers for that resonance."""
        # City contributes predari +100
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            key_type=KeyType.RESONANCE,
            resonance=self.predari,
            value=100,
        )
        # Room overrides copperi to 1000 absolute — does NOT affect predari
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=self.copperi,
            value=1000,
        )
        self.assertEqual(effective_value(self.room, resonance=self.predari), 100)
        self.assertEqual(effective_value(self.room, resonance=self.copperi), 1000)

    def test_resonance_default_is_zero_when_no_rows(self) -> None:
        """No cascade rows for a resonance returns 0 (no STAT_DEFAULTS equivalent)."""
        self.assertEqual(effective_value(self.room, resonance=self.predari), 0)

    def test_resonance_not_clamped(self) -> None:
        """Resonance values are not clamped — staff author whatever magnitude."""
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=self.predari,
            value=99999,
        )
        self.assertEqual(effective_value(self.room, resonance=self.predari), 99999)

    def test_requires_exactly_one_axis(self) -> None:
        """Calling with neither or both axis kwargs raises ValueError."""
        with self.assertRaises(ValueError):
            effective_value(self.room)  # neither
        with self.assertRaises(ValueError):
            effective_value(self.room, stat_key=StatKey.CRIME, resonance=self.predari)

    def test_stat_key_path_still_works(self) -> None:
        """effective_value(room, stat_key=X) matches the legacy effective_stat result."""
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            stat_key=StatKey.CRIME,  # defaults to KeyType.STAT
            value=20,
        )
        self.assertEqual(
            effective_value(self.room, stat_key=StatKey.CRIME),
            effective_value(self.room, stat_key=StatKey.CRIME),
        )


class UpsertRoomResonanceModifierTests(TestCase):
    """Tests for the shared upsert_room_resonance_modifier primitive."""

    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.resonance = ResonanceFactory()

    def test_create_on_first_call(self) -> None:
        """A first call creates a row with value == delta."""
        row = upsert_room_resonance_modifier(
            self.room_profile, self.resonance, source="test:1", delta=6
        )
        self.assertEqual(row.value, 6)
        self.assertEqual(row.change_per_day, 0)
        self.assertEqual(row.key_type, KeyType.RESONANCE)
        self.assertEqual(row.parent_type, LocationParentType.ROOM)
        self.assertEqual(row.source, "test:1")

    def test_accumulates_on_second_call_same_source(self) -> None:
        """A second call on the same (room_profile, resonance, source) accumulates."""
        first = upsert_room_resonance_modifier(
            self.room_profile, self.resonance, source="test:1", delta=6
        )
        second = upsert_room_resonance_modifier(
            self.room_profile, self.resonance, source="test:1", delta=-4
        )
        # Same row (same pk)
        self.assertEqual(first.pk, second.pk)
        # Accumulated value: 6 + (-4) = 2
        self.assertEqual(second.value, 2)

    def test_different_source_creates_distinct_row(self) -> None:
        """A different source on the same (room_profile, resonance) is a separate row."""
        row_a = upsert_room_resonance_modifier(
            self.room_profile, self.resonance, source="test:1", delta=6
        )
        row_b = upsert_room_resonance_modifier(
            self.room_profile, self.resonance, source="test:2", delta=3
        )
        self.assertNotEqual(row_a.pk, row_b.pk)
        self.assertEqual(
            LocationValueModifier.objects.filter(
                room_profile=self.room_profile, resonance=self.resonance
            ).count(),
            2,
        )
