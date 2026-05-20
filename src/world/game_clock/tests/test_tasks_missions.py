"""Test that the missions reward-batch cron task registers at startup.

Phase 5b.2 wires :func:`apply_mission_reward_batch` into the game_clock
scheduler with task_key ``missions.reward_batch``. This test asserts the
registration happens when :func:`register_all_tasks` runs.
"""

from datetime import timedelta

from django.test import TestCase

from world.game_clock.task_registry import (
    clear_registry,
    get_registered_tasks,
)
from world.game_clock.tasks import register_all_tasks


class MissionsRewardBatchRegistrationTests(TestCase):
    """``missions.reward_batch`` is registered after register_all_tasks() runs."""

    def setUp(self) -> None:
        clear_registry()

    def tearDown(self) -> None:
        clear_registry()

    def test_missions_reward_batch_is_registered(self) -> None:
        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("missions.reward_batch", keys)

    def test_missions_reward_batch_has_hourly_interval(self) -> None:
        # Hourly mirrors the cleanup tasks in this file (Conditions/Forms
        # cleanups are hourly; AP regen is daily/weekly). The reward batch
        # is a cleanup-style sweep so the same cadence fits.
        register_all_tasks()
        task = next(t for t in get_registered_tasks() if t.task_key == "missions.reward_batch")
        self.assertEqual(task.interval, timedelta(hours=1))

    def test_missions_reward_batch_callable_is_apply_batch(self) -> None:
        from world.missions.services.cron import apply_mission_reward_batch

        register_all_tasks()
        task = next(t for t in get_registered_tasks() if t.task_key == "missions.reward_batch")
        self.assertIs(task.callable, apply_mission_reward_batch)
