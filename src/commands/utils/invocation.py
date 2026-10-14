"""Telnet grammar for calling on a being's favor (#4333).

Every check surface takes the same trailing segment: ``/invoke <being>[=<line>]``,
for example ``mission resolve 12 1/invoke Ombrin=A hush falls`` or
``check perception at hard /invoke Ombrin``. ``invoke`` on its own lists the
beings a character can call on, how hard each is and the bonus by result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.worship.types import InvocationChoice

INVOKE_MARKER = "/invoke "
MSG_NO_BEING_NAMED = "Name the being to call on: '/invoke <being>[=<line>]'."


def split_invocation(raw: str) -> tuple[str, str | None, str]:
    """Split ``raw`` into (the rest, the being's name or None, the player's line)."""
    index = raw.lower().rfind(INVOKE_MARKER)
    if index < 0:
        return raw, None, ""
    rest = raw[:index].rstrip()
    name, _, line = raw[index + len(INVOKE_MARKER) :].partition("=")
    name = name.strip()
    if not name:
        raise CommandError(MSG_NO_BEING_NAMED)
    return rest, name, line.strip()


def invocation_choice_for(
    caller: ObjectDB, being_name: str | None, line: str
) -> InvocationChoice | None:
    """The choice for ``being_name`` as ``caller``'s character, or None when no
    being was named. Raises ``CommandError`` when no being has that name."""
    if being_name is None:
        return None
    from world.worship.invocation_services import (  # noqa: PLC0415
        MSG_NO_SUCH_BEING,
        find_being_to_invoke,
    )
    from world.worship.types import InvocationChoice  # noqa: PLC0415

    sheet = caller.character_sheet
    being = find_being_to_invoke(sheet, being_name) if sheet is not None else None
    if being is None:
        raise CommandError(MSG_NO_SUCH_BEING)
    return InvocationChoice(being_id=being.pk, player_line=line)
