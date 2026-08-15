"""Telnet face of the sticky declared-mood switch + empathy sense (#2994).

Thin `ArxCommand` shells over `SetMoodAction`/`SenseMoodAction`
(`actions/definitions/mood.py`) -- no business logic lives here, only
name/target resolution. `feel` is INTERNAL and SILENT (see `SetMoodAction`'s
docstring); `sense` is the earned-empathy read of another's mood.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.mood import SenseMoodAction, SetMoodAction
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


class CmdSense(ArxCommand):
    """Try to privately read a co-located character's declared mood.

    Usage:
      sense <character>

    Gated on an earned Empathy specialization and resolved via a check --
    see `SenseMoodAction`. SILENT to the target in every outcome; only you
    ever see a message.
    """

    key = "sense"
    locks = "cmd:all()"
    action = SenseMoodAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = (self.args or "").strip()
        if not name:
            msg = "Usage: sense <character>"
            raise CommandError(msg)

        target = self.caller.search(name)
        if not target:
            msg = f"Could not find '{name}'."
            raise CommandError(msg)
        return {"target": target}
