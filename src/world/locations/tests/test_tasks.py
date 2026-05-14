"""Tests for the location periodic task wiring."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from world.areas.factories import AreaFactory
from world.game_clock.task_registry import get_registered_tasks
from world.game_clock.tasks import register_all_tasks
from world.locations.constants import StatKey
from world.locations.factories import LocationValueModifierFactory
from world.locations.models import LocationValueModifier
from world.locations.tasks import decayed_modifier_cleanup_task


class DecayedModifierCleanupTaskTests(TestCase):
    def test_deletes_decayed_modifiers(self) -> None:
        area = AreaFactory()
        # Decayed: value=10, -1/day, 30 days ago → current_value=0
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=10,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=30),
        )
        # Not decayed: value=20, -1/day, 5 days ago → current_value=15
        active = LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.NOISE,
            value=20,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=5),
        )

        decayed_modifier_cleanup_task()

        surviving = list(LocationValueModifier.objects.values_list("pk", flat=True))
        self.assertEqual(surviving, [active.pk])

    def test_logs_deleted_count(self) -> None:
        area = AreaFactory()
        LocationValueModifierFactory(
            area=area,
            stat_key=StatKey.CRIME,
            value=5,
            change_per_day=-1,
            applied_at=timezone.now() - timedelta(days=20),
        )
        with self.assertLogs("world.locations.tasks", level="INFO") as cm:
            decayed_modifier_cleanup_task()
        self.assertTrue(
            any("1 decayed modifiers deleted" in line for line in cm.output),
            cm.output,
        )


class TaskRegistrationTests(TestCase):
    def test_cleanup_task_is_registered(self) -> None:
        register_all_tasks()
        tasks = {t.task_key: t for t in get_registered_tasks()}
        cleanup = tasks.get("locations.decayed_modifier_cleanup")
        self.assertIsNotNone(cleanup, "decayed_modifier_cleanup not registered")
        self.assertEqual(cleanup.interval, timedelta(hours=24))
        self.assertIs(cleanup.callable, decayed_modifier_cleanup_task)

    def test_registered_callable_invokes_service(self) -> None:
        register_all_tasks()
        tasks = {t.task_key: t for t in get_registered_tasks()}
        cleanup = tasks["locations.decayed_modifier_cleanup"]
        with patch("world.locations.tasks.cleanup_decayed_modifiers", return_value=0) as svc:
            cleanup.callable()
        svc.assert_called_once_with()
