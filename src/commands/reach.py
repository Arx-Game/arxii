"""Telnet reaching (#5308): the pose switch that names the resonance a pose reaches for.

    pose/reach <resonance>=<text>

``pose/reach`` poses ``<text>`` and records that the pose reaches for the resonance named before
the ``=``, held or not. An endorsement of the pose pays that resonance. It stands alone, because
``=`` already belongs to the other attachments. No game logic lives here: the service resolves
the name and the pose action checks the reach before the pose posts and writes it after.
"""

from __future__ import annotations

from typing import Any

from commands.exceptions import CommandError
from world.magic.exceptions import ReachError
from world.magic.services.reach import resolve_reach_name

SWITCH_REACH = "reach"
REACH_USAGE = "Usage: pose/reach <resonance>=<text>"


def reach_kwargs_and_rest(args: str) -> tuple[dict[str, Any], str]:
    """Split ``<resonance>=<rest>`` into the pose action's reach kwargs and the rest.

    A line with no ``=`` or no resonance name, or a name that matches no resonance, is the
    command's own error, and nothing is posted.
    """
    if "=" not in args:
        raise CommandError(REACH_USAGE)
    name, _, rest = args.partition("=")
    if not name.strip():
        raise CommandError(REACH_USAGE)
    try:
        resonance_id = resolve_reach_name(name)
    except ReachError as exc:
        raise CommandError(exc.user_message) from exc
    return {"reach_resonance_id": resonance_id}, rest
