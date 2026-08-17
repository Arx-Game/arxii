"""Tests for the downtime services (#3194)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone

from world.downtime.constants import SYSTEM_REBOOT_MESSAGE, DowntimeSource
from world.downtime.factories import DowntimeWindowFactory
from world.downtime.services import get_next_downtime


def _write_scheduled_file(directory: str, starts_at: datetime, mode: str = "reboot") -> Path:
    usec = int(starts_at.timestamp() * 1_000_000)
    path = Path(directory) / "scheduled"
    path.write_text(f"USEC={usec}\nWARN_WALL=1\nMODE={mode}\n")
    return path


class StaffWindowTests(TestCase):
    def test_no_windows_means_no_downtime(self):
        self.assertIsNone(get_next_downtime())

    def test_upcoming_window_is_returned(self):
        window = DowntimeWindowFactory(message="Postgres move")
        result = get_next_downtime()
        self.assertIsNotNone(result)
        self.assertEqual(result.source, DowntimeSource.STAFF)
        self.assertEqual(result.starts_at, window.starts_at)
        self.assertEqual(result.message, "Postgres move")

    def test_canceled_window_is_not_announced(self):
        DowntimeWindowFactory(canceled_at=timezone.now())
        self.assertIsNone(get_next_downtime())

    def test_finished_window_is_not_announced(self):
        DowntimeWindowFactory(
            starts_at=timezone.now() - timedelta(hours=3),
            expected_duration_minutes=30,
        )
        self.assertIsNone(get_next_downtime())

    def test_in_progress_window_is_still_announced(self):
        DowntimeWindowFactory(
            starts_at=timezone.now() - timedelta(minutes=10),
            expected_duration_minutes=60,
            message="Ongoing move",
        )
        result = get_next_downtime()
        self.assertIsNotNone(result)
        self.assertEqual(result.message, "Ongoing move")

    def test_finished_recent_window_does_not_shadow_a_future_one(self):
        DowntimeWindowFactory(
            starts_at=timezone.now() - timedelta(hours=5),
            expected_duration_minutes=15,
        )
        future = DowntimeWindowFactory(message="The real one")
        result = get_next_downtime()
        self.assertIsNotNone(result)
        self.assertEqual(result.starts_at, future.starts_at)

    def test_earliest_of_several_upcoming_windows_wins(self):
        DowntimeWindowFactory(starts_at=timezone.now() + timedelta(hours=12))
        soonest = DowntimeWindowFactory(starts_at=timezone.now() + timedelta(hours=2))
        result = get_next_downtime()
        self.assertEqual(result.starts_at, soonest.starts_at)


class SystemRebootTests(TestCase):
    def test_scheduled_reboot_is_derived_from_systemd_file(self):
        # microsecond=0 keeps the USEC round trip exact.
        reboot_at = (datetime.now(tz=UTC) + timedelta(hours=10)).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_scheduled_file(tmp, reboot_at)
            with override_settings(SCHEDULED_SHUTDOWN_FILE=str(path)):
                result = get_next_downtime()
        self.assertIsNotNone(result)
        self.assertEqual(result.source, DowntimeSource.SYSTEM)
        self.assertEqual(result.message, SYSTEM_REBOOT_MESSAGE)
        self.assertEqual(result.starts_at, reboot_at)

    def test_stale_file_for_a_past_reboot_is_ignored(self):
        reboot_at = datetime.now(tz=UTC) - timedelta(hours=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_scheduled_file(tmp, reboot_at)
            with override_settings(SCHEDULED_SHUTDOWN_FILE=str(path)):
                self.assertIsNone(get_next_downtime())

    def test_missing_file_means_no_system_downtime(self):
        with override_settings(SCHEDULED_SHUTDOWN_FILE="/nonexistent/scheduled"):
            self.assertIsNone(get_next_downtime())

    def test_garbage_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scheduled"
            path.write_text("not a systemd file at all")
            with override_settings(SCHEDULED_SHUTDOWN_FILE=str(path)):
                self.assertIsNone(get_next_downtime())

    def test_soonest_source_wins(self):
        """A reboot before the staff window is the one announced, and vice versa."""
        DowntimeWindowFactory(starts_at=timezone.now() + timedelta(hours=20))
        reboot_at = datetime.now(tz=UTC) + timedelta(hours=4)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_scheduled_file(tmp, reboot_at)
            with override_settings(SCHEDULED_SHUTDOWN_FILE=str(path)):
                result = get_next_downtime()
        self.assertEqual(result.source, DowntimeSource.SYSTEM)
