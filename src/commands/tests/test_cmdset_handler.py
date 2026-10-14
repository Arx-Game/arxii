from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.evennia_overrides.cmdset_handler import CmdSetHandler


class CmdSetHandlerTests(TestCase):
    """Tests for the command set handler sending OOB updates."""

    def test_send_update_sends_the_whole_frame(self):
        """A cmdset change re-sends the descriptors and the typed names together (#4346)."""
        session = MagicMock()
        obj = MagicMock()
        obj.sessions.all.return_value = [session]

        handler = CmdSetHandler.__new__(CmdSetHandler)
        handler.obj = obj
        handler._update_handle = None

        frame = (["cmd"], {"names": ["cmd"]})
        with patch(
            "commands.evennia_overrides.cmdset_handler.commands_frame",
            return_value=frame,
        ) as build_frame:
            handler._send_update()

        build_frame.assert_called_once_with(obj)
        session.msg.assert_called_with(commands=frame)
