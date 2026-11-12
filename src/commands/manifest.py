"""The technique picker on telnet (#4341): ``manifest``.

Bare ``manifest`` lists each manifesting technique the character knows with its options
(the chosen one marked, the ones whose bond does not hold with the reason).
``manifest <technique>=<option>`` dispatches ``manifest_set`` through the shared
player-action seam. No game logic lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef
    from world.magic.types.manifestation import ManifestChoice

USAGE = "Usage: manifest <technique>=<option>"


def choice_lines(choice: ManifestChoice) -> list[str]:
    """One technique's block: what it brings now, then each option."""
    lines = [f"|w{choice.technique_name}|n brings into a fight:"]
    for row in choice.options:
        chosen = choice.chosen is not None and choice.chosen.pk == row.option.pk
        if not row.available:
            lines.append(f"  {row.label} - unavailable: {row.reason}")
        elif chosen:
            lines.append(f"  {row.label} - chosen")
        else:
            lines.append(f"  {row.label}")
    return lines


class CmdManifest(DispatchCommand):
    """Choose which bound being or companion a technique brings into a fight.

    Usage:
        manifest                        - your techniques that bring someone, and options
        manifest <technique>=<option>   - choose what that technique brings

    An option is a being you hold a patronage with, or one of your own companions of
    the kind the technique can bring. Options whose bond does not hold are listed
    with the reason and cannot be chosen.
    """

    key = "manifest"
    locks = "cmd:all()"
    help_category = "Magic"

    def func(self) -> None:
        if not (self.args or "").strip():
            self._list()
            return
        super().func()

    def _list(self) -> None:
        from world.magic.services.manifestation import manifest_choices_for  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return
        choices = manifest_choices_for(sheet)
        if not choices:
            self.msg("You know no technique that brings anyone into a fight.")
            return
        lines: list[str] = []
        for choice in choices:
            lines.extend(choice_lines(choice))
        lines.append(USAGE)
        self.msg("\n".join(lines))

    def resolve_action_ref(self) -> ActionRef:
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="manifest_set")

    def resolve_action_args(self) -> dict[str, Any]:
        technique, sep, option = (self.args or "").partition("=")
        if not sep or not technique.strip() or not option.strip():
            raise CommandError(USAGE)
        return {"technique_name": technique.strip(), "option_name": option.strip()}
