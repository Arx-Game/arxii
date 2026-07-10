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


_MSG_NO_CHARACTER_SHEET = "You have no character sheet."
_MSG_NO_SUCH_PROJECT = "No such project."


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
            return _ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return _ActionResult(success=False, message="You have no active persona to donate as.")

        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            return _ActionResult(success=False, message=_MSG_NO_SUCH_PROJECT)

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


@dataclass
class CheckContributeAction(Action):
    """Make a check-based contribution to a project via an authored method (#1574).

    Rolls the method's check (spending its AP cost); a success advances the project. The
    available methods are keyed by the project's ``ProjectKind`` — projects of a kind with
    no method (e.g. a ransom) offer no check path.
    """

    key: str = "project_check"
    name: str = "Contribute (Check)"
    icon: str = "dice"
    category: str = "projects"
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911 — distinct guard returns, each a specific failure message
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        project_id: int | None = None,
        method_name: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.projects.models import ContributionMethod, Project  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            ContributionMethodError,
            ProjectNotActiveError,
            contribute_check_to_project,
        )
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        if project_id is None or not method_name:
            return _ActionResult(success=False, message="Contribute to which project, and how?")
        sheet = actor.sheet_data
        if sheet is None:
            return _ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return _ActionResult(success=False, message="You have no active persona.")

        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            return _ActionResult(success=False, message=_MSG_NO_SUCH_PROJECT)
        method = ContributionMethod.objects.filter(
            kind=project.kind, name__iexact=method_name, is_active=True
        ).first()
        if method is None:
            return _ActionResult(
                success=False, message=f"No '{method_name}' method for this project."
            )

        try:
            contribution = contribute_check_to_project(
                project, actor=actor, contributor_persona=persona, method=method
            )
        except (ContributionMethodError, ProjectNotActiveError) as exc:
            return _ActionResult(success=False, message=str(exc))

        outcome = contribution.check_outcome
        succeeded = outcome is not None and outcome.success_level >= 0
        verb = "advances" if succeeded else "fails to advance"
        target = project.threshold_target
        progress = f"{project.current_progress}/{target}" if target is not None else "—"
        return _ActionResult(
            success=True,
            message=(
                f"Your {method.name} check {verb} project #{project.pk}. Progress: {progress}."
            ),
        )


@dataclass
class StoryContributeAction(Action):
    """Record the narrative of how you helped — your latest contribution to a project (#1574)."""

    key: str = "project_story"
    name: str = "Contribution Story"
    icon: str = "scroll"
    category: str = "projects"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        project_id: int | None = None,
        text: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415
        from world.projects.services import set_contribution_story  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        if project_id is None or not text:
            return _ActionResult(success=False, message="Tell the story for which project?")
        sheet = actor.sheet_data
        if sheet is None:
            return _ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return _ActionResult(success=False, message="You have no active persona.")

        project = Project.objects.filter(pk=project_id).first()
        if project is None:
            return _ActionResult(success=False, message=_MSG_NO_SUCH_PROJECT)

        contribution = set_contribution_story(project, contributor_persona=persona, text=text)
        if contribution is None:
            return _ActionResult(
                success=False, message="You have not contributed to that project yet."
            )
        return _ActionResult(success=True, message="Your contribution's story is recorded.")


@dataclass
class LaunchPropagandaCampaignAction(Action):
    """Launch a propaganda campaign — the money→prestige sink (#1621).

    Creates an ACTIVE PROPAGANDA project at a chosen authored tier; anyone may
    then fund it via ``project/donate``. At threshold the campaign completes
    instantly and fires the sponsor's renown award (the only project→fame
    path). Telnet: ``project/launch <tier> name=<text>``.
    """

    key: str = "launch_propaganda_campaign"
    name: str = "Launch Propaganda Campaign"
    icon: str = "megaphone"
    category: str = "projects"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        tier_id: int | None = None,
        campaign_name: str = "",
        description: str = "",
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.societies.models import PropagandaCampaignTier  # noqa: PLC0415
        from world.societies.propaganda import (  # noqa: PLC0415
            PropagandaError,
            launch_propaganda_campaign,
        )

        if tier_id is None or not campaign_name.strip():
            return _ActionResult(
                success=False, message="Pick a campaign scale and give the campaign a name."
            )
        sheet = actor.sheet_data
        if sheet is None:
            return _ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return _ActionResult(success=False, message="You have no active persona.")

        tier = PropagandaCampaignTier.objects.filter(pk=tier_id).first()
        if tier is None:
            return _ActionResult(success=False, message="No such campaign scale.")

        try:
            project = launch_propaganda_campaign(
                owner_persona=persona,
                tier=tier,
                campaign_name=campaign_name.strip(),
                description=description,
            )
        except PropagandaError as exc:
            return _ActionResult(success=False, message=exc.user_message)

        return _ActionResult(
            success=True,
            message=(
                f"Campaign '{campaign_name.strip()}' launched (project #{project.pk}). "
                f"Fund it with project/donate {project.pk}=<amount>."
            ),
            data={"project_id": project.pk},
        )
