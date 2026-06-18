"""Error capture (#1164) — report_error dedup + the run_safely boundary."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.player_submissions.models import SystemErrorReport
from world.player_submissions.services import PLAYER_ERROR_MESSAGE, report_error, run_safely


def _raise(message: str = "boom") -> None:
    raise ValueError(message)


class ReportErrorTests(TestCase):
    def test_captures_a_report_with_traceback(self) -> None:
        try:
            _raise()
        except ValueError as exc:
            report_error(exc, label="test.hook")

        report = SystemErrorReport.objects.get(label="test.hook")
        assert report.exception_type == "ValueError"
        assert report.message == "boom"
        assert "ValueError" in report.traceback
        assert report.occurrence_count == 1

    def test_dedups_repeats_into_one_row_with_a_count(self) -> None:
        for _ in range(3):
            try:
                _raise("again")
            except ValueError as exc:
                report_error(exc, label="test.hook")

        reports = SystemErrorReport.objects.filter(exception_type="ValueError")
        assert reports.count() == 1
        assert reports.get().occurrence_count == 3


class RunSafelyTests(TestCase):
    @staticmethod
    def _boom() -> None:
        msg = "nope"
        raise RuntimeError(msg)

    def test_returns_result_and_captures_nothing_on_success(self) -> None:
        assert run_safely("ok", lambda: 42) == 42
        assert not SystemErrorReport.objects.exists()

    def test_captures_and_returns_none_on_failure(self) -> None:
        result = run_safely("risky", self._boom)

        assert result is None
        assert SystemErrorReport.objects.filter(exception_type="RuntimeError").exists()

    def test_notifies_the_actor_with_the_generic_line(self) -> None:
        actor = MagicMock()

        run_safely("risky", self._boom, actor=actor)

        actor.msg.assert_called_once_with(PLAYER_ERROR_MESSAGE)

    def test_no_actor_captures_without_notifying(self) -> None:
        run_safely("risky", self._boom)  # no actor → capture only

        assert SystemErrorReport.objects.exists()
