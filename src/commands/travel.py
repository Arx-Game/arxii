"""Telnet `travel` command (#2163) — dispatches TravelAction/StopTravelAction.

Modeled on CmdPosition (commands/positions.py): overrides func() directly
(rather than the base ArxCommand._execute() single-action-dispatch recipe)
since resolving the destination argument needs custom logic before dispatch.
"""

from actions.definitions.movement import StopTravelAction, TravelAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_STOP_TOKEN = "stop"  # noqa: S105


class CmdTravel(ArxCommand):
    """Auto-walk to a character's location, or stop an in-progress walk.

    Usage:
      travel <character name>
      travel stop
    """

    key = "travel"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self.msg("Travel to whom? (Usage: travel <character name> | travel stop)")
            return

        if raw.lower() == _STOP_TOKEN:
            self._do_stop()
            return

        try:
            self._do_travel(raw)
        except CommandError as err:
            self.msg(str(err))

    def _do_travel(self, name: str) -> None:
        target_char = self.caller.search(name, global_search=True)
        if target_char is None:
            # caller.search() already messaged the caller on no-match.
            return
        destination = target_char.location
        if destination is None:
            msg = f"{target_char.name} has no location to travel to."
            raise CommandError(msg)

        result = TravelAction().run(self.caller, target=destination)
        if result.message:
            self.msg(result.message)

    def _do_stop(self) -> None:
        result = StopTravelAction().run(self.caller)
        if result.message:
            self.msg(result.message)
