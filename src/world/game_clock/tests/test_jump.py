"""The jump plan changes nothing until it is applied, and puts everything back if its
write fails (#5248)."""

from datetime import UTC, datetime

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.game_clock.factories import GameClockFactory
from world.game_clock.jump import JumpPlan
from world.game_clock.models import GameClock, ScheduledTaskRecord

OLD = datetime(1000, 1, 1, tzinfo=UTC)
NEW = datetime(1020, 1, 1, tzinfo=UTC)


class JumpPlanTests(TestCase):
    def test_recording_a_value_changes_nothing(self) -> None:
        clock = GameClockFactory(anchor_ic_time=OLD, paused=True)
        plan = JumpPlan()

        plan.set(clock, "anchor_ic_time", NEW)

        self.assertEqual(len(plan), 1)
        self.assertEqual(clock.anchor_ic_time, OLD)

    def test_apply_assigns_and_writes(self) -> None:
        clock = GameClockFactory(anchor_ic_time=OLD, paused=True)
        plan = JumpPlan()
        plan.set(clock, "anchor_ic_time", NEW)

        plan.apply()

        self.assertEqual(clock.anchor_ic_time, NEW)
        self.assertEqual(
            GameClock.objects.filter(pk=clock.pk).values_list("anchor_ic_time", flat=True)[0], NEW
        )

    def test_a_failed_write_puts_every_instance_back(self) -> None:
        """The clock is live for the whole process the moment it is assigned, and a
        rolled-back transaction does not undo that; the plan does."""
        clock = GameClockFactory(anchor_ic_time=OLD, paused=True)
        record = ScheduledTaskRecord.objects.create(task_key="test.plan", last_ic_run_at=OLD)
        plan = JumpPlan()
        plan.set(clock, "anchor_ic_time", NEW)
        plan.set(record, "last_ic_run_at", NEW)
        plan.set(record, "task_key", None)  # the column refuses a null

        with self.assertRaises(IntegrityError), transaction.atomic():
            plan.apply()

        self.assertEqual(clock.anchor_ic_time, OLD)
        self.assertEqual(record.last_ic_run_at, OLD)
        self.assertEqual(record.task_key, "test.plan")
