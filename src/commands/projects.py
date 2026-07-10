"""Telnet surface for project contribution + status (#1574).

``+project <id>`` shows a project's status; ``project/donate`` gives money, ``project/check``
makes an authored check-based contribution (spending AP), and ``project/story`` records the
narrative of how you helped. Thin over the project-contribution actions + the read layer;
no business logic in the command.
"""

from __future__ import annotations

from typing import Any

from actions.base import Action
from actions.definitions.projects import (
    CheckContributeAction,
    DonateToProjectAction,
    LaunchPropagandaCampaignAction,
    StoryContributeAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdProject(ArxCommand):
    """View a project or contribute to it.

    Usage:
      +project <id>                 — show a project's status
      project/donate <id>=<amount>  — donate money from your purse
      project/check <id>=<method>   — make a check-based contribution (spends AP)
      project/story <id>=<text>     — record how you helped (your latest contribution)
      project/launch <tier>=<name>  — launch a propaganda campaign (#1621);
                                      bare project/launch lists the scales
    """

    key = "project"
    aliases = ("+project",)
    locks = "cmd:all()"
    help_category = "Projects"
    action = DonateToProjectAction()

    def _execute(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        if "donate" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            self._dispatch(self.action, self._parse_id_value("project/donate", numeric=True))
            return
        if "check" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            parsed = self._parse_id_value("project/check", numeric=False)
            self._dispatch(
                CheckContributeAction(),
                {"project_id": parsed["project_id"], "method_name": parsed["value"]},
            )
            return
        if "story" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            parsed = self._parse_id_value("project/story", numeric=False)
            self._dispatch(
                StoryContributeAction(),
                {"project_id": parsed["project_id"], "text": parsed["value"]},
            )
            return
        if "launch" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            self._launch_campaign()
            return
        self._show_status()

    def _launch_campaign(self) -> None:
        """``project/launch <tier>=<name>``; the bare form lists the active scales."""
        from world.currency.constants import format_coppers  # noqa: PLC0415
        from world.societies.models import PropagandaCampaignTier  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            tiers = list(PropagandaCampaignTier.objects.filter(is_active=True))
            if not tiers:
                self.msg("No campaign scales are currently offered.")
                return
            lines = ["|wPropaganda campaign scales|n (project/launch <tier>=<name>):"]
            lines.extend(
                f"  {tier.name} — {format_coppers(tier.threshold_coppers)}" for tier in tiers
            )
            self.msg("\n".join(lines))
            return
        if "=" not in raw:
            msg = "Usage: project/launch <tier>=<campaign name>"
            raise CommandError(msg)
        tier_part, name_part = (part.strip() for part in raw.split("=", 1))
        if not tier_part or not name_part:
            msg = "Usage: project/launch <tier>=<campaign name>"
            raise CommandError(msg)
        tier = (
            PropagandaCampaignTier.objects.filter(pk=int(tier_part)).first()
            if tier_part.isdigit()
            else PropagandaCampaignTier.objects.filter(name__iexact=tier_part).first()
        )
        if tier is None:
            msg = f"No campaign scale named '{tier_part}'. Bare project/launch lists them."
            raise CommandError(msg)
        self._dispatch(
            LaunchPropagandaCampaignAction(),
            {"tier_id": tier.pk, "campaign_name": name_part},
        )

    def _dispatch(self, action: Action, kwargs: dict[str, Any]) -> None:
        result = action.run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _parse_id_value(self, usage: str, *, numeric: bool) -> dict[str, Any]:
        raw = (self.args or "").strip()
        if "=" not in raw:
            msg = f"Usage: {usage} <id>=<value>"
            raise CommandError(msg)
        id_part, value_part = (part.strip() for part in raw.split("=", 1))
        if not id_part.isdigit() or not value_part:
            msg = f"Usage: {usage} <id>=<value>"
            raise CommandError(msg)
        if numeric:
            if not value_part.isdigit():
                msg = "The amount must be a number."
                raise CommandError(msg)
            return {"project_id": int(id_part), "amount": int(value_part)}
        return {"project_id": int(id_part), "value": value_part}

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
