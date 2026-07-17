"""Tests for the telnet MUSH-markup normalization in the ``text`` inputfunc."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from server.conf.inputfuncs import text as text_inputfunc


def _session(protocol_key: str) -> MagicMock:
    session = MagicMock()
    session.protocol_key = protocol_key
    return session


class TextInputfuncMarkupTests(TestCase):
    def test_telnet_input_is_normalized_before_delegating(self) -> None:
        session = _session("telnet")
        with patch("server.conf.inputfuncs._evennia_text") as delegate:
            text_inputfunc(session, "A man.%rHe waits.")
        delegate.assert_called_once()
        forwarded = delegate.call_args.args[1]
        self.assertEqual(forwarded, "A man.\nHe waits.")

    def test_telnet_ssl_is_also_normalized(self) -> None:
        session = _session("telnet/ssl")
        with patch("server.conf.inputfuncs._evennia_text") as delegate:
            text_inputfunc(session, "a%tb")
        self.assertEqual(delegate.call_args.args[1], "a\tb")

    def test_websocket_input_is_left_untouched(self) -> None:
        session = _session("websocket")
        with patch("server.conf.inputfuncs._evennia_text") as delegate:
            text_inputfunc(session, "A man.%rHe waits.")
        self.assertEqual(delegate.call_args.args[1], "A man.%rHe waits.")

    def test_empty_args_delegates_without_error(self) -> None:
        session = _session("telnet")
        with patch("server.conf.inputfuncs._evennia_text") as delegate:
            text_inputfunc(session)
        delegate.assert_called_once_with(session)
