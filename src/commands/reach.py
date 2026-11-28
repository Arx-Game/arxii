"""Telnet reaching (#5308) and marking (#5327): the pose switch that names a resonance.

    pose/reach <resonance>=<text>
    pose/reach <resonance>:<number>=<text>

``pose/reach`` poses ``<text>`` and records that the pose reaches for the resonance named before
the ``=``, held or not. An endorsement of the pose pays that resonance. With ``:<number>`` it
marks the act with that id (the number the ``acts`` list prints) instead: the pose points at
what the character did, and the mark pays at once. It stands alone, because ``=`` already
belongs to the other attachments. No game logic lives here: the service resolves the name and
the pose action checks the reach or the mark before the pose posts and writes it after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.exceptions import CommandError
from world.magic.exceptions import ReachError
from world.magic.services.reach import resolve_reach_name

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

SWITCH_REACH = "reach"
REACH_USAGE = "Usage: pose/reach <resonance>[:<act number>]=<text>"
NO_SUCH_ACT = "You have no act number {number}. Use 'acts' to see the acts you can mark."


def reach_kwargs_and_rest(args: str, sheet: CharacterSheet | None) -> tuple[dict[str, Any], str]:
    """Split ``<resonance>[:<number>]=<rest>`` into the pose action's kwargs and the rest.

    The number is an act's own id, as the ``acts`` list prints it, so the kwargs carry
    ``reach_act_id`` beside ``reach_resonance_id`` and the pose marks that act. A line with no
    ``=`` or no resonance name, a name that matches no resonance, or a number with no act is the
    command's own error, and nothing is posted.
    """
    if "=" not in args:
        raise CommandError(REACH_USAGE)
    name, _, rest = args.partition("=")
    name, colon, number_text = name.rpartition(":") if ":" in name else (name, "", "")
    if not name.strip():
        raise CommandError(REACH_USAGE)
    try:
        resonance_id = resolve_reach_name(name)
    except ReachError as exc:
        raise CommandError(exc.user_message) from exc
    kwargs: dict[str, Any] = {"reach_resonance_id": resonance_id}
    if colon:
        kwargs["reach_act_id"] = _act_id_for(sheet, number_text.strip())
    return kwargs, rest


def _act_id_for(sheet: CharacterSheet | None, number_text: str) -> int:
    """``number_text`` as the id of one of ``sheet``'s acts a mark can still point at."""
    from world.magic.services.marking import pointable_acts_queryset  # noqa: PLC0415

    if not number_text.isdigit() or sheet is None:
        raise CommandError(REACH_USAGE)
    number = int(number_text)
    if not pointable_acts_queryset().filter(character_sheet=sheet, pk=number).exists():
        raise CommandError(NO_SUCH_ACT.format(number=number))
    return number
