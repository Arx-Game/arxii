"""Telnet surface for project contribution + status (#1574).

``+project <id>`` shows a project's status; ``project/donate <id>=<amount>`` donates money
from your purse. The check / story switches land alongside these once the per-ProjectKind
check-method framework ships. Thin over ``DonateToProjectAction`` + the projects read layer;
no business logic in the command.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.projects import DonateToProjectAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdProject(ArxCommand):
    """View a project or contribute to it.

    Usage:
      +project <id>                 — show a project's status
      project/donate <id>=<amount>  — donate money from your purse
    """

    key = "project"
    aliases = ("+project",)
    locks = "cmd:all()"
    help_category = "Projects"
    action = DonateToProjectAction()

    def _execute(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        if "donate" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            kwargs = self._parse_donate()
            result = self.action.run(actor=self.caller, **kwargs)
            if result.message:
                self.msg(result.message)
            return
        self._show_status()

    def _parse_donate(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        if "=" not in raw:
            msg = "Usage: project/donate <id>=<amount>"
            raise CommandError(msg)
        id_part, amount_part = (part.strip() for part in raw.split("=", 1))
        if not id_part.isdigit() or not amount_part.isdigit():
            msg = "Both the project id and the amount must be numbers."
            raise CommandError(msg)
        return {"project_id": int(id_part), "amount": int(amount_part)}

    def _show_status(self) -> None:
        from world.currency.constants import format_coppers  # noqa: PLC0415
        from world.projects.constants import CompletionMode  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415

        arg = (self.args or "").strip()
        if not arg.isdigit():
            msg = "Which project? Usage: +project <id>"
            raise CommandError(msg)
        project = Project.objects.filter(pk=int(arg)).first()
        if project is None:
            msg = "No such project."
            raise CommandError(msg)

        target = project.threshold_target
        progress = (
            f"{project.current_progress}/{target}"
            if target is not None
            else str(project.current_progress)
        )
        lines = [
            f"|wProject #{project.pk}|n — {project.get_kind_display()} [{project.status}]",
        ]
        if project.description:
            lines.append(project.description)
        lines.append(f"Progress: {progress}")
        if target is not None and project.completion_mode == CompletionMode.SINGLE_THRESHOLD:
            # Money projects fund at 1 progress per 100 coppers; show the coin cost left.
            remaining = max(0, target - project.current_progress)
            lines.append(f"Remaining to fund: {format_coppers(remaining * 100)}")
        self.msg("\n".join(lines))
