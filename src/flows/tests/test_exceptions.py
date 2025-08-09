"""
Tests for flows.exceptions module.
"""

from commands.exceptions import CommandError
from flows.exceptions import CancelFlow, StopBranch, StopEvent, StopFlow


class TestStopEvent:
    """Tests for StopEvent exception."""

    def test_stop_event_inherits_from_command_error(self):
        """StopEvent should inherit from CommandError."""
        exception = StopEvent("test message")
        assert isinstance(exception, CommandError)

    def test_stop_event_can_be_raised_and_caught(self):
        """StopEvent can be raised and caught properly."""
        try:
            raise StopEvent("test message")
        except StopEvent as e:
            assert str(e) == "test message"
        except Exception:
            raise AssertionError("Should have caught StopEvent specifically")

    def test_stop_event_without_message(self):
        """StopEvent can be raised without a message."""
        try:
            raise StopEvent()
        except StopEvent as e:
            assert str(e) == ""


class TestStopBranch:
    """Tests for StopBranch exception."""

    def test_stop_branch_inherits_from_exception(self):
        """StopBranch should inherit from Exception."""
        exception = StopBranch()
        assert isinstance(exception, Exception)

    def test_stop_branch_can_be_raised_and_caught(self):
        """StopBranch can be raised and caught properly."""
        try:
            raise StopBranch()
        except StopBranch:
            pass  # Expected
        except Exception:
            raise AssertionError("Should have caught StopBranch specifically")

    def test_stop_branch_with_message(self):
        """StopBranch can be raised with a message."""
        try:
            raise StopBranch("test message")
        except StopBranch as e:
            assert str(e) == "test message"


class TestStopFlow:
    """Tests for StopFlow exception."""

    def test_stop_flow_inherits_from_exception(self):
        """StopFlow should inherit from Exception."""
        exception = StopFlow()
        assert isinstance(exception, Exception)

    def test_stop_flow_without_message(self):
        """StopFlow can be created without a message."""
        exception = StopFlow()
        assert exception.message is None
        assert str(exception) == "None"

    def test_stop_flow_with_message(self):
        """StopFlow can be created with a message."""
        exception = StopFlow("test message")
        assert exception.message == "test message"
        assert str(exception) == "test message"

    def test_stop_flow_can_be_raised_and_caught(self):
        """StopFlow can be raised and caught properly."""
        try:
            raise StopFlow("test message")
        except StopFlow as e:
            assert e.message == "test message"
            assert str(e) == "test message"
        except Exception:
            raise AssertionError("Should have caught StopFlow specifically")


class TestCancelFlow:
    """Tests for CancelFlow exception."""

    def test_cancel_flow_inherits_from_exception(self):
        """CancelFlow should inherit from Exception."""
        exception = CancelFlow("test message")
        assert isinstance(exception, Exception)

    def test_cancel_flow_requires_message(self):
        """CancelFlow requires a message parameter."""
        exception = CancelFlow("test message")
        assert exception.message == "test message"
        assert str(exception) == "test message"

    def test_cancel_flow_can_be_raised_and_caught(self):
        """CancelFlow can be raised and caught properly."""
        try:
            raise CancelFlow("test error message")
        except CancelFlow as e:
            assert e.message == "test error message"
            assert str(e) == "test error message"
        except Exception:
            raise AssertionError("Should have caught CancelFlow specifically")

    def test_cancel_flow_empty_string_message(self):
        """CancelFlow can be created with an empty string message."""
        exception = CancelFlow("")
        assert exception.message == ""
        assert str(exception) == ""
