"""Telnet face of the sticky declared-mood switch (#2994).

Thin `ArxCommand` shell over `SetMoodAction` (`actions/definitions/mood.py`) --
no business logic lives here, only name-to-pk resolution. INTERNAL and SILENT:
the resulting message is self-only (see `SetMoodAction`'s docstring).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.mood import SetMoodAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdFeel(ArxCommand):
    """Declare (or clear) your internal mood.

    Usage:
      feel <mood>   - declare <mood> as your current internal state
      feel          - clear your declared mood

    Silent and internal -- nothing is shown to the room. Others learn your mood
    only if they can read it via an earned empathy sense.
    """

    key = "feel"
    locks = "cmd:all()"
    action = SetMoodAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = (self.args or "").strip()
        if not name:
            return {}

        from world.character_sheets.models import MoodOption  # noqa: PLC0415

        mood = MoodOption.objects.filter(name__iexact=name, is_active=True).first()
        if mood is None:
            msg = f"There is no mood called '{name}'."
            raise CommandError(msg)
        return {"mood_id": mood.pk}
