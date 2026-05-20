from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from world.areas.factories import AreaFactory
from world.locations.constants import StatKey
from world.locations.factories import LocationValueModifierFactory
from world.locations.models import LocationValueModifier
from world.locations.services import cleanup_decayed_modifiers


class CleanupDecayedModifiersTests(TestCase):
    def test_zero_rate_modifier_not_deleted(self) -> None:
        area = AreaFactory()
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=0,
            applied_at=timezone.now() - timedelta(days=365),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 0)
        self.assertEqual(LocationValueModifier.objects.count(), 1)

    def test_non_decayed_modifier_not_deleted(self) -> None:
        area = AreaFactory()
        # value=20, decays at -1/day, applied 5 days ago → current_value=15
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=5),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 0)
        self.assertEqual(LocationValueModifier.objects.count(), 1)

    def test_decayed_modifier_deleted(self) -> None:
        area = AreaFactory()
        # value=10, decays at -1/day, applied 30 days ago → current_value=0
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 1)
        self.assertEqual(LocationValueModifier.objects.count(), 0)

    def test_mixed_batch_only_decayed_deleted(self) -> None:
        area = AreaFactory()
        # Decayed
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=20),
        )
        # Not decayed
        active = LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.NOISE,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=3),
        )
        # Static (no decay)
        static = LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.ORDER,
            value=50,
            change_per_day=0,
        )

        deleted = cleanup_decayed_modifiers()
        self.assertEqual(deleted, 1)
        surviving = set(LocationValueModifier.objects.values_list("pk", flat=True))
        self.assertEqual(surviving, {active.pk, static.pk})

    def test_returns_zero_when_nothing_to_delete(self) -> None:
        self.assertEqual(cleanup_decayed_modifiers(), 0)

    def test_caller_supplied_now_honored(self) -> None:
        area = AreaFactory()
        # value=10, decays at -1/day, applied 5 days ago — NOT decayed if
        # now is 5 days ago, but IS decayed if now is well into the future
        applied = timezone.now() - timedelta(days=5)
        LocationValueModifierFactory(
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
        self.assertEqual(LocationValueModifier.objects.count(), 0)


class CleanupDecayedModifiersCommandTests(TestCase):
    def test_command_runs_and_reports_count(self) -> None:
        area = AreaFactory()
        # One decayed, one not
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.NOISE,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=3),
        )

        out = StringIO()
        call_command("cleanup_decayed_modifiers", stdout=out)
        output = out.getvalue()
        self.assertIn("Deleted 1", output)
        self.assertEqual(LocationValueModifier.objects.count(), 1)
