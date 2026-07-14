"""Telnet face of SearchAction + StartInvestigationAction (#1866, #1825).

Bare ``search`` stays the room search it always was. ``search start`` opens the
research-lab door into the clue loop (#1825): it lists your held RESEARCH-mode leads,
and ``search start <#>`` opens the collaborative investigation project — the same
``start_investigation`` action the web dispatches. No business logic in the command.
"""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.investigation import SearchAction, StartInvestigationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_START = "start"
_START_USAGE = "Usage: search start [<#>]  (bare lists your researchable leads)"


class CmdSearch(ArxCommand):
    """Search your current room for clues — or open an investigation.

    Usage:
      search               — search the room for hidden clues
      investigate          — alias for search
      search start         — list the leads you could research at a lab
      search start <#>     — open an investigation project on lead # (needs a Lab)
    """

    key = "search"
    aliases: ClassVar[list[str]] = ["investigate"]
    locks = "cmd:all()"
    help_category = "General"
    action = SearchAction()

    def _execute(self) -> None:
        raw = (self.args or "").strip()
        verb, _, rest = raw.partition(" ")
        if verb.lower() == _START:
            self._start_investigation(rest.strip())
            return
        super()._execute()

    def _researchable_clues(self) -> list[Any]:
        from world.clues.constants import ClueResolution  # noqa: PLC0415
        from world.clues.models import CharacterClue  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            return []
        try:
            entry = sheet.roster_entry
        except RosterEntry.DoesNotExist:
            return []
        held = CharacterClue.objects.filter(
            roster_entry=entry, clue__resolution_mode=ClueResolution.RESEARCH
        ).select_related("clue")
        return [record.clue for record in held]

    def _start_investigation(self, arg: str) -> None:
        clues = self._researchable_clues()
        if not arg:
            if not clues:
                self.msg("You hold no leads that want researching.")
                return
            lines = ["|wLeads you could research:|n"]
            lines += [f"  {index}. {clue.name}" for index, clue in enumerate(clues, 1)]
            lines.append("Use |wsearch start <#>|n at a research lab to open the investigation.")
            self.msg("\n".join(lines))
            return
        try:
            position = int(arg) - 1
        except (ValueError, TypeError):
            raise CommandError(_START_USAGE) from None
        if not 0 <= position < len(clues):
            self.msg(f"No lead #{arg}. See |wsearch start|n for the list.")
            return
        result = StartInvestigationAction().run(self.caller, clue_id=clues[position].pk)
        self.msg(result.message)
