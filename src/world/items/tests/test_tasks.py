"""Test that the soft-delete cleanup cron task registers at startup (#1025).

Task 4 wires :func:`soft_delete_cleanup_task` into the game_clock
scheduler with task_key ``items.soft_delete_cleanup`` and a 1-day interval.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from world.game_clock.task_registry import (
    clear_registry,
    get_registered_tasks,
)
from world.game_clock.tasks import register_all_tasks


class SoftDeleteCleanupTaskRegistrationTests(TestCase):
    """``items.soft_delete_cleanup`` is registered after register_all_tasks() runs."""

    def setUp(self) -> None:
        clear_registry()

    def tearDown(self) -> None:
        clear_registry()

    def test_cleanup_task_is_registered(self) -> None:
        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("items.soft_delete_cleanup", keys)

    def test_cleanup_task_has_daily_interval(self) -> None:
        register_all_tasks()
        task = next(t for t in get_registered_tasks() if t.task_key == "items.soft_delete_cleanup")
        self.assertEqual(task.interval, timedelta(days=1))

    def test_cleanup_task_callable_invokes_service(self) -> None:
        from world.items.tasks import soft_delete_cleanup_task

        with patch("world.items.tasks.purge_expired_soft_deleted_items", return_value=3) as mocked:
            soft_delete_cleanup_task()
        mocked.assert_called_once_with()
