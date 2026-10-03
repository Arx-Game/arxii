"""A typed ``quit`` reaches the web client as a close reason it reads as leaving.

The client reconnects every close the server makes, since a close code alone
never says who meant it. ``quit`` is the one close the player asked for, and
the only thing that tells it apart on the wire is the reason Evennia's
``CmdQuit`` hands to the disconnect. The client keeps those reasons in
``SERVER_QUIT_CLOSE_REASONS``; these tests fail when the command stops giving
exactly that set, or when the Portal stops putting the reason on the frame.
"""

from pathlib import Path
import re
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from evennia.commands.default.account import CmdQuit
from evennia.server.portal.webclient import CLOSE_NORMAL, WebSocketClient

from server.portal.secure_websocket import SecureWebSocketClient

CLIENT_TYPES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "hooks" / "types.ts"

_CLIENT_SET = re.compile(r"SERVER_QUIT_CLOSE_REASONS\b[^=]*=\s*new Set\(\[(?P<members>[^\]]*)\]\)")


class ClientQuitReasonsMissing(AssertionError):
    """``types.ts`` no longer declares ``SERVER_QUIT_CLOSE_REASONS`` the way we scan for it."""

    def __init__(self) -> None:
        super().__init__("SERVER_QUIT_CLOSE_REASONS is no longer a `new Set([...])` in types.ts")


def client_quit_reasons(source: str) -> set[str]:
    """Return the string literals inside ``SERVER_QUIT_CLOSE_REASONS``."""
    match = _CLIENT_SET.search(source)
    if match is None:
        raise ClientQuitReasonsMissing
    return set(re.findall(r"'([^']+)'", match.group("members")))


def quit_reason(switches: list[str]) -> str:
    """Run Evennia's ``quit`` and return the reason it disconnects the session with."""
    command = CmdQuit()
    command.account = MagicMock()
    command.session = MagicMock()
    command.switches = switches
    command.account.sessions.all.return_value = [command.session]
    command.func()
    return command.account.disconnect_session_from_account.call_args.args[1]


class ClientQuitReasonExtractionTests(SimpleTestCase):
    def test_reads_the_set_members(self) -> None:
        source = "const SERVER_QUIT_CLOSE_REASONS: ReadonlySet<string> = new Set(['a', 'b/c']);"
        self.assertEqual(client_quit_reasons(source), {"a", "b/c"})

    def test_a_missing_set_fails_loudly(self) -> None:
        with self.assertRaises(ClientQuitReasonsMissing):
            client_quit_reasons("export const OTHER = new Set(['quit']);")


class QuitCloseReasonParityTests(SimpleTestCase):
    def test_the_client_names_every_reason_quit_gives(self) -> None:
        server = {quit_reason([]), quit_reason(["all"])}
        client = client_quit_reasons(CLIENT_TYPES.read_text(encoding="utf-8"))
        self.assertEqual(client, server)

    def test_the_portal_sends_the_reason_on_the_close_frame(self) -> None:
        protocol = SecureWebSocketClient()
        protocol.sessionhandler = MagicMock()
        with (
            patch.object(protocol, "get_client_session", return_value=None),
            patch.object(WebSocketClient, "sendClose") as send_close,
        ):
            protocol.disconnect("quit")
        send_close.assert_called_once_with(CLOSE_NORMAL, "quit")
