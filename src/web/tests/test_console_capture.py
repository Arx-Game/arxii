"""A staff console line's output is tagged so the web client keeps it out of the column (#3857).

The web client sends a Commands-mode line as ``["text", [line], {"console": true}]``.
The ``text`` inputfunc marks the session for the duration of Evennia's own handler,
and ``ServerSession.data_out`` merges the session's ``ndb.text_frame_options`` into
the options of every ``text`` frame sent meanwhile, keeping any option a command
already set (#3856's ``type``). A line without the flag, and any frame sent outside
a console line, is untouched. This is the same seam Task 4 (#3933) uses to tag a
joining session's login look with ``{"on_entry": True}``.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from server.conf.inputfuncs import text as text_inputfunc
from server.conf.serversession import ServerSession


def _session() -> MagicMock:
    session = MagicMock()
    session.protocol_key = "websocket"
    session.ndb.text_frame_options = None
    return session


class ConsoleFlagOnInputTests(TestCase):
    def test_a_console_line_marks_the_session_while_evennia_runs_it(self) -> None:
        session = _session()
        seen: list[dict | None] = []

        def record(passed_session, *_args, **_kwargs):
            seen.append(passed_session.ndb.text_frame_options)

        with patch("server.conf.inputfuncs._evennia_text", side_effect=record) as delegate:
            text_inputfunc(session, "@dig East", console=True)
        self.assertEqual(seen, [{"console": True}])
        self.assertIsNone(session.ndb.text_frame_options)
        # The flag is ours; Evennia's handler never sees it as a keyword.
        self.assertNotIn("console", delegate.call_args.kwargs)

    def test_the_mark_clears_even_when_the_command_raises(self) -> None:
        session = _session()
        with (
            patch("server.conf.inputfuncs._evennia_text", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            text_inputfunc(session, "@dig East", console=True)
        self.assertIsNone(session.ndb.text_frame_options)

    def test_a_plain_line_never_marks_the_session(self) -> None:
        session = _session()
        with patch("server.conf.inputfuncs._evennia_text") as delegate:
            text_inputfunc(session, "look")
        delegate.assert_called_once_with(session, "look")
        self.assertIsNone(session.ndb.text_frame_options)


class ConsoleTagOnOutputTests(TestCase):
    def _session(self, options: dict | None) -> ServerSession:
        session = ServerSession()
        # `ndb` keys its in-memory store by the session id `init_session` normally assigns.
        session.sessid = 1
        session.sessionhandler = MagicMock()
        session.ndb.text_frame_options = options
        return session

    def sent_text(self, session: ServerSession):
        return session.sessionhandler.data_out.call_args.kwargs["text"]

    def test_a_bare_string_becomes_the_tuple_form_with_the_console_option(self) -> None:
        session = self._session(options={"console": True})
        session.data_out(text="Created room East(#412).")
        session.sessionhandler.data_out.assert_called_once_with(
            session, text=("Created room East(#412).", {"console": True})
        )

    def test_an_existing_option_is_kept_beside_the_console_one(self) -> None:
        session = self._session(options={"console": True})
        session.data_out(text=("Command 'x' is not available.", {"type": "error"}))
        session.sessionhandler.data_out.assert_called_once_with(
            session, text=("Command 'x' is not available.", {"type": "error", "console": True})
        )

    def test_frames_outside_a_console_line_are_untouched(self) -> None:
        session = self._session(options=None)
        session.data_out(text="A quiet room.", options={"nocolor": True})
        session.sessionhandler.data_out.assert_called_once_with(
            session, text="A quiet room.", options={"nocolor": True}
        )

    def test_a_frame_without_text_is_untouched_while_capturing(self) -> None:
        session = self._session(options={"console": True})
        session.data_out(command_error={"error": "x", "command": "y"})
        session.sessionhandler.data_out.assert_called_once_with(
            session, command_error={"error": "x", "command": "y"}
        )

    def test_any_option_set_on_the_session_is_merged_into_text_frames(self) -> None:
        session = self._session(options={"on_entry": True})
        session.data_out(text=("Limbo", {"type": "look"}))
        self.assertEqual(self.sent_text(session), ("Limbo", {"type": "look", "on_entry": True}))

    def test_the_frames_own_option_wins_over_the_session_option(self) -> None:
        session = self._session(options={"console": True})
        session.data_out(text=("x", {"console": False}))
        self.assertEqual(self.sent_text(session), ("x", {"console": False}))

    def test_a_non_text_frame_is_never_touched(self) -> None:
        session = self._session(options={"console": True})
        session.data_out(oob=("echo", ("hi",), {}))
        session.sessionhandler.data_out.assert_called_once_with(session, oob=("echo", ("hi",), {}))
