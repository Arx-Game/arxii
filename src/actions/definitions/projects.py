"""Project-contribution actions (#1574).

The shared seam telnet (``CmdProject``) and any future web surface converge on for
contributing to a Project. ``DonateToProjectAction`` is the money path; check / story
contribution actions land alongside it when the per-ProjectKind check-method framework
ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext, ActionResult


@dataclass
class DonateToProjectAction(Action):
    """Donate money from your own purse to an ACTIVE project (#1574).

    Anyone may donate; the spend + the contribution land atomically and advance the
    project's progress. Used by the telnet ``project/donate`` switch and reused by the
    ransom flow (a Ransom is a money-threshold Project — #1500).
    """

    key: str = "project_donate"
    name: str = "Donate to Project"
    icon: str = "coins"
    category: str = "projects"
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911 — distinct guard returns, each a specific failure message
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        project_id: int | None = None,
        amount: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.currency.constants import format_coppers  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            ProjectNotActiveError,
            donate_to_project,
        )
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        if project_id is None or amount is None:
            return _ActionResult(success=False, message="Donate how much to which project?")
        if amount <= 0:
            return _ActionResult(success=False, message="Donate a positive amount.")

        sheet = actor.sheet_data
        if sheet is None:
            return _ActionResult(success=False, message="You have no character sheet.")
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return _ActionResult(success=False, message="You have no active persona to donate as.")

        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            return _ActionResult(success=False, message="No such project.")

        try:
            donate_to_project(project, donor_persona=persona, amount=amount)
        except DjangoValidationError as exc:
            return _ActionResult(success=False, message="; ".join(exc.messages))
        except ProjectNotActiveError as exc:
            return _ActionResult(success=False, message=str(exc))

        target = project.threshold_target
        progress = f"{project.current_progress}/{target}" if target is not None else "—"
        return _ActionResult(
            success=True,
            message=(
                f"You donate {format_coppers(amount)} to project #{project.pk}. "
                f"Progress: {progress}."
            ),
        )
