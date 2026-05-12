from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.areas.factories import AreaFactory
from world.locations.constants import StatKey
from world.locations.factories import LocationStatModifierFactory
from world.locations.models import LocationStatModifier
from world.locations.services import cleanup_decayed_modifiers


class CleanupDecayedModifiersTests(TestCase):
    def test_zero_rate_modifier_not_deleted(self) -> None:
        area = AreaFactory()
        LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=0,
            applied_at=timezone.now() - timedelta(days=365),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 0)
        self.assertEqual(LocationStatModifier.objects.count(), 1)

    def test_non_decayed_modifier_not_deleted(self) -> None:
        area = AreaFactory()
        # value=20, decays at -1/day, applied 5 days ago → current_value=15
        LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=5),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 0)
        self.assertEqual(LocationStatModifier.objects.count(), 1)

    def test_decayed_modifier_deleted(self) -> None:
        area = AreaFactory()
        # value=10, decays at -1/day, applied 30 days ago → current_value=0
        LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 1)
        self.assertEqual(LocationStatModifier.objects.count(), 0)

    def test_mixed_batch_only_decayed_deleted(self) -> None:
        area = AreaFactory()
        # Decayed
        LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=20),
        )
        # Not decayed
        active = LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.NOISE,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=3),
        )
        # Static (no decay)
        static = LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.ORDER,
            value=50,
            change_per_day=0,
        )

        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 1)
        surviving = set(LocationStatModifier.objects.values_list("pk", flat=True))
        self.assertEqual(surviving, {active.pk, static.pk})

    def test_returns_zero_when_nothing_to_delete(self) -> None:
        self.assertEqual(cleanup_decayed_modifiers(), 0)

    def test_caller_supplied_now_honored(self) -> None:
        area = AreaFactory()
        # value=10, decays at -1/day, applied 5 days ago — NOT decayed if
        # now is 5 days ago, but IS decayed if now is well into the future
        applied = timezone.now() - timedelta(days=5)
        LocationStatModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=applied,
        )
        # Sweep with `now` = applied: 0 days elapsed → not decayed
        deleted_with_past_now = cleanup_decayed_modifiers(now=applied)
        self.assertEqual(deleted_with_past_now, 0)

        # Sweep with `now` 100 days ahead: very decayed
        far_future = applied + timedelta(days=100)
        deleted_with_future_now = cleanup_decayed_modifiers(now=far_future)
        self.assertEqual(deleted_with_future_now, 1)
        self.assertEqual(LocationStatModifier.objects.count(), 0)
