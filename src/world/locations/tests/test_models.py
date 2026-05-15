from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier, LocationValueOverride


class LocationValueOverrideTests(TestCase):
    def test_create_with_area(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        row = LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        self.assertEqual(row.area, area)
        self.assertIsNone(row.room_profile)

    def test_create_with_room(self) -> None:
        room = RoomProfileFactory()
        row = LocationValueOverride.objects.create(
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
        row = LocationValueOverride(
            parent_type=LocationParentType.AREA,
            area=area,
            room_profile=room,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_fk(self) -> None:
        row = LocationValueOverride(
            parent_type=LocationParentType.AREA,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_unique_override_per_area_stat(self) -> None:
        area = AreaFactory()
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationValueOverride.objects.create(
                parent_type=LocationParentType.AREA,
                area=area,
                stat_key=StatKey.CRIME,
                value=20,
            )

    def test_unique_override_per_room_stat(self) -> None:
        room = RoomProfileFactory()
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=-2,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationValueOverride.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=room,
                stat_key=StatKey.LIGHTING,
                value=2,
            )

    def test_different_stats_on_same_area_ok(self) -> None:
        area = AreaFactory()
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
        )
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.ORDER,
            value=80,
        )
        self.assertEqual(
            LocationValueOverride.objects.filter(area=area).count(),
            2,
        )


class LocationValueModifierCurrentValueTests(TestCase):
    def test_change_per_day_zero_is_static(self) -> None:
        area = AreaFactory()
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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
        mod = LocationValueModifier.objects.create(
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


class LocationValueModifierStackingTests(TestCase):
    def test_multiple_modifiers_on_same_area_and_stat_allowed(self) -> None:
        area = AreaFactory()
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            source="rebellion",
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            source="market_day",
        )
        self.assertEqual(
            LocationValueModifier.objects.filter(area=area, stat_key=StatKey.CRIME).count(),
            2,
        )

    def test_create_with_room_profile(self) -> None:
        room = RoomProfileFactory()
        mod = LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            stat_key=StatKey.LIGHTING,
            value=1,
        )
        self.assertEqual(mod.room_profile, room)
        self.assertIsNone(mod.area)


class LocationValueOverrideKeyTypeTests(TestCase):
    """Validation tests for the key_type discriminator on Override (stat vs resonance)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room_profile = RoomProfileFactory()
        cls.area = AreaFactory(level=AreaLevel.WARD)

    def test_locationstatoverride_resonance_key_clean(self) -> None:
        """A row with key_type=RESONANCE requires resonance and forbids stat_key."""
        from world.locations.constants import KeyType
        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory()
        row = LocationValueOverride(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=1000,
        )
        row.full_clean()  # should not raise

    def test_locationstatoverride_resonance_key_requires_resonance(self) -> None:
        """key_type=RESONANCE with resonance=None fails clean."""
        from world.locations.constants import KeyType

        row = LocationValueOverride(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            stat_key=StatKey.CRIME,  # wrong field set
            value=1000,
        )
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        assert "resonance" in ctx.exception.message_dict

    def test_locationstatoverride_stat_key_still_works(self) -> None:
        """Existing key_type=STAT path continues to work unchanged."""
        from world.locations.constants import KeyType

        row = LocationValueOverride(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.STAT,
            stat_key=StatKey.CRIME,
            value=42,
        )
        row.full_clean()  # should not raise

    def test_locationstatoverride_unique_per_room_resonance(self) -> None:
        """Only one override row per (room, resonance) — partial UniqueConstraint."""
        from world.locations.constants import KeyType
        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory()
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=1000,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LocationValueOverride.objects.create(
                    parent_type=LocationParentType.ROOM,
                    room_profile=self.room_profile,
                    key_type=KeyType.RESONANCE,
                    resonance=resonance,
                    value=500,
                )

    def test_locationstatoverride_multiple_resonances_same_room(self) -> None:
        """Different resonances on same room are allowed (only same-resonance is unique)."""
        from world.locations.constants import KeyType
        from world.magic.factories import ResonanceFactory

        celestial = ResonanceFactory(name="Copperi")
        abyssal = ResonanceFactory(name="Predari")
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=celestial,
            value=1000,
        )
        # Should NOT raise — different resonance
        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=abyssal,
            value=500,
        )


class LocationValueModifierKeyTypeTests(TestCase):
    """Validation tests for the key_type discriminator (stat vs resonance)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room_profile = RoomProfileFactory()

    def test_locationstatmodifier_resonance_key_clean(self) -> None:
        """A row with key_type=RESONANCE requires resonance and forbids stat_key."""
        from world.locations.constants import KeyType
        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory()
        row = LocationValueModifier(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=100,
        )
        row.full_clean()  # should not raise

    def test_locationstatmodifier_resonance_key_requires_resonance(self) -> None:
        """key_type=RESONANCE with resonance=None fails clean."""
        from world.locations.constants import KeyType

        row = LocationValueModifier(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            stat_key=StatKey.CRIME,  # wrong field set
            value=100,
        )
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        assert "resonance" in ctx.exception.message_dict

    def test_locationstatmodifier_stat_key_still_works(self) -> None:
        """Existing key_type=STAT path continues to work unchanged."""
        from world.locations.constants import KeyType

        row = LocationValueModifier(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.STAT,
            stat_key=StatKey.CRIME,
            value=42,
        )
        row.full_clean()  # should not raise
