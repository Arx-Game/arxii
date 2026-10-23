"""Exercise malformed and fragmented input through the configured telnet protocol."""

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase
from evennia.server.portal.naws import NAWS, Naws
from evennia.utils.utils import class_from_module
from hypothesis import given, settings as hypothesis_settings, strategies as st
from twisted.conch import telnet
from twisted.internet.testing import StringTransport


class TelnetInputTests(SimpleTestCase):
    """The socket boundary closes invalid streams and preserves normal traffic."""

    def setUp(self):
        self.warning = self.enterContext(patch("server.portal.telnet.logger.warning"))

    def protocol(self):
        protocol = class_from_module(settings.TELNET_PROTOCOL_CLASS)()
        protocol.transport = StringTransport()
        protocol.protocol_flags = {}
        protocol.line_buffer = b""
        protocol.sessid = 1
        protocol.sessionhandler = Mock(spec=["data_in", "sync", "get"])
        return protocol

    def test_invalid_command_closes_without_error_or_later_input(self):
        protocol = self.protocol()
        with patch("evennia.utils.logger.log_err") as error:
            protocol.dataReceived(telnet.IAC + b"\x02")
            self.assertTrue(protocol.transport.disconnecting)
            protocol.dataReceived(b"look\r\n")
        error.assert_not_called()
        self.warning.assert_called_once_with(
            "Closing telnet connection with an unsupported command"
        )
        protocol.sessionhandler.data_in.assert_not_called()

    def test_invalid_command_split_across_packets_closes(self):
        protocol = self.protocol()
        protocol.dataReceived(telnet.IAC)
        self.assertFalse(protocol.transport.disconnecting)
        with patch("evennia.utils.logger.log_err") as error:
            protocol.dataReceived(b"\x02")
        self.assertTrue(protocol.transport.disconnecting)
        error.assert_not_called()

    def test_every_unsupported_command_closes(self):
        supported = {
            telnet.IAC,
            telnet.SB,
            telnet.EOR,
            telnet.NOP,
            telnet.DM,
            telnet.BRK,
            telnet.IP,
            telnet.AO,
            telnet.AYT,
            telnet.EC,
            telnet.EL,
            telnet.GA,
            telnet.WILL,
            telnet.WONT,
            telnet.DO,
            telnet.DONT,
        }
        for value in range(256):
            byte = bytes([value])
            if byte in supported:
                continue
            with self.subTest(value=value), patch("evennia.utils.logger.log_err") as error:
                protocol = self.protocol()
                protocol.dataReceived(telnet.IAC + byte)
                self.assertTrue(protocol.transport.disconnecting)
                error.assert_not_called()

    @hypothesis_settings(max_examples=40, deadline=None)
    @given(st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=12))
    def test_valid_stream_survives_arbitrary_packet_boundaries(self, sizes):
        protocol = self.protocol()
        stream = b"look\r\n" + telnet.IAC + telnet.NOP + b"say " + telnet.IAC * 2 + b"\r\n"
        offset = 0
        for size in sizes:
            protocol.dataReceived(stream[offset : offset + size])
            offset += size
        protocol.dataReceived(stream[offset:])
        self.assertFalse(protocol.transport.disconnecting)
        self.assertEqual(
            [call.kwargs["text"] for call in protocol.sessionhandler.data_in.call_args_list],
            [b"look\n", b"say " + telnet.IAC + b"\n"],
        )

    def test_option_payload_is_not_mistaken_for_a_command(self):
        protocol = self.protocol()
        protocol.dataReceived(telnet.IAC + telnet.WILL + b"\x02")
        self.assertFalse(protocol.transport.disconnecting)
        self.assertEqual(protocol.transport.value(), telnet.IAC + telnet.DONT + b"\x02")

    def test_subnegotiation_payload_may_contain_escaped_bytes(self):
        protocol = self.protocol()
        # Unknown options are ignored by Twisted; their payload is not a command stream.
        protocol.dataReceived(telnet.IAC + telnet.SB + b"\x7f" + telnet.IAC)
        protocol.dataReceived(b"\x02" + telnet.IAC + telnet.SE + b"look\r\n")
        self.assertFalse(protocol.transport.disconnecting)
        protocol.sessionhandler.data_in.assert_called_once_with(protocol, text=b"look\n")

    def test_window_size_negotiation_keeps_resize_sync(self):
        protocol = self.protocol()
        protocol.handshakes = 2
        protocol.naws = Naws(protocol)
        protocol.dataReceived(telnet.IAC + telnet.WILL + NAWS)
        self.assertTrue(protocol.protocol_flags["AUTORESIZE"])
        protocol.dataReceived(
            telnet.IAC + telnet.SB + NAWS + b"\x00\x50\x00\x18" + telnet.IAC + telnet.SE
        )
        self.assertEqual(protocol.protocol_flags["SCREENWIDTH"], {0: 80})
        self.assertEqual(protocol.protocol_flags["SCREENHEIGHT"], {0: 24})
        protocol.sessionhandler.sync.assert_called_once()

    def test_application_value_error_is_still_reported(self):
        protocol = self.protocol()
        protocol.sessionhandler.data_in.side_effect = ValueError("application failure")
        with patch("evennia.utils.logger.log_err") as error:
            protocol.dataReceived(b"look\r\n")
        error.assert_called_once()
        self.assertFalse(protocol.transport.disconnecting)
