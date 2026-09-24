"""Tests for the staff-requested full reboot (#4001)."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, create_autospec, patch

from django.test import SimpleTestCase
from evennia.server.sessionhandler import ServerSessionHandler


def _handler(mock_evennia: MagicMock) -> MagicMock:
    """Stand a signature-checked ServerSessionHandler in for the real one.

    A bare MagicMock accepts any call shape, so a drift on ``announce_all`` or
    ``portal_shutdown`` would stay green; an autospec fails it.
    """
    handler = create_autospec(ServerSessionHandler, instance=True)
    mock_evennia.SESSION_HANDLER = handler
    return handler


class RequestRebootTests(SimpleTestCase):
    """A reboot is a request file for the root watchdog plus a Portal shutdown.

    The game user cannot restart its own systemd unit, and ``Restart=always`` was
    rejected because it would turn every ``@shutdown`` into a restart. So the
    request file is what tells the watchdog (root, once a minute) that this
    inactive unit should come back, and the Portal shutdown is exactly what
    ``@shutdown`` does.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.request_file = Path(self.tmp.name) / "server" / "reboot.requested"

    def _request(self, requested_by: str = "Apostate") -> None:
        from evennia_extensions.reboot import request_reboot

        with patch("evennia_extensions.reboot.REBOOT_REQUEST_FILE", self.request_file):
            request_reboot(requested_by=requested_by)

    @patch("evennia_extensions.reboot.evennia")
    def test_writes_the_request_file_before_shutting_down(self, mock_evennia: MagicMock) -> None:
        handler = _handler(mock_evennia)
        seen_at_shutdown: list[bool] = []
        handler.portal_shutdown.side_effect = lambda: seen_at_shutdown.append(
            self.request_file.exists()
        )

        self._request()

        self.assertEqual(seen_at_shutdown, [True])
        self.assertIn("Apostate", self.request_file.read_text())

    @patch("evennia_extensions.reboot.evennia")
    def test_announces_to_everyone_naming_who_asked(self, mock_evennia: MagicMock) -> None:
        handler = _handler(mock_evennia)

        self._request(requested_by="Apostate")

        handler.announce_all.assert_called_once()
        announcement = handler.announce_all.call_args[0][0]
        self.assertIn("Apostate", announcement)
        self.assertIn("restart", announcement.lower())

    @patch("evennia_extensions.reboot.evennia")
    def test_does_not_shut_down_when_the_request_cannot_be_written(
        self, mock_evennia: MagicMock
    ) -> None:
        """No file means the watchdog would never start the game again."""
        handler = _handler(mock_evennia)
        # A file where the parent directory should be makes mkdir/write fail.
        self.request_file.parent.parent.mkdir(parents=True, exist_ok=True)
        self.request_file.parent.write_text("not a directory")

        with self.assertRaises(OSError):
            self._request()

        handler.portal_shutdown.assert_not_called()
        handler.announce_all.assert_not_called()
