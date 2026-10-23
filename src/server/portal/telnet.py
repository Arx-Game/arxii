"""Reject unsupported telnet commands before Evennia's error-logging wrapper."""

# ruff: noqa: N802 -- Twisted extension API names.

import logging

from evennia.server.portal.telnet import TelnetProtocol
from twisted.conch import telnet

logger = logging.getLogger(__name__)

_ESCAPED_STATE = "escaped"

_COMMANDS = frozenset(
    (
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
    )
)
# Twisted's framing transitions only; it still interprets and dispatches all data.
_TRANSITIONS = {
    "data": {telnet.IAC: "escaped", b"\r": "newline"},
    "escaped": {
        telnet.SB: "subnegotiation",
        **dict.fromkeys((telnet.WILL, telnet.WONT, telnet.DO, telnet.DONT), "command"),
    },
    "newline": {telnet.IAC: "escaped"},
    "subnegotiation": {telnet.IAC: "subnegotiation-escaped"},
    "subnegotiation-escaped": {telnet.SE: "data"},
}
_DEFAULT_STATES = {
    "data": "data",
    "escaped": "data",
    "command": "data",
    "newline": "data",
    "subnegotiation": "subnegotiation",
    "subnegotiation-escaped": "subnegotiation",
}


def _invalid_command(data: bytes, state: str) -> bool:
    """Preflight Twisted's framing without interpreting or consuming payloads.

    Start from the real parser's state so a command split between TCP packets
    has the same result. Only an unsupported byte in command position is refused;
    option and subnegotiation payloads remain the upstream parser's responsibility.
    """
    if telnet.IAC not in data and state != _ESCAPED_STATE:
        return False
    for value in data:
        byte = bytes([value])
        if state == _ESCAPED_STATE and byte not in _COMMANDS:
            return True
        state = _TRANSITIONS.get(state, {}).get(byte, _DEFAULT_STATES.get(state, state))
    return False


class ValidatedTelnetProtocol(TelnetProtocol):
    """Close malformed streams once, keeping the stock negotiation and resize path."""

    _invalid_input = False

    def dataReceived(self, data: bytes) -> None:
        """Refuse invalid framing without logging client bytes or an exception."""
        if self._invalid_input:
            return
        if _invalid_command(data, self.state):
            self._invalid_input = True
            logger.warning("Closing telnet connection with an unsupported command")
            self.transport.loseConnection()
            return
        super().dataReceived(data)
