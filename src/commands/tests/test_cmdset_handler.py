from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.evennia_overrides.cmdset_handler import CmdSetHandler


class CmdSetHandlerTests(TestCase):
    """Tests for the command set handler sending OOB updates."""

    def test_send_update_includes_empty_kwargs(self):
        session = MagicMock()
        obj = MagicMock()
        obj.sessions.all.return_value = [session]

        handler = CmdSetHandler.__new__(CmdSetHandler)
        handler.obj = obj
        handler._update_handle = None

        with patch(
            "commands.evennia_overrides.cmdset_handler.serialize_cmdset",
            return_value=["cmd"],
        ):
            handler._send_update()

        session.msg.assert_called_with(commands=(["cmd"], {}))
