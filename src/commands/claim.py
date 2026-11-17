"""Telnet claiming (#5181): the pose switch that collects resonance a kindled deed set aside.

    pose/claim <text>
    pose/claim <resonance>[,<resonance>...]=<text>

``pose/claim`` poses ``<text>`` and claims everything waiting; naming resonances before ``=``
claims only those. It combines with ``pose/reflect``, ``pose/entreat`` and ``pose/sineat`` (as
``pose/claim/reflect``), where it claims everything waiting, because ``=`` already belongs to
the other part. No game logic lives here: the service resolves the names and the pose action
checks the claim before the pose posts and collects it after.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.exceptions import ClaimError
from world.magic.services.claiming import resolve_waiting_names

SWITCH_CLAIM = "claim"
NO_SHEET = "You have no character sheet."


def claim_kwargs_and_rest(
    command: ArxCommand, args: str, *, names_allowed: bool
) -> tuple[dict[str, Any], str]:
    """Split ``[<names>=]<rest>`` into the pose action's claim kwargs and the rest.

    With ``names_allowed`` false (another attachment owns the ``=``) the claim is for everything
    waiting and ``args`` is returned untouched. A name that matches no resonance the character
    has something waiting in is the command's own error, and nothing is posted.
    """
    sheet = command.caller.character_sheet
    if sheet is None:
        raise CommandError(NO_SHEET)
    if not names_allowed or "=" not in args:
        return {"claim": True}, args
    names, _, rest = args.partition("=")
    try:
        ids = resolve_waiting_names(sheet, names.split(","))
    except ClaimError as exc:
        raise CommandError(exc.user_message) from exc
    return {"claim": True, "claim_resonance_ids": list(ids)}, rest
