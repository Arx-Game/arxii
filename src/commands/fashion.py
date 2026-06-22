"""Telnet fashion commands — thin shells over fashion Actions (#1340).

CmdJudgePresentation: ``judge <presentation_id>``

Delegates entirely to ``JudgePresentationAction`` — no business logic here.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.fashion import JudgePresentationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdJudgePresentation(ArxCommand):
    """Endorse a fashion presentation at an event.

    Syntax:
        judge <presentation_id>

    Judges (endorses) the given fashion presentation. You must not be the
    presenter or share an account with the presenter. Each judge may
    endorse a given presentation only once.

    Example:
        judge 42
    """

    key = "judge"
    locks = "cmd:all()"
    action = JudgePresentationAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args("Judge which presentation? (judge <id>)")
        if not args.strip().isdigit():
            msg = "The presentation id must be a number: judge <id>"
            raise CommandError(msg)
        return {"presentation_id": int(args.strip())}
