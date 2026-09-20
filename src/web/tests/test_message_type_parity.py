"""Every websocket message type the server can send has a client case (#3933)."""

from pathlib import Path
import re

from django.test import SimpleTestCase

from web.webclient.message_types import WebsocketMessageType

CLIENT_TYPES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "hooks" / "types.ts"


class MessageTypeParityTests(SimpleTestCase):
    def test_the_client_type_table_exists(self) -> None:
        self.assertTrue(CLIENT_TYPES.is_file(), CLIENT_TYPES)

    def test_every_server_type_is_named_in_the_client_table(self) -> None:
        source = CLIENT_TYPES.read_text(encoding="utf-8")
        named = set(re.findall(r"'([a-z_]+)'", source))
        missing = sorted(m.value for m in WebsocketMessageType if m.value not in named)
        self.assertEqual(missing, [], f"add these to WS_MESSAGE_TYPE in {CLIENT_TYPES.name}")
