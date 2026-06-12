"""Tests for the game clock task registry."""

from datetime import UTC, timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from world.game_clock.models import ScheduledTaskRecord
from world.game_clock.task_registry import (
    CronDefinition,
    FrequencyType,
    clear_registry,
    register_task,
    run_due_tasks,
)


class RunDueTasksTests(TestCase):
    """Tests for run_due_tasks and the task registry."""

    def setUp(self) -> None:
        clear_registry()

    def tearDown(self) -> None:
        clear_registry()

    def _make_task(
        self,
        key: str = "test_task",
        interval: timedelta | None = None,
        frequency_type: FrequencyType = FrequencyType.REAL,
    ) -> tuple[CronDefinition, MagicMock]:
        """Helper to create and register a task, returning the definition and mock."""
        mock_fn = MagicMock()
        task_def = CronDefinition(
            task_key=key,
            callable=mock_fn,
            interval=interval or timedelta(minutes=10),
            frequency_type=frequency_type,
        )
        register_task(task_def)
        return task_def, mock_fn

    def test_first_execution_runs_immediately(self) -> None:
        """A task with no prior run record should execute on first check."""
        _, mock_fn = self._make_task("first_run")
        executed = run_due_tasks()
        self.assertEqual(executed, ["first_run"])
        mock_fn.assert_called_once()

    def test_task_not_due_skipped(self) -> None:
        """A task that ran recently (within its interval) should be skipped."""
        _, mock_fn = self._make_task("recent", interval=timedelta(hours=1))
        # Create a record showing it ran just now
        ScheduledTaskRecord.objects.create(
            task_key="recent",
            last_run_at=timezone.now(),
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])
        mock_fn.assert_not_called()

    def test_task_interval_elapsed_runs(self) -> None:
        """A task whose interval has elapsed should run."""
        _, mock_fn = self._make_task("elapsed", interval=timedelta(minutes=5))
        ScheduledTaskRecord.objects.create(
            task_key="elapsed",
            last_run_at=timezone.now() - timedelta(minutes=10),
        )
        executed = run_due_tasks()
        self.assertEqual(executed, ["elapsed"])
        mock_fn.assert_called_once()

    def test_disabled_task_skipped(self) -> None:
        """A disabled task should not run even if due."""
        _, mock_fn = self._make_task("disabled_task")
        ScheduledTaskRecord.objects.create(
            task_key="disabled_task",
            enabled=False,
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])
        mock_fn.assert_not_called()

    def test_updates_last_run_at(self) -> None:
        """After execution, last_run_at should be updated."""
        self._make_task("update_check")
        run_due_tasks()
        record = ScheduledTaskRecord.objects.get(task_key="update_check")
        self.assertIsNotNone(record.last_run_at)

    def test_ic_frequency_checks_ic_time(self) -> None:
        """An IC-frequency task should check against ic_now."""
        _, mock_fn = self._make_task(
            "ic_task",
            interval=timedelta(days=1),
            frequency_type=FrequencyType.IC,
        )
        ic_past = timezone.now() - timedelta(days=2)
        ic_now = timezone.now()
        ScheduledTaskRecord.objects.create(
            task_key="ic_task",
            last_ic_run_at=ic_past,
        )
        executed = run_due_tasks(ic_now=ic_now)
        self.assertEqual(executed, ["ic_task"])
        mock_fn.assert_called_once()

    def test_ic_task_skipped_when_ic_now_not_provided(self) -> None:
        """An IC-frequency task should be skipped when ic_now is None."""
        _, mock_fn = self._make_task(
            "ic_no_now",
            interval=timedelta(days=1),
            frequency_type=FrequencyType.IC,
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])
        mock_fn.assert_not_called()

    def test_ic_task_first_run_with_ic_now(self) -> None:
        """An IC task with no prior run should execute when ic_now is provided."""
        _, mock_fn = self._make_task(
            "ic_first",
            interval=timedelta(days=1),
            frequency_type=FrequencyType.IC,
        )
        executed = run_due_tasks(ic_now=timezone.now())
        self.assertEqual(executed, ["ic_first"])
        mock_fn.assert_called_once()

    def test_failed_task_does_not_block_others(self) -> None:
        """A task that raises an exception should not prevent other tasks from running."""
        failing_mock = MagicMock(side_effect=RuntimeError("boom"))
        failing_task = CronDefinition(
            task_key="failing",
            callable=failing_mock,
            interval=timedelta(minutes=10),
        )
        register_task(failing_task)

        _, success_mock = self._make_task("succeeding")

        executed = run_due_tasks()
        # The failing task should not appear in executed list
        self.assertNotIn("failing", executed)
        # The succeeding task should still run
        self.assertIn("succeeding", executed)
        success_mock.assert_called_once()

    def test_multiple_due_tasks_all_run(self) -> None:
        """Multiple due tasks should all be executed."""
        _, mock_a = self._make_task("task_a")
        _, mock_b = self._make_task("task_b")
        _, mock_c = self._make_task("task_c")

        executed = run_due_tasks()
        self.assertEqual(sorted(executed), ["task_a", "task_b", "task_c"])
        mock_a.assert_called_once()
        mock_b.assert_called_once()
        mock_c.assert_called_once()

    def test_ic_task_updates_last_ic_run_at(self) -> None:
        """After executing an IC task, last_ic_run_at should be set."""
        self._make_task(
            "ic_update",
            interval=timedelta(days=1),
            frequency_type=FrequencyType.IC,
        )
        ic_now = timezone.now()
        run_due_tasks(ic_now=ic_now)
        record = ScheduledTaskRecord.objects.get(task_key="ic_update")
        self.assertIsNotNone(record.last_ic_run_at)
        self.assertEqual(record.last_ic_run_at, ic_now)


class AnchoredWeeklyDueTests(TestCase):
    """Sunday-midnight-EST anchored rollover (#932)."""

    def _task(self):
        from datetime import timedelta

        from world.game_clock.task_registry import CronDefinition

        return CronDefinition(
            task_key="anchored_test",
            callable=lambda: None,
            interval=timedelta(days=7),
            anchor_weekday=0,  # Monday (= Sunday midnight EST in UTC terms)
            anchor_hour_utc=5,
        )

    def test_first_sight_baselines_without_firing(self) -> None:
        from datetime import datetime

        from world.game_clock.models import ScheduledTaskRecord
        from world.game_clock.task_registry import _is_task_due

        record = ScheduledTaskRecord.objects.create(task_key="anchored_test")
        now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)  # Wednesday
        assert _is_task_due(record, self._task(), now=now, ic_now=None) is False
        record.refresh_from_db()
        assert record.last_run_at is not None  # baseline stamped

    def test_due_after_anchor_passes(self) -> None:
        from datetime import datetime

        from world.game_clock.models import ScheduledTaskRecord
        from world.game_clock.task_registry import _is_task_due

        # Last ran Saturday; now it's Monday 06:00 UTC — the anchor passed.
        record = ScheduledTaskRecord.objects.create(
            task_key="anchored_test",
            last_run_at=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),  # Saturday
        )
        now = datetime(2026, 6, 15, 6, 0, tzinfo=UTC)  # Monday after 05:00
        assert _is_task_due(record, self._task(), now=now, ic_now=None) is True

    def test_not_due_again_same_week(self) -> None:
        from datetime import datetime

        from world.game_clock.models import ScheduledTaskRecord
        from world.game_clock.task_registry import _is_task_due

        # Ran at Monday 05:30; Wednesday is still the same anchor window.
        record = ScheduledTaskRecord.objects.create(
            task_key="anchored_test",
            last_run_at=datetime(2026, 6, 15, 5, 30, tzinfo=UTC),
        )
        now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)  # Wednesday
        assert _is_task_due(record, self._task(), now=now, ic_now=None) is False

    def test_not_due_before_anchor_hour(self) -> None:
        from datetime import datetime

        from world.game_clock.models import ScheduledTaskRecord
        from world.game_clock.task_registry import _is_task_due

        # Monday 04:00 UTC — before the 05:00 anchor; last ran Friday.
        record = ScheduledTaskRecord.objects.create(
            task_key="anchored_test",
            last_run_at=datetime(2026, 6, 12, 12, 0, tzinfo=UTC),  # Friday
        )
        now = datetime(2026, 6, 15, 4, 0, tzinfo=UTC)
        assert _is_task_due(record, self._task(), now=now, ic_now=None) is False
