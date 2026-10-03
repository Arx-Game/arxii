"""Telnet verbs for after-fight allegiance choices (#4091): settle, sendaway, retain."""

from __future__ import annotations

from commands.consent import ConsentRequestCommand


class CmdSettle(ConsentRequestCommand):
    """Settle a charm, turn or calm on an NPC. Anyone in the scene may try.

    Usage:
        settle <character>
    """

    key = "settle"
    action_key = "settle"
    help_category = "Social"
