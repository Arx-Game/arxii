"""Telnet Sineating (#5177): the pose switches that attach the plea and the ritual to a pose.

    pose/entreat <sineater>=<units> <text>
    pose/sineat <sinner>=<units> <text>

``pose/entreat`` is the Sinner's plea and ``pose/sineat`` the Sineater's ritual. The partner
is named by name; the units are how many to offer, or how many of those offered to take on.
No game logic lives here: the pose action checks the plea or the ritual before posting the
pose and carries it out after.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.constants import SineatingPoseRole

# The pose switch that names each part.
SWITCH_ENTREAT = "entreat"
SWITCH_SINEAT = "sineat"
SINEATING_SWITCHES = {
    SWITCH_ENTREAT: SineatingPoseRole.ENTREAT,
    SWITCH_SINEAT: SineatingPoseRole.PERFORM,
}


def sineating_kwargs_and_rest(
    command: ArxCommand, role: str, args: str, *, usage: str
) -> tuple[dict[str, Any], str]:
    """Split ``<partner>=<units> <rest>`` into the pose action's Sineating kwargs and rest.

    ``usage`` is the whole line's usage, shown when the shape is wrong. The partner must be a
    character here with a sheet.
    """
    name, equals, after = args.strip().partition("=")
    units_text, _, rest = after.strip().partition(" ")
    if not equals or not name.strip() or not units_text.isdigit() or int(units_text) < 1:
        raise CommandError(usage)
    partner = command.search_or_raise(name.strip())
    sheet = partner.character_sheet
    if sheet is None:
        msg = f"{partner.key} cannot take part in Sineating."
        raise CommandError(msg)
    return (
        {
            "sineating_role": role,
            "sineating_partner_id": sheet.pk,
            "sineating_units": int(units_text),
        },
        rest.strip(),
    )
