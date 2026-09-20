"""Every websocket message type the server can send has a client case (#3933)."""

from pathlib import Path
import re

from django.test import SimpleTestCase

from web.webclient.message_types import WebsocketMessageType

CLIENT_TYPES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "hooks" / "types.ts"

_TABLE_START = "export const WS_MESSAGE_TYPE = {"
_TABLE_END = "} as const"


class ClientTableMarkerMissing(AssertionError):
    """``types.ts`` no longer delimits ``WS_MESSAGE_TYPE`` the way we scan for it."""

    def __init__(self, marker: str) -> None:
        super().__init__(f"the client type table no longer contains {marker!r}; update this scan")


def client_message_types(source: str) -> set[str]:
    """Return the string literals inside the ``WS_MESSAGE_TYPE`` table only.

    The rest of ``types.ts`` is full of unrelated single-quoted literals
    (``'channel'``, ``'error'``, ``'system'``, ...), so scanning the whole file
    would let a server type pass parity on a coincidence elsewhere.
    """
    start = source.find(_TABLE_START)
    if start == -1:
        raise ClientTableMarkerMissing(_TABLE_START)
    end = source.find(_TABLE_END, start)
    if end == -1:
        raise ClientTableMarkerMissing(_TABLE_END)
    return set(re.findall(r"'([a-z_]+)'", source[start + len(_TABLE_START) : end]))


class ClientMessageTypeExtractionTests(SimpleTestCase):
    """The extraction itself, against in-memory sources rather than the real file."""

    def test_a_literal_outside_the_table_does_not_count(self) -> None:
        source = (
            "export const GAME_MESSAGE_TYPE = { SYSTEM: 'system' } as const;\n"
            "export const WS_MESSAGE_TYPE = {\n  TEXT: 'text',\n} as const;\n"
            "export const EVENNIA_CONTROL_TYPES = ['channel'];\n"
        )
        self.assertEqual(client_message_types(source), {"text"})

    def test_a_missing_start_marker_fails_loudly(self) -> None:
        with self.assertRaises(ClientTableMarkerMissing):
            client_message_types("export const OTHER = { TEXT: 'text' } as const;\n")

    def test_a_missing_end_marker_fails_loudly(self) -> None:
        with self.assertRaises(ClientTableMarkerMissing):
            client_message_types("export const WS_MESSAGE_TYPE = {\n  TEXT: 'text',\n")


class MessageTypeParityTests(SimpleTestCase):
    def test_the_client_type_table_exists(self) -> None:
        self.assertTrue(CLIENT_TYPES.is_file(), CLIENT_TYPES)

    def test_every_server_type_is_named_in_the_client_table(self) -> None:
        named = client_message_types(CLIENT_TYPES.read_text(encoding="utf-8"))
        missing = sorted(m.value for m in WebsocketMessageType if m.value not in named)
        self.assertEqual(missing, [], f"add these to WS_MESSAGE_TYPE in {CLIENT_TYPES.name}")
